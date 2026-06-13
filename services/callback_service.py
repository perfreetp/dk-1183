from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import httpx
import hashlib
import time
from models.database import Callback, Application, CallbackSendAttempt
from schemas.schemas import CallbackStatus

class CallbackService:
    @staticmethod
    def create_callback(
        db: Session,
        application_id: int,
        event_type: str,
        payload: Dict[str, Any],
        callback_url: Optional[str] = None,
        scheduled_at: Optional[datetime] = None
    ) -> Callback:
        if not callback_url:
            app = db.query(Application).filter(Application.id == application_id).first()
            if app:
                callback_url = app.callback_url
        
        callback = Callback(
            application_id=application_id,
            event_type=event_type,
            payload=payload,
            callback_url=callback_url,
            status=CallbackStatus.PENDING,
            scheduled_at=scheduled_at or datetime.utcnow()
        )
        db.add(callback)
        db.commit()
        db.refresh(callback)
        return callback

    @staticmethod
    def generate_callback_signature(app_code: str, app_secret: str, timestamp: str, nonce: str) -> str:
        sign_str = f"{app_code}{timestamp}{nonce}{app_secret}"
        return hashlib.sha256(sign_str.encode()).hexdigest()

    @staticmethod
    async def send_callback(callback_id: int, db: Session) -> bool:
        callback = db.query(Callback).filter(Callback.id == callback_id).first()
        if not callback:
            return False
        
        if callback.status == CallbackStatus.CONFIRMED:
            return True
        
        if not callback.callback_url:
            attempt = CallbackSendAttempt(
                callback_id=callback.id,
                attempt_number=callback.retry_count + 1,
                status=CallbackStatus.FAILED,
                error_message="No callback URL configured for application",
                sign_version=callback.sign_version,
                sent_at=datetime.utcnow()
            )
            db.add(attempt)
            
            callback.status = CallbackStatus.FAILED
            callback.error_message = "No callback URL configured for application"
            callback.sent_at = datetime.utcnow()
            db.commit()
            return False
        
        app = db.query(Application).filter(Application.id == callback.application_id).first()
        if not app:
            attempt = CallbackSendAttempt(
                callback_id=callback.id,
                attempt_number=callback.retry_count + 1,
                status=CallbackStatus.FAILED,
                error_message="Application not found",
                sign_version=callback.sign_version,
                sent_at=datetime.utcnow()
            )
            db.add(attempt)
            
            callback.status = CallbackStatus.FAILED
            callback.error_message = "Application not found"
            callback.sent_at = datetime.utcnow()
            db.commit()
            return False
        
        start_time = time.time()
        timestamp = str(int(time.time()))
        nonce = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
        signature = CallbackService.generate_callback_signature(app.app_code, app.app_secret, timestamp, nonce)
        
        headers = {
            "Content-Type": "application/json",
            "X-App-Code": app.app_code,
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Sign-Version": "v1"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    callback.callback_url,
                    json=callback.payload,
                    headers=headers
                )
                
                duration_ms = int((time.time() - start_time) * 1000)
                http_status_code = response.status_code
                
                if response.is_success:
                    attempt_status = CallbackStatus.SENT
                    error_message = None
                else:
                    attempt_status = CallbackStatus.FAILED
                    error_message = f"HTTP {http_status_code}: {response.text[:500]}"
                
                attempt = CallbackSendAttempt(
                    callback_id=callback.id,
                    attempt_number=callback.retry_count + 1,
                    status=attempt_status,
                    http_status_code=http_status_code,
                    response_data=response.text[:2000] if response.text else None,
                    error_message=error_message,
                    sign_version="v1",
                    sent_at=datetime.utcnow(),
                    duration_ms=duration_ms
                )
                db.add(attempt)
                
                callback.response_data = response.text[:2000] if response.text else None
                callback.http_status_code = http_status_code
                callback.sent_at = datetime.utcnow()
                callback.sign_version = "v1"
                
                if response.is_success:
                    callback.status = CallbackStatus.SENT
                    return True
                else:
                    callback.error_message = error_message
                    callback.retry_count += 1
                    
                    if 500 <= http_status_code < 600:
                        if callback.retry_count < callback.max_retries:
                            callback.status = CallbackStatus.PENDING
                            callback.scheduled_at = datetime.utcnow() + timedelta(minutes=5 * callback.retry_count)
                        else:
                            callback.status = CallbackStatus.FAILED
                    else:
                        callback.status = CallbackStatus.FAILED
                    
                    return False
                    
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            attempt = CallbackSendAttempt(
                callback_id=callback.id,
                attempt_number=callback.retry_count + 1,
                status=CallbackStatus.FAILED,
                error_message=str(e),
                sign_version="v1",
                sent_at=datetime.utcnow(),
                duration_ms=duration_ms
            )
            db.add(attempt)
            
            callback.error_message = str(e)
            callback.retry_count += 1
            
            if callback.retry_count < callback.max_retries:
                callback.status = CallbackStatus.PENDING
                callback.scheduled_at = datetime.utcnow() + timedelta(minutes=5 * callback.retry_count)
            else:
                callback.status = CallbackStatus.FAILED
            
            return False
        finally:
            db.commit()

    @staticmethod
    def replay_callback(db: Session, callback_id: int, delay_minutes: int = 0) -> Optional[Callback]:
        callback = db.query(Callback).filter(Callback.id == callback_id).first()
        if not callback:
            return None
        
        callback.status = CallbackStatus.PENDING
        callback.retry_count = 0
        
        if delay_minutes > 0:
            callback.scheduled_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        else:
            callback.scheduled_at = datetime.utcnow()
        
        callback.error_message = None
        callback.response_data = None
        callback.http_status_code = None
        db.commit()
        db.refresh(callback)
        return callback

    @staticmethod
    def confirm_callback(db: Session, callback_id: int) -> Optional[Callback]:
        callback = db.query(Callback).filter(Callback.id == callback_id).first()
        if not callback:
            return None
        
        callback.status = CallbackStatus.CONFIRMED
        db.commit()
        db.refresh(callback)
        return callback

    @staticmethod
    def get_pending_callbacks(db: Session, limit: int = 100) -> List[Callback]:
        now = datetime.utcnow()
        return db.query(Callback).filter(
            Callback.status == CallbackStatus.PENDING,
            Callback.scheduled_at <= now
        ).limit(limit).all()

    @staticmethod
    def get_callbacks_by_application(
        db: Session,
        application_id: int,
        status: Optional[CallbackStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Callback]:
        query = db.query(Callback).filter(Callback.application_id == application_id)
        if status:
            query = query.filter(Callback.status == status)
        return query.order_by(Callback.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_failed_callbacks(db: Session, skip: int = 0, limit: int = 100) -> List[Callback]:
        return db.query(Callback).filter(
            Callback.status == CallbackStatus.FAILED
        ).order_by(Callback.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_callback_with_attempts(db: Session, callback_id: int) -> Optional[Callback]:
        callback = db.query(Callback).filter(Callback.id == callback_id).first()
        if callback:
            db.refresh(callback, attribute_names=['send_attempts'])
        return callback

    @staticmethod
    def get_send_attempts(db: Session, callback_id: int) -> List[CallbackSendAttempt]:
        return db.query(CallbackSendAttempt).filter(
            CallbackSendAttempt.callback_id == callback_id
        ).order_by(CallbackSendAttempt.attempt_number).all()