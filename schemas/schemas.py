from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class AppStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class ApiCategory(str, Enum):
    ORDER = "order"
    CUSTOMER = "customer"
    PRODUCT = "product"
    AFTER_SALE = "after_sale"

class CallStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"

class CallbackStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CONFIRMED = "confirmed"

class ApplicationCreate(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    contact_name: str = Field(..., min_length=1, max_length=50)
    contact_email: str = Field(..., regex=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    contact_phone: Optional[str] = Field(None, max_length=20)

class ApplicationUpdate(BaseModel):
    app_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    contact_name: Optional[str] = Field(None, max_length=50)
    contact_email: Optional[str] = Field(None, regex=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    contact_phone: Optional[str] = Field(None, max_length=20)
    daily_quota: Optional[int] = Field(None, gt=0)
    status: Optional[AppStatus] = None

class ApplicationResponse(BaseModel):
    id: int
    app_name: str
    app_code: str
    description: Optional[str]
    status: AppStatus
    daily_quota: int
    contact_name: str
    contact_email: str
    contact_phone: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ApiEndpointResponse(BaseModel):
    id: int
    api_code: str
    api_name: str
    category: ApiCategory
    method: str
    path: str
    description: Optional[str]
    parameters: Optional[Dict[str, Any]]
    request_example: Optional[str]
    response_example: Optional[str]
    rate_limit: int
    is_active: bool
    version: str

    class Config:
        from_attributes = True

class AccessScopeRequest(BaseModel):
    api_codes: List[str] = Field(..., min_items=1)

class AccessScopeResponse(BaseModel):
    id: int
    api_code: str
    api_name: str
    is_approved: bool
    approved_at: Optional[datetime]

    class Config:
        from_attributes = True

class CallLogResponse(BaseModel):
    id: int
    request_id: str
    api_endpoint_id: int
    method: str
    path: str
    status_code: Optional[int]
    call_status: CallStatus
    error_code: Optional[str]
    error_message: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class CallbackRequest(BaseModel):
    callback_url: str
    event_type: str
    payload: Dict[str, Any]

class CallbackResponse(BaseModel):
    id: int
    event_type: str
    status: CallbackStatus
    retry_count: int
    callback_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str
    category: Optional[str] = None
    priority: int = 0

class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    category: Optional[str]
    priority: int
    is_active: bool
    published_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class StatisticsResponse(BaseModel):
    application_id: int
    date: datetime
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    avg_duration_ms: float
    error_counts: Dict[str, int]

    class Config:
        from_attributes = True

class ApiResponse(BaseModel):
    code: int = 200
    message: str = "Success"
    data: Optional[Any] = None
    request_id: Optional[str] = None

class ErrorResponse(BaseModel):
    code: int
    message: str
    error_code: Optional[str] = None
    request_id: Optional[str] = None
    solution: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
