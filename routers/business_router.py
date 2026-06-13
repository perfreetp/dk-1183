from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import uuid
import time

from config.database import get_db
from schemas.schemas import ApiResponse, CallStatus
from services.auth_service import ApplicationService, AccessScopeService
from services.rate_limit_service import RateLimitService, CallLogService, StatisticsService
from services.error_service import ErrorService, ValidationService
from models.database import Application, ApiEndpoint, CallLog
from schemas.schemas import AppStatus

router = APIRouter(prefix="/api/v1/business", tags=["业务接口"])

async def verify_business_access(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> tuple[Application, str]:
    from services.auth_service import AuthService
    
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
    
    if application.status != AppStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("AUTH_004" if application.status == AppStatus.SUSPENDED else "AUTH_005")
        )
    
    return application, payload.get("sub")

async def check_rate_limit(
    app: Application,
    api_code: str,
    db: Session
) -> str:
    rate_limit_service = RateLimitService()
    
    allowed, current, quota = rate_limit_service.check_daily_quota(
        app.app_code, app.daily_quota
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=ErrorService.create_error_response("RATE_001")
        )
    
    api = db.query(ApiEndpoint).filter(ApiEndpoint.api_code == api_code).first()
    if api:
        allowed, current = rate_limit_service.check_api_rate_limit(
            app.app_code, api_code, api.rate_limit
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=ErrorService.create_error_response("RATE_002")
            )
    
    return f"{app.app_code}-{int(time.time() * 1000)}"

