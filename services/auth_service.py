from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
import secrets
import hashlib
from sqlalchemy.orm import Session
from models.database import Application, AccessScope, ApiEndpoint
from schemas.schemas import ApplicationCreate, ApplicationUpdate

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    @staticmethod
    def generate_app_code() -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_part = secrets.token_hex(4)
        return f"APP{timestamp}{random_part}".upper()

    @staticmethod
    def generate_app_secret() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_secret(secret: str) -> str:
        return pwd_context.hash(secret)

    @staticmethod
    def verify_secret(plain_secret: str, hashed_secret: str) -> bool:
        return pwd_context.verify(plain_secret, hashed_secret)

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            return None

    @staticmethod
    def generate_signature(app_code: str, app_secret: str, timestamp: str, nonce: str) -> str:
        data = f"{app_code}{timestamp}{nonce}{app_secret}"
        return hashlib.sha256(data.encode()).hexdigest()

class ApplicationService:
    @staticmethod
    def create_application(db: Session, app_data: ApplicationCreate) -> Tuple[Application, str]:
        app_code = AuthService.generate_app_code()
        app_secret = AuthService.generate_app_secret()
        
        application = Application(
            app_name=app_data.app_name,
            app_code=app_code,
            app_secret=AuthService.hash_secret(app_secret),
            description=app_data.description,
            contact_name=app_data.contact_name,
            contact_email=app_data.contact_email,
            contact_phone=app_data.contact_phone,
            daily_quota=1000,
            status="active"
        )
        db.add(application)
        db.commit()
        db.refresh(application)
        
        return application, app_secret

    @staticmethod
    def get_application_by_code(db: Session, app_code: str) -> Optional[Application]:
        return db.query(Application).filter(Application.app_code == app_code).first()

    @staticmethod
    def get_application_by_id(db: Session, app_id: int) -> Optional[Application]:
        return db.query(Application).filter(Application.id == app_id).first()

    @staticmethod
    def update_application(db: Session, app_id: int, app_data: ApplicationUpdate) -> Optional[Application]:
        application = db.query(Application).filter(Application.id == app_id).first()
        if not application:
            return None
        
        update_data = app_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(application, key, value)
        
        db.commit()
        db.refresh(application)
        return application

    @staticmethod
    def update_application_status(db: Session, app_id: int, status: str) -> Optional[Application]:
        application = db.query(Application).filter(Application.id == app_id).first()
        if not application:
            return None
        application.status = status
        db.commit()
        db.refresh(application)
        return application

    @staticmethod
    def update_daily_quota(db: Session, app_id: int, quota: int) -> Optional[Application]:
        application = db.query(Application).filter(Application.id == app_id).first()
        if not application:
            return None
        application.daily_quota = quota
        db.commit()
        db.refresh(application)
        return application

    @staticmethod
    def regenerate_secret(db: Session, app_id: int) -> Tuple[Optional[Application], Optional[str]]:
        application = db.query(Application).filter(Application.id == app_id).first()
        if not application:
            return None, None
        
        new_secret = AuthService.generate_app_secret()
        application.app_secret = AuthService.hash_secret(new_secret)
        db.commit()
        db.refresh(application)
        
        return application, new_secret

    @staticmethod
    def list_applications(db: Session, skip: int = 0, limit: int = 20, status: Optional[str] = None):
        query = db.query(Application)
        if status:
            query = query.filter(Application.status == status)
        return query.offset(skip).limit(limit).all()

class AccessScopeService:
    @staticmethod
    def request_access(db: Session, application_id: int, api_codes: list[str]) -> list[AccessScope]:
        scopes_created = []
        for api_code in api_codes:
            api_endpoint = db.query(ApiEndpoint).filter(ApiEndpoint.api_code == api_code).first()
            if not api_endpoint:
                continue
            
            existing = db.query(AccessScope).filter(
                AccessScope.application_id == application_id,
                AccessScope.api_endpoint_id == api_endpoint.id
            ).first()
            
            if existing:
                continue
            
            scope = AccessScope(
                application_id=application_id,
                api_endpoint_id=api_endpoint.id,
                is_approved=False
            )
            db.add(scope)
            scopes_created.append(scope)
        
        db.commit()
        for scope in scopes_created:
            db.refresh(scope)
        
        return scopes_created

    @staticmethod
    def approve_access(db: Session, scope_id: int) -> Optional[AccessScope]:
        scope = db.query(AccessScope).filter(AccessScope.id == scope_id).first()
        if not scope:
            return None
        
        scope.is_approved = True
        scope.approved_at = datetime.utcnow()
        db.commit()
        db.refresh(scope)
        return scope

    @staticmethod
    def get_application_scopes(db: Session, application_id: int) -> list[dict]:
        scopes = db.query(AccessScope).filter(AccessScope.application_id == application_id).all()
        result = []
        for scope in scopes:
            api = db.query(ApiEndpoint).filter(ApiEndpoint.id == scope.api_endpoint_id).first()
            result.append({
                "id": scope.id,
                "api_code": api.api_code if api else None,
                "api_name": api.api_name if api else None,
                "is_approved": scope.is_approved,
                "approved_at": scope.approved_at
            })
        return result

    @staticmethod
    def check_access(db: Session, application_id: int, api_code: str) -> bool:
        api_endpoint = db.query(ApiEndpoint).filter(ApiEndpoint.api_code == api_code).first()
        if not api_endpoint:
            return False
        
        scope = db.query(AccessScope).filter(
            AccessScope.application_id == application_id,
            AccessScope.api_endpoint_id == api_endpoint.id,
            AccessScope.is_approved == True
        ).first()
        
        return scope is not None
