from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
import redis
import json
from models.database import Application, CallLog, DailyStatistics, ApiEndpoint, ErrorCode
from schemas.schemas import CallStatus

class RateLimitService:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

    def check_daily_quota(self, app_code: str, daily_quota: int) -> Tuple[bool, int, int]:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"quota:{app_code}:{today}"
        
        current_count = self.redis_client.get(key)
        current_count = int(current_count) if current_count else 0
        
        if current_count >= daily_quota:
            return False, current_count, daily_quota
        
        self.redis_client.incr(key)
        self.redis_client.expire(key, 86400)
        
        return True, current_count + 1, daily_quota

    def check_api_rate_limit(self, app_code: str, api_code: str, rate_limit: int) -> Tuple[bool, int]:
        minute_key = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        key = f"rate:{app_code}:{api_code}:{minute_key}"
        
        current_count = self.redis_client.get(key)
        current_count = int(current_count) if current_count else 0
        
        if current_count >= rate_limit:
            return False, rate_limit
        
        self.redis_client.incr(key)
        self.redis_client.expire(key, 120)
        
        return True, current_count + 1

    def get_remaining_quota(self, app_code: str, daily_quota: int) -> int:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"quota:{app_code}:{today}"
        
        current_count = self.redis_client.get(key)
        current_count = int(current_count) if current_count else 0
        
        return max(0, daily_quota - current_count)

class CallLogService:
    @staticmethod
    def create_call_log(
        db: Session,
        application_id: int,
        api_endpoint_id: int,
        request_id: str,
        method: str,
        path: str,
        request_body: Optional[str] = None,
        status_code: Optional[int] = None,
        call_status: CallStatus = CallStatus.SUCCESS,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> CallLog:
        log = CallLog(
            application_id=application_id,
            api_endpoint_id=api_endpoint_id,
            request_id=request_id,
            method=method,
            path=path,
            request_body=request_body,
            status_code=status_code,
            call_status=call_status,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def update_call_log(
        db: Session,
        request_id: str,
        response_body: Optional[str] = None,
        status_code: Optional[int] = None,
        call_status: Optional[CallStatus] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> Optional[CallLog]:
        log = db.query(CallLog).filter(CallLog.request_id == request_id).first()
        if not log:
            return None
        
        if response_body is not None:
            log.response_body = response_body
        if status_code is not None:
            log.status_code = status_code
        if call_status is not None:
            log.call_status = call_status
        if error_code is not None:
            log.error_code = error_code
        if error_message is not None:
            log.error_message = error_message
        if duration_ms is not None:
            log.duration_ms = duration_ms
        
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_call_logs(
        db: Session,
        application_id: Optional[int] = None,
        api_endpoint_id: Optional[int] = None,
        call_status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> list[CallLog]:
        query = db.query(CallLog)
        
        if application_id:
            query = query.filter(CallLog.application_id == application_id)
        if api_endpoint_id:
            query = query.filter(CallLog.api_endpoint_id == api_endpoint_id)
        if call_status:
            query = query.filter(CallLog.call_status == call_status)
        if start_date:
            query = query.filter(CallLog.created_at >= start_date)
        if end_date:
            query = query.filter(CallLog.created_at <= end_date)
        
        return query.order_by(CallLog.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_failed_calls(
        db: Session,
        application_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> list[CallLog]:
        query = db.query(CallLog).filter(CallLog.call_status == CallStatus.FAILED)
        
        if application_id:
            query = query.filter(CallLog.application_id == application_id)
        if start_date:
            query = query.filter(CallLog.created_at >= start_date)
        if end_date:
            query = query.filter(CallLog.created_at <= end_date)
        
        return query.order_by(CallLog.created_at.desc()).offset(skip).limit(limit).all()

class StatisticsService:
    @staticmethod
    def update_daily_statistics(db: Session, application_id: int, date: datetime = None):
        if date is None:
            date = datetime.utcnow()
        
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        stats = db.query(DailyStatistics).filter(
            DailyStatistics.application_id == application_id,
            DailyStatistics.date == start_of_day
        ).first()
        
        total_calls = db.query(func.count(CallLog.id)).filter(
            CallLog.application_id == application_id,
            CallLog.created_at >= start_of_day,
            CallLog.created_at < end_of_day
        ).scalar()
        
        successful_calls = db.query(func.count(CallLog.id)).filter(
            CallLog.application_id == application_id,
            CallLog.created_at >= start_of_day,
            CallLog.created_at < end_of_day,
            CallLog.call_status == CallStatus.SUCCESS
        ).scalar()
        
        failed_calls = db.query(func.count(CallLog.id)).filter(
            CallLog.application_id == application_id,
            CallLog.created_at >= start_of_day,
            CallLog.created_at < end_of_day,
            CallLog.call_status == CallStatus.FAILED
        ).scalar()
        
        total_duration = db.query(func.sum(CallLog.duration_ms)).filter(
            CallLog.application_id == application_id,
            CallLog.created_at >= start_of_day,
            CallLog.created_at < end_of_day,
            CallLog.duration_ms.isnot(None)
        ).scalar() or 0
        
        error_counts_raw = db.query(
            CallLog.error_code,
            func.count(CallLog.id)
        ).filter(
            CallLog.application_id == application_id,
            CallLog.created_at >= start_of_day,
            CallLog.created_at < end_of_day,
            CallLog.error_code.isnot(None)
        ).group_by(CallLog.error_code).all()
        
        error_counts = {error_code: count for error_code, count in error_counts_raw}
        
        if stats:
            stats.total_calls = total_calls
            stats.successful_calls = successful_calls
            stats.failed_calls = failed_calls
            stats.total_duration_ms = total_duration
            stats.error_counts = error_counts
        else:
            stats = DailyStatistics(
                application_id=application_id,
                date=start_of_day,
                total_calls=total_calls,
                successful_calls=successful_calls,
                failed_calls=failed_calls,
                total_duration_ms=total_duration,
                error_counts=error_counts
            )
            db.add(stats)
        
        db.commit()
        return stats

    @staticmethod
    def get_application_statistics(
        db: Session,
        application_id: int,
        start_date: datetime,
        end_date: datetime
    ) -> list[DailyStatistics]:
        return db.query(DailyStatistics).filter(
            DailyStatistics.application_id == application_id,
            DailyStatistics.date >= start_date,
            DailyStatistics.date <= end_date
        ).order_by(DailyStatistics.date.desc()).all()

    @staticmethod
    def get_all_applications_statistics(
        db: Session,
        start_date: datetime,
        end_date: datetime
    ) -> list[DailyStatistics]:
        return db.query(DailyStatistics).filter(
            DailyStatistics.date >= start_date,
            DailyStatistics.date <= end_date
        ).order_by(DailyStatistics.date.desc()).all()

    @staticmethod
    def get_high_frequency_errors(
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> list[Dict]:
        query = db.query(
            CallLog.error_code,
            CallLog.error_message,
            func.count(CallLog.id).label('count')
        ).filter(
            CallLog.error_code.isnot(None),
            CallLog.call_status == CallStatus.FAILED
        )
        
        if start_date:
            query = query.filter(CallLog.created_at >= start_date)
        if end_date:
            query = query.filter(CallLog.created_at <= end_date)
        
        results = query.group_by(
            CallLog.error_code,
            CallLog.error_message
        ).order_by(
            func.count(CallLog.id).desc()
        ).limit(limit).all()
        
        return [
            {
                "error_code": r.error_code,
                "error_message": r.error_message,
                "count": r.count
            }
            for r in results
        ]
