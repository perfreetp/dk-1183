from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta
import uuid

from config.database import get_db
from schemas.schemas import (
    ApplicationCreate, ApplicationUpdate, ApplicationResponse,
    ApiEndpointResponse, AccessScopeRequest, AccessScopeResponse,
    CallLogResponse, CallbackRequest, CallbackResponse,
    ApiResponse, ErrorResponse, TokenResponse, AppStatus
)
from services.auth_service import (
    AuthService, ApplicationService, AccessScopeService
)
from services.rate_limit_service import RateLimitService, CallLogService
from services.error_service import ErrorService, ValidationService
from services.callback_service import CallbackService
from models.database import Application, ApiEndpoint
from schemas.schemas import CallStatus

router = APIRouter(prefix="/api/v1", tags=["认证授权"])
security = HTTPBearer()

@router.post("/auth/app/register", response_model=ApiResponse)
def register_application(app_data: ApplicationCreate, db: Session = Depends(get_db)):
    application, app_secret = ApplicationService.create_application(db, app_data)
    
    return ApiResponse(
        code=200,
        message="Application registered successfully",
        data={
            "app_code": application.app_code,
            "app_secret": app_secret,
            "status": application.status.value
        }
    )

@router.post("/auth/token", response_model=TokenResponse)
def get_access_token(
    app_code: str,
    app_secret: str,
    db: Session = Depends(get_db)
):
    application = ApplicationService.get_application_by_code(db, app_code)
    
    if not application:
        raise HTTPException(
            status_code=401,
            detail=ErrorService.create_error_response("AUTH_001")
        )
    
    if not AuthService.verify_secret(app_secret, application.app_secret):
        raise HTTPException(
            status_code=401,
            detail=ErrorService.create_error_response("AUTH_001")
        )
    
    if application.status == AppStatus.SUSPENDED:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("AUTH_004")
        )
    
    if application.status == AppStatus.INACTIVE:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("AUTH_005")
        )
    
    access_token = AuthService.create_access_token(
        data={"sub": application.app_code, "app_id": application.id},
        expires_delta=timedelta(hours=1)
    )
    refresh_token = AuthService.create_refresh_token(
        data={"sub": application.app_code, "app_id": application.id}
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=3600,
        refresh_token=refresh_token
    )

@router.post("/auth/refresh")
def refresh_access_token(refresh_token: str, db: Session = Depends(get_db)):
    payload = AuthService.verify_token(refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=401,
            detail=ErrorService.create_error_response("AUTH_002")
        )
    
    app_code = payload.get("sub")
    application = ApplicationService.get_application_by_code(db, app_code)
    
    if not application or application.status != AppStatus.ACTIVE:
        raise HTTPException(
            status_code=401,
            detail=ErrorService.create_error_response("AUTH_001")
        )
    
    new_access_token = AuthService.create_access_token(
        data={"sub": application.app_code, "app_id": application.id},
        expires_delta=timedelta(hours=1)
    )
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": 3600
    }

async def verify_app_credentials(
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
) -> Application:
    if not authorization:
        if not all([app_code, signature, timestamp, nonce]):
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001")
            )
        
        application = ApplicationService.get_application_by_code(db, app_code)
        if not application:
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001")
            )
        
        expected_signature = AuthService.generate_signature(
            app_code, application.app_secret, timestamp, nonce
        )
        if signature != expected_signature:
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_003")
            )
    else:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001")
            )
        
        payload = AuthService.verify_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_002")
            )
        
        app_code = payload.get("sub")
        application = ApplicationService.get_application_by_code(db, app_code)
    
    if not application:
        raise HTTPException(
            status_code=401,
            detail=ErrorService.create_error_response("AUTH_001")
        )
    
    if application.status == AppStatus.SUSPENDED:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("AUTH_004")
        )
    
    if application.status == AppStatus.INACTIVE:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("AUTH_005")
        )
    
    return application

