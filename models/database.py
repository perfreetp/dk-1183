from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from config.database import Base

class AppStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class ApiCategory(str, enum.Enum):
    ORDER = "order"
    CUSTOMER = "customer"
    PRODUCT = "product"
    AFTER_SALE = "after_sale"

class CallStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"

class CallbackStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CONFIRMED = "confirmed"

class Application(Base):
    __tablename__ = "applications"
    
    id = Column(Integer, primary_key=True, index=True)
    app_name = Column(String(100), nullable=False)
    app_code = Column(String(50), unique=True, nullable=False, index=True)
    app_secret = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(Enum(AppStatus), default=AppStatus.ACTIVE)
    daily_quota = Column(Integer, default=1000)
    contact_name = Column(String(50))
    contact_email = Column(String(100))
    contact_phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    api_credentials = relationship("ApiCredential", back_populates="application")
    access_scopes = relationship("AccessScope", back_populates="application")
    call_logs = relationship("CallLog", back_populates="application")

class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"
    
    id = Column(Integer, primary_key=True, index=True)
    api_code = Column(String(50), unique=True, nullable=False, index=True)
    api_name = Column(String(100), nullable=False)
    category = Column(Enum(ApiCategory), nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(String(200), nullable=False)
    description = Column(Text)
    parameters = Column(JSON)
    request_example = Column(Text)
    response_example = Column(Text)
    rate_limit = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    version = Column(String(20), default="1.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    access_scopes = relationship("AccessScope", back_populates="api_endpoint")

class AccessScope(Base):
    __tablename__ = "access_scopes"
    
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    api_endpoint_id = Column(Integer, ForeignKey("api_endpoints.id"), nullable=False)
    is_approved = Column(Boolean, default=False)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="access_scopes")
    api_endpoint = relationship("ApiEndpoint", back_populates="access_scopes")

class CallLog(Base):
    __tablename__ = "call_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    api_endpoint_id = Column(Integer, ForeignKey("api_endpoints.id"), nullable=False)
    request_id = Column(String(50), unique=True, nullable=False, index=True)
    method = Column(String(10))
    path = Column(String(200))
    request_body = Column(Text)
    response_body = Column(Text)
    status_code = Column(Integer)
    call_status = Column(Enum(CallStatus), nullable=False)
    error_code = Column(String(50))
    error_message = Column(Text)
    duration_ms = Column(Integer)
    ip_address = Column(String(50))
    user_agent = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    application = relationship("Application", back_populates="call_logs")

    __table_args__ = (
        Index('idx_app_created', 'application_id', 'created_at'),
        Index('idx_api_created', 'api_endpoint_id', 'created_at'),
    )

class ErrorCode(Base):
    __tablename__ = "error_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    message = Column(String(255), nullable=False)
    http_status = Column(Integer, default=400)
    solution = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Callback(Base):
    __tablename__ = "callbacks"
    
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(CallbackStatus), default=CallbackStatus.PENDING)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    callback_url = Column(String(255))
    response_data = Column(Text)
    error_message = Column(Text)
    scheduled_at = Column(DateTime)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_status_scheduled', 'status', 'scheduled_at'),
    )

class Announcement(Base):
    __tablename__ = "announcements"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50))
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DailyStatistics(Base):
    __tablename__ = "daily_statistics"
    
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    total_calls = Column(Integer, default=0)
    successful_calls = Column(Integer, default=0)
    failed_calls = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    error_counts = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_app_date', 'application_id', 'date'),
    )
