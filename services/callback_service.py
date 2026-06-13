from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import httpx
from models.database import Callback, Application
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
    async def send_callback(callback_id: int, db: Session) -> bool:
        callback = db.query(Callback).filter(Callback.id == callback_id).first()
        if not callback:
            return False
        
        if callback.status == CallbackStatus.CONFIRMED:
            return True
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    callback.callback_url,
                    json=callback.payload,
                    headers={"Content-Type": "application/json"}
                )
                
                callback.response_data = response.text
                callback.status = CallbackStatus.SENT if response.is_success else CallbackStatus.FAILED
                callback.sent_at = datetime.utcnow()
                
                if response.is_success:
                    return True
                else:
                    callback.retry_count += 1
                    if callback.retry_count < callback.max_retries:
                        callback.status = CallbackStatus.PENDING
                        callback.scheduled_at = datetime.utcnow() + timedelta(minutes=5 * callback.retry_count)
                    return False
                    
        except Exception as e:
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
    def replay_callback(db: Session, callback_id: int) -> Optional[Callback]:
        callback = db.query(Callback).filter(Callback.id == callback_id).first()
        if not callback:
            return None
        
        callback.status = CallbackStatus.PENDING
        callback.retry_count = 0
        callback.scheduled_at = datetime.utcnow()
        callback.error_message = None
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