@router.get("/partner/apis", response_model=ApiResponse)
async def list_available_apis(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ApiEndpoint).filter(ApiEndpoint.is_active == True)
    
    if category:
        query = query.filter(ApiEndpoint.category == category)
    
    apis = query.all()
    
    api_list = [
        {
            "api_code": api.api_code,
            "api_name": api.api_name,
            "category": api.category.value,
            "method": api.method,
            "path": api.path,
            "description": api.description,
            "version": api.version,
            "rate_limit": api.rate_limit
        }
        for api in apis
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"apis": api_list, "total": len(api_list)}
    )

@router.get("/partner/apis/{api_code}", response_model=ApiResponse)
async def get_api_details(api_code: str, db: Session = Depends(get_db)):
    api = db.query(ApiEndpoint).filter(
        ApiEndpoint.api_code == api_code,
        ApiEndpoint.is_active == True
    ).first()
    
    if not api:
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_001")
        )
    
    return ApiResponse(
        code=200,
        message="Success",
        data={
            "api_code": api.api_code,
            "api_name": api.api_name,
            "category": api.category.value,
            "method": api.method,
            "path": api.path,
            "description": api.description,
            "parameters": api.parameters,
            "request_example": api.request_example,
            "response_example": api.response_example,
            "version": api.version,
            "rate_limit": api.rate_limit
        }
    )

@router.post("/partner/access/request", response_model=ApiResponse)
async def request_api_access(
    scope_request: AccessScopeRequest,
    app: Application = Depends(verify_app_credentials),
    db: Session = Depends(get_db)
):
    scopes = AccessScopeService.request_access(db, app.id, scope_request.api_codes)
    
    return ApiResponse(
        code=200,
        message="Access requested successfully",
        data={
            "requested_apis": len(scopes),
            "scopes": [
                {
                    "api_code": db.query(ApiEndpoint).get(s.api_endpoint_id).api_code,
                    "is_approved": s.is_approved
                }
                for s in scopes
            ]
        }
    )

@router.get("/partner/access/list", response_model=ApiResponse)
async def list_my_access(
    app: Application = Depends(verify_app_credentials),
    db: Session = Depends(get_db)
):
    scopes = AccessScopeService.get_application_scopes(db, app.id)
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"scopes": scopes}
    )

@router.get("/partner/quota", response_model=ApiResponse)
async def get_my_quota(
    app: Application = Depends(verify_app_credentials),
    db: Session = Depends(get_db)
):
    rate_limit_service = RateLimitService()
    remaining = rate_limit_service.get_remaining_quota(app.app_code, app.daily_quota)
    
    return ApiResponse(
        code=200,
        message="Success",
        data={
            "daily_quota": app.daily_quota,
            "remaining": remaining,
            "used": app.daily_quota - remaining
        }
    )

@router.get("/partner/calls/logs", response_model=ApiResponse)
async def get_my_call_logs(
    api_code: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    app: Application = Depends(verify_app_credentials),
    db: Session = Depends(get_db)
):
    skip, limit = ValidationService.validate_pagination(skip, limit)
    
    api_endpoint = None
    if api_code:
        api_endpoint = db.query(ApiEndpoint).filter(ApiEndpoint.api_code == api_code).first()
    
    logs = CallLogService.get_call_logs(
        db,
        application_id=app.id,
        api_endpoint_id=api_endpoint.id if api_endpoint else None,
        call_status=status,
        skip=skip,
        limit=limit
    )
    
    log_list = [
        {
            "request_id": log.request_id,
            "api_code": db.query(ApiEndpoint).get(log.api_endpoint_id).api_code if db.query(ApiEndpoint).get(log.api_endpoint_id) else None,
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "call_status": log.call_status.value,
            "error_code": log.error_code,
            "error_message": log.error_message,
            "duration_ms": log.duration_ms,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"logs": log_list, "total": len(log_list), "skip": skip, "limit": limit}
    )