def log_api_call(
    db: Session,
    app: Application,
    api_endpoint_id: int,
    request_id: str,
    request: Request,
    call_status: CallStatus = CallStatus.SUCCESS,
    status_code: int = 200,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None
):
    CallLogService.create_call_log(
        db=db,
        application_id=app.id,
        api_endpoint_id=api_endpoint_id,
        request_id=request_id,
        method=request.method,
        path=str(request.url.path),
        status_code=status_code,
        call_status=call_status,
        error_code=error_code,
        error_message=error_message,
        duration_ms=duration_ms,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

@router.get("/order/query")
async def query_order(
    order_id: str,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app, app_code = await verify_business_access(authorization, db)
    
    has_access = AccessScopeService.check_access(db, app.id, "ORDER_QUERY")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("ACCESS_001")
        )
    
    request_id = await check_rate_limit(app, "ORDER_QUERY", db)
    
    if not ValidationService.validate_order_id(order_id):
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 1, request_id, request, CallStatus.FAILED, 400, "VALIDATION_001", "Invalid order ID", duration_ms)
        raise HTTPException(
            status_code=400,
            detail=ErrorService.create_error_response("VALIDATION_001", request_id, "Invalid order ID")
        )
    
    order_data = {
        "order_id": order_id,
        "customer_id": "CUST001",
        "status": "completed",
        "total_amount": 299.99,
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T14:20:00Z",
        "items": [
            {"product_id": "P001", "name": "Product A", "quantity": 2, "price": 99.99},
            {"product_id": "P002", "name": "Product B", "quantity": 1, "price": 100.01}
        ]
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_api_call(db, app, 1, request_id, request, CallStatus.SUCCESS, 200, None, None, duration_ms)
    
    return ApiResponse(
        code=200,
        message="Success",
        data=order_data,
        request_id=request_id
    )

@router.get("/customer/query")
async def query_customer(
    customer_id: str,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app, app_code = await verify_business_access(authorization, db)
    
    has_access = AccessScopeService.check_access(db, app.id, "CUSTOMER_QUERY")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("ACCESS_001")
        )
    
    request_id = await check_rate_limit(app, "CUSTOMER_QUERY", db)
    
    if not ValidationService.validate_customer_id(customer_id):
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 2, request_id, request, CallStatus.FAILED, 400, "VALIDATION_001", "Invalid customer ID", duration_ms)
        raise HTTPException(
            status_code=400,
            detail=ErrorService.create_error_response("VALIDATION_001", request_id, "Invalid customer ID")
        )
    
    customer_data = {
        "customer_id": customer_id,
        "name": "张三",
        "email": "zhangsan@example.com",
        "phone": "138****8888",
        "level": "VIP",
        "total_orders": 50,
        "total_amount": 15000.00,
        "created_at": "2020-01-01T00:00:00Z"
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_api_call(db, app, 2, request_id, request, CallStatus.SUCCESS, 200, None, None, duration_ms)
    
    return ApiResponse(
        code=200,
        message="Success",
        data=customer_data,
        request_id=request_id
    )

@router.get("/product/query")
async def query_product(
    product_id: str,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app, app_code = await verify_business_access(authorization, db)
    
    has_access = AccessScopeService.check_access(db, app.id, "PRODUCT_QUERY")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("ACCESS_001")
        )
    
    request_id = await check_rate_limit(app, "PRODUCT_QUERY", db)
    
    product_data = {
        "product_id": product_id,
        "name": "Product Name",
        "category": "Electronics",
        "price": 199.99,
        "stock": 100,
        "status": "available",
        "description": "Product description here"
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_api_call(db, app, 3, request_id, request, CallStatus.SUCCESS, 200, None, None, duration_ms)
    
    return ApiResponse(
        code=200,
        message="Success",
        data=product_data,
        request_id=request_id
    )

@router.post("/aftersale/create")
async def create_aftersale(
    aftersale_data: dict,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app, app_code = await verify_business_access(authorization, db)
    
    has_access = AccessScopeService.check_access(db, app.id, "AFTERSALE_CREATE")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("ACCESS_001")
        )
    
    request_id = await check_rate_limit(app, "AFTERSALE_CREATE", db)
    
    aftersale_id = f"AS{int(time.time() * 1000)}"
    
    result = {
        "aftersale_id": aftersale_id,
        "order_id": aftersale_data.get("order_id"),
        "type": aftersale_data.get("type", "refund"),
        "status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_api_call(db, app, 4, request_id, request, CallStatus.SUCCESS, 200, None, None, duration_ms)
    
    return ApiResponse(
        code=200,
        message="After-sale created successfully",
        data=result,
        request_id=request_id
    )

@router.get("/aftersale/query")
async def query_aftersale(
    aftersale_id: str,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app, app_code = await verify_business_access(authorization, db)
    
    has_access = AccessScopeService.check_access(db, app.id, "AFTERSALE_QUERY")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("ACCESS_001")
        )
    
    request_id = await check_rate_limit(app, "AFTERSALE_QUERY", db)
    
    aftersale_data = {
        "aftersale_id": aftersale_id,
        "order_id": "ORD001",
        "type": "refund",
        "reason": "Product damaged",
        "status": "processing",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T12:00:00Z"
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_api_call(db, app, 4, request_id, request, CallStatus.SUCCESS, 200, None, None, duration_ms)
    
    return ApiResponse(
        code=200,
        message="Success",
        data=aftersale_data,
        request_id=request_id
    )

@router.post("/order/status/update")
async def update_order_status(
    order_id: str,
    new_status: str,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app, app_code = await verify_business_access(authorization, db)
    
    has_access = AccessScopeService.check_access(db, app.id, "ORDER_STATUS_UPDATE")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail=ErrorService.create_error_response("ACCESS_001")
        )
    
    request_id = await check_rate_limit(app, "ORDER_STATUS_UPDATE", db)
    
    result = {
        "order_id": order_id,
        "previous_status": "pending",
        "new_status": new_status,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_api_call(db, app, 1, request_id, request, CallStatus.SUCCESS, 200, None, None, duration_ms)
    
    return ApiResponse(
        code=200,
        message="Order status updated successfully",
        data=result,
        request_id=request_id
    )

@router.post("/callback/confirm")
async def confirm_callback(
    callback_id: int,
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    app, app_code = await verify_business_access(authorization, db)
    
    from services.callback_service import CallbackService
    callback = CallbackService.confirm_callback(db, callback_id)
    
    if not callback:
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_001", None, "Callback not found")
        )
    
    return ApiResponse(
        code=200,
        message="Callback confirmed",
        data={"callback_id": callback_id}
    )
