from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid
import time

from config.database import get_db
from schemas.schemas import ApiResponse, CallStatus
from services.auth_service import ApplicationService, AccessScopeService, AuthService
from services.rate_limit_service import RateLimitService, CallLogService
from services.error_service import ErrorService, ValidationService
from services.callback_service import CallbackService
from services.business_service import BusinessDataService
from models.database import Application, ApiEndpoint
from schemas.schemas import AppStatus

router = APIRouter(prefix="/api/v1/business", tags=["业务接口"])

class AfterSaleCreateRequest(BaseModel):
    order_id: Optional[str] = None
    type: Optional[str] = None
    reason: Optional[str] = None

class OrderStatusUpdateRequest(BaseModel):
    order_id: Optional[str] = None
    new_status: Optional[str] = None

async def verify_business_access(
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
) -> Application:
    if authorization:
        try:
            scheme, token = authorization.split()
        except ValueError:
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001", None, "Invalid authorization header format")
            )
        
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001", None, "Invalid authorization scheme")
            )
        
        payload = AuthService.verify_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_002")
            )
        
        app_code = payload.get("sub")
        application = ApplicationService.get_application_by_code(db, app_code)
    
    elif all([app_code, app_secret, signature, timestamp, nonce]):
        application = ApplicationService.get_application_by_code(db, app_code)
        if not application:
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001", None, "Invalid app_code")
            )
        
        if not AuthService.verify_secret(app_secret, application.app_secret):
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_001", None, "Invalid app_secret")
            )
        
        expected_signature = AuthService.generate_signature(
            app_code, app_secret, timestamp, nonce
        )
        if signature != expected_signature:
            raise HTTPException(
                status_code=401,
                detail=ErrorService.create_error_response("AUTH_003", None, "Signature verification failed")
            )
    
    else:
        raise HTTPException(
            status_code=401,
            detail=ErrorService.create_error_response("AUTH_001", None, "Missing authentication headers")
        )
    
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
    
    return application

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
    
    return f"{app.app_code}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

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
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app = await verify_business_access(authorization, app_code, app_secret, signature, timestamp, nonce, db)
    
    request_id = await check_rate_limit(app, "ORDER_QUERY", db)
    
    if not ValidationService.validate_order_id(order_id):
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 1, request_id, request, CallStatus.FAILED, 400, "VALIDATION_001", "Invalid order ID", duration_ms)
        raise HTTPException(
            status_code=400,
            detail=ErrorService.create_error_response("VALIDATION_001", request_id, "Invalid order ID")
        )
    
    order = BusinessDataService.get_order(db, order_id)
    
    if not order:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 1, request_id, request, CallStatus.FAILED, 404, "RESOURCE_002", "Order not found", duration_ms)
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_002", request_id, f"Order {order_id} not found")
        )
    
    order_data = {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total_amount": order.total_amount / 100,
        "items": order.items or [],
        "created_at": order.created_at.isoformat() + "Z",
        "updated_at": order.updated_at.isoformat() + "Z"
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
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app = await verify_business_access(authorization, app_code, app_secret, signature, timestamp, nonce, db)
    
    request_id = await check_rate_limit(app, "CUSTOMER_QUERY", db)
    
    if not ValidationService.validate_customer_id(customer_id):
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 2, request_id, request, CallStatus.FAILED, 400, "VALIDATION_001", "Invalid customer ID", duration_ms)
        raise HTTPException(
            status_code=400,
            detail=ErrorService.create_error_response("VALIDATION_001", request_id, "Invalid customer ID")
        )
    
    customer = BusinessDataService.get_customer(db, customer_id)
    
    if not customer:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 2, request_id, request, CallStatus.FAILED, 404, "RESOURCE_003", "Customer not found", duration_ms)
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_003", request_id, f"Customer {customer_id} not found")
        )
    
    customer_data = {
        "customer_id": customer.customer_id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "level": customer.level,
        "total_orders": customer.total_orders,
        "total_amount": customer.total_amount / 100,
        "created_at": customer.created_at.isoformat() + "Z"
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
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app = await verify_business_access(authorization, app_code, app_secret, signature, timestamp, nonce, db)
    
    request_id = await check_rate_limit(app, "PRODUCT_QUERY", db)
    
    product = BusinessDataService.get_product(db, product_id)
    
    if not product:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 3, request_id, request, CallStatus.FAILED, 404, "RESOURCE_001", "Product not found", duration_ms)
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_001", request_id, f"Product {product_id} not found")
        )
    
    product_data = {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "price": product.price / 100,
        "stock": product.stock,
        "status": product.status,
        "description": product.description
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
    aftersale_req: AfterSaleCreateRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app = await verify_business_access(authorization, app_code, app_secret, signature, timestamp, nonce, db)
    
    request_id = await check_rate_limit(app, "AFTERSALE_CREATE", db)
    
    validation_result = BusinessDataService.validate_aftersale_params(
        aftersale_req.order_id, aftersale_req.type, aftersale_req.reason
    )
    
    if not validation_result["valid"]:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 4, request_id, request, CallStatus.FAILED, 400, "VALIDATION_001", 
                     str(validation_result["errors"]), duration_ms)
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": "参数校验失败",
                "error_code": "VALIDATION_001",
                "request_id": request_id,
                "errors": validation_result["errors"]
            }
        )
    
    order = BusinessDataService.get_order(db, aftersale_req.order_id)
    if not order:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 4, request_id, request, CallStatus.FAILED, 404, "RESOURCE_002", 
                     f"Order {aftersale_req.order_id} not found", duration_ms)
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_002", request_id, 
                                                      f"Order {aftersale_req.order_id} not found")
        )
    
    aftersale = BusinessDataService.create_aftersale(
        db, aftersale_req.order_id, aftersale_req.type, aftersale_req.reason
    )
    
    result = {
        "aftersale_id": aftersale.aftersale_id,
        "order_id": aftersale.order_id,
        "type": aftersale.type,
        "reason": aftersale.reason,
        "status": aftersale.status,
        "created_at": aftersale.created_at.isoformat() + "Z",
        "request_id": request_id
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
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app = await verify_business_access(authorization, app_code, app_secret, signature, timestamp, nonce, db)
    
    request_id = await check_rate_limit(app, "AFTERSALE_QUERY", db)
    
    aftersale = BusinessDataService.get_aftersale(db, aftersale_id)
    
    if not aftersale:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 4, request_id, request, CallStatus.FAILED, 404, "RESOURCE_001", 
                     "After-sale not found", duration_ms)
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_001", request_id, 
                                                      f"After-sale {aftersale_id} not found")
        )
    
    aftersale_data = {
        "aftersale_id": aftersale.aftersale_id,
        "order_id": aftersale.order_id,
        "type": aftersale.type,
        "reason": aftersale.reason,
        "status": aftersale.status,
        "created_at": aftersale.created_at.isoformat() + "Z",
        "updated_at": aftersale.updated_at.isoformat() + "Z"
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
    status_req: OrderStatusUpdateRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    app_code: Optional[str] = Header(None, alias="X-App-Code"),
    app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
    signature: Optional[str] = Header(None, alias="X-Signature"),
    timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    nonce: Optional[str] = Header(None, alias="X-Nonce"),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    app = await verify_business_access(authorization, app_code, app_secret, signature, timestamp, nonce, db)
    
    request_id = await check_rate_limit(app, "ORDER_STATUS_UPDATE", db)
    
    validation_result = BusinessDataService.validate_order_status(status_req.new_status)
    
    if not validation_result["valid"]:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 1, request_id, request, CallStatus.FAILED, 400, "VALIDATION_001", 
                     str(validation_result["errors"]), duration_ms)
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": "参数校验失败",
                "error_code": "VALIDATION_001",
                "request_id": request_id,
                "errors": validation_result["errors"]
            }
        )
    
    order = BusinessDataService.get_order(db, status_req.order_id)
    if not order:
        duration_ms = int((time.time() - start_time) * 1000)
        log_api_call(db, app, 1, request_id, request, CallStatus.FAILED, 404, "RESOURCE_002", 
                     f"Order {status_req.order_id} not found", duration_ms)
        raise HTTPException(
            status_code=404,
            detail=ErrorService.create_error_response("RESOURCE_002", request_id, 
                                                      f"Order {status_req.order_id} not found")
        )
    
    previous_status = order.status
    updated_order = BusinessDataService.update_order_status(db, status_req.order_id, status_req.new_status)
    
    callback = CallbackService.create_callback(
        db=db,
        application_id=app.id,
        event_type="order_status_updated",
        payload={
            "order_id": status_req.order_id,
            "previous_status": previous_status,
            "new_status": status_req.new_status,
            "updated_at": updated_order.updated_at.isoformat() + "Z",
            "request_id": request_id
        },
        callback_url=app.callback_url
    )
    
    result = {
        "order_id": status_req.order_id,
        "previous_status": previous_status,
        "new_status": status_req.new_status,
        "updated_at": updated_order.updated_at.isoformat() + "Z",
        "callback_id": callback.id,
        "request_id": request_id,
        "callback_url_configured": app.callback_url is not None
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