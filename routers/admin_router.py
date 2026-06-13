from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from config.database import get_db
from schemas.schemas import (
    ApplicationResponse, ApiEndpointResponse, AnnouncementCreate, AnnouncementResponse,
    ApiResponse, StatisticsResponse, CallStatus
)
from services.auth_service import ApplicationService, AccessScopeService
from services.rate_limit_service import CallLogService, StatisticsService
from services.error_service import ErrorService, ValidationService
from services.callback_service import CallbackService
from models.database import Application, ApiEndpoint, AccessScope, Announcement

router = APIRouter(prefix="/api/v1/admin", tags=["管理端"])

ADMIN_TOKEN = "admin-secret-token-change-in-production"

def verify_admin(request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/applications", response_model=ApiResponse)
async def list_applications(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    applications = ApplicationService.list_applications(db, skip, limit, status)
    
    app_list = [
        {
            "id": app.id,
            "app_name": app.app_name,
            "app_code": app.app_code,
            "description": app.description,
            "status": app.status.value,
            "daily_quota": app.daily_quota,
            "contact_name": app.contact_name,
            "contact_email": app.contact_email,
            "created_at": app.created_at.isoformat()
        }
        for app in applications
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"applications": app_list, "total": len(app_list)}
    )

@router.post("/applications/{app_id}/suspend", response_model=ApiResponse)
async def suspend_application(
    app_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    application = ApplicationService.update_application_status(db, app_id, "suspended")
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return ApiResponse(
        code=200,
        message="Application suspended",
        data={"app_id": app_id, "status": "suspended"}
    )

@router.post("/applications/{app_id}/activate", response_model=ApiResponse)
async def activate_application(
    app_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    application = ApplicationService.update_application_status(db, app_id, "active")
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return ApiResponse(
        code=200,
        message="Application activated",
        data={"app_id": app_id, "status": "active"}
    )

@router.put("/applications/{app_id}/quota", response_model=ApiResponse)
async def update_quota(
    app_id: int,
    quota: int = Query(..., gt=0),
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    application = ApplicationService.update_daily_quota(db, app_id, quota)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return ApiResponse(
        code=200,
        message="Quota updated",
        data={"app_id": app_id, "daily_quota": quota}
    )

@router.post("/applications/{app_id}/regenerate-secret", response_model=ApiResponse)
async def regenerate_secret(
    app_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    application, new_secret = ApplicationService.regenerate_secret(db, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return ApiResponse(
        code=200,
        message="Secret regenerated",
        data={"app_id": app_id, "app_secret": new_secret}
    )

@router.get("/applications/{app_id}/statistics", response_model=ApiResponse)
async def get_application_statistics(
    app_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.utcnow() - timedelta(days=7)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.utcnow()
    
    stats = StatisticsService.get_application_statistics(db, app_id, start, end)
    
    stats_list = [
        {
            "date": s.date.isoformat(),
            "total_calls": s.total_calls,
            "successful_calls": s.successful_calls,
            "failed_calls": s.failed_calls,
            "success_rate": round(s.successful_calls / s.total_calls * 100, 2) if s.total_calls > 0 else 0,
            "avg_duration_ms": s.total_duration_ms // s.total_calls if s.total_calls > 0 else 0,
            "error_counts": s.error_counts or {}
        }
        for s in stats
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"statistics": stats_list}
    )

@router.get("/access-requests", response_model=ApiResponse)
async def list_access_requests(
    is_approved: Optional[bool] = None,
    skip: int = 0,
    limit: int = 20,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    query = db.query(AccessScope)
    if is_approved is not None:
        query = query.filter(AccessScope.is_approved == is_approved)
    
    scopes = query.offset(skip).limit(limit).all()
    
    requests_list = []
    for scope in scopes:
        app = db.query(Application).filter(Application.id == scope.application_id).first()
        api = db.query(ApiEndpoint).filter(ApiEndpoint.id == scope.api_endpoint_id).first()
        
        requests_list.append({
            "scope_id": scope.id,
            "app_code": app.app_code if app else None,
            "app_name": app.app_name if app else None,
            "api_code": api.api_code if api else None,
            "api_name": api.api_name if api else None,
            "is_approved": scope.is_approved,
            "approved_at": scope.approved_at.isoformat() if scope.approved_at else None,
            "created_at": scope.created_at.isoformat()
        })
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"requests": requests_list, "total": len(requests_list)}
    )

@router.post("/access-requests/{scope_id}/approve", response_model=ApiResponse)
async def approve_access_request(
    scope_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    scope = AccessScopeService.approve_access(db, scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Access request not found")
    
    return ApiResponse(
        code=200,
        message="Access approved",
        data={"scope_id": scope_id, "is_approved": True}
    )

@router.get("/logs/failed", response_model=ApiResponse)
async def list_failed_logs(
    application_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    
    logs = CallLogService.get_failed_calls(db, application_id, start, end, skip, limit)
    
    log_list = [
        {
            "request_id": log.request_id,
            "application_id": log.application_id,
            "api_endpoint_id": log.api_endpoint_id,
            "error_code": log.error_code,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"logs": log_list, "total": len(log_list)}
    )

@router.get("/callbacks/failed", response_model=ApiResponse)
async def list_failed_callbacks(
    skip: int = 0,
    limit: int = 100,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    callbacks = CallbackService.get_failed_callbacks(db, skip, limit)
    
    callback_list = [
        {
            "id": cb.id,
            "application_id": cb.application_id,
            "event_type": cb.event_type,
            "retry_count": cb.retry_count,
            "max_retries": cb.max_retries,
            "error_message": cb.error_message,
            "created_at": cb.created_at.isoformat()
        }
        for cb in callbacks
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"callbacks": callback_list, "total": len(callback_list)}
    )

class ReplayCallbackRequest(BaseModel):
    delay_minutes: int = Field(0, ge=0, description="延迟重放分钟数，0表示立即重放")

@router.post("/callbacks/{callback_id}/replay", response_model=ApiResponse)
async def replay_callback(
    callback_id: int,
    replay_request: ReplayCallbackRequest = ReplayCallbackRequest(),
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    callback = CallbackService.replay_callback(db, callback_id, replay_request.delay_minutes)
    if not callback:
        raise HTTPException(status_code=404, detail="Callback not found")
    
    result = {
        "callback_id": callback_id,
        "status": callback.status.value,
        "retry_count": callback.retry_count,
        "scheduled_at": callback.scheduled_at.isoformat(),
        "delay_minutes": replay_request.delay_minutes
    }
    
    if replay_request.delay_minutes == 0:
        success = await CallbackService.send_callback(callback_id, db)
        db.refresh(callback)
        
        attempts = CallbackService.get_send_attempts(db, callback_id)
        last_attempt = attempts[-1] if attempts else None
        
        result.update({
            "sent_at": callback.sent_at.isoformat() if callback.sent_at else None,
            "response_data": callback.response_data,
            "error_message": callback.error_message,
            "http_status_code": callback.http_status_code,
            "success": success,
            "sign_version": callback.sign_version,
            "last_attempt": {
                "attempt_number": last_attempt.attempt_number,
                "status": last_attempt.status.value,
                "http_status_code": last_attempt.http_status_code,
                "response_data": last_attempt.response_data,
                "error_message": last_attempt.error_message,
                "sent_at": last_attempt.sent_at.isoformat(),
                "duration_ms": last_attempt.duration_ms,
                "sign_version": last_attempt.sign_version
            } if last_attempt else None
        })
    
    return ApiResponse(
        code=200,
        message="Callback replay " + ("executed" if replay_request.delay_minutes == 0 else "scheduled"),
        data=result
    )

@router.get("/callbacks/{callback_id}", response_model=ApiResponse)
async def get_callback_detail(
    callback_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    from models.database import Callback
    callback = db.query(Callback).filter(Callback.id == callback_id).first()
    if not callback:
        raise HTTPException(status_code=404, detail="Callback not found")
    
    app = db.query(Application).filter(Application.id == callback.application_id).first()
    
    attempts = CallbackService.get_send_attempts(db, callback_id)
    attempts_list = [
        {
            "id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "status": attempt.status.value,
            "http_status_code": attempt.http_status_code,
            "response_data": attempt.response_data,
            "error_message": attempt.error_message,
            "sign_version": attempt.sign_version,
            "sent_at": attempt.sent_at.isoformat(),
            "duration_ms": attempt.duration_ms
        }
        for attempt in attempts
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={
            "id": callback.id,
            "application_id": callback.application_id,
            "app_code": app.app_code if app else None,
            "app_name": app.app_name if app else None,
            "event_type": callback.event_type,
            "payload": callback.payload,
            "status": callback.status.value,
            "callback_url": callback.callback_url,
            "retry_count": callback.retry_count,
            "max_retries": callback.max_retries,
            "scheduled_at": callback.scheduled_at.isoformat() if callback.scheduled_at else None,
            "sent_at": callback.sent_at.isoformat() if callback.sent_at else None,
            "response_data": callback.response_data,
            "http_status_code": callback.http_status_code,
            "error_message": callback.error_message,
            "sign_version": callback.sign_version,
            "created_at": callback.created_at.isoformat(),
            "updated_at": callback.updated_at.isoformat(),
            "send_attempts": attempts_list
        }
    )

@router.post("/announcements", response_model=ApiResponse)
async def create_announcement(
    announcement: AnnouncementCreate,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    new_announcement = Announcement(
        title=announcement.title,
        content=announcement.content,
        category=announcement.category,
        priority=announcement.priority,
        is_active=True,
        published_at=datetime.utcnow()
    )
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)
    
    return ApiResponse(
        code=200,
        message="Announcement created",
        data={"id": new_announcement.id}
    )

@router.get("/announcements", response_model=ApiResponse)
async def list_announcements(
    is_active: Optional[bool] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    query = db.query(Announcement)
    if is_active is not None:
        query = query.filter(Announcement.is_active == is_active)
    
    announcements = query.order_by(Announcement.priority.desc(), Announcement.created_at.desc()).all()
    
    announcement_list = [
        {
            "id": a.id,
            "title": a.title,
            "content": a.content,
            "category": a.category,
            "priority": a.priority,
            "is_active": a.is_active,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "created_at": a.created_at.isoformat()
        }
        for a in announcements
    ]
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"announcements": announcement_list}
    )

@router.get("/statistics/overview", response_model=ApiResponse)
async def get_overview_statistics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.utcnow() - timedelta(days=7)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.utcnow()
    
    stats = StatisticsService.get_all_applications_statistics(db, start, end)
    
    total_calls = sum(s.total_calls for s in stats)
    total_success = sum(s.successful_calls for s in stats)
    total_failed = sum(s.failed_calls for s in stats)
    
    high_freq_errors = StatisticsService.get_high_frequency_errors(db, start, end)
    
    return ApiResponse(
        code=200,
        message="Success",
        data={
            "total_calls": total_calls,
            "successful_calls": total_success,
            "failed_calls": total_failed,
            "success_rate": round(total_success / total_calls * 100, 2) if total_calls > 0 else 0,
            "high_frequency_errors": high_freq_errors,
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            }
        }
    )

@router.get("/statistics/by-partner", response_model=ApiResponse)
async def get_statistics_by_partner(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    request: Request = None,
    db: Session = Depends(get_db)
):
    verify_admin(request)
    
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.utcnow() - timedelta(days=7)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.utcnow()
    
    stats = StatisticsService.get_all_applications_statistics(db, start, end)
    
    partner_stats = {}
    for s in stats:
        if s.application_id not in partner_stats:
            app = db.query(Application).filter(Application.id == s.application_id).first()
            partner_stats[s.application_id] = {
                "application_id": s.application_id,
                "app_code": app.app_code if app else None,
                "app_name": app.app_name if app else None,
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0
            }
        
        partner_stats[s.application_id]["total_calls"] += s.total_calls
        partner_stats[s.application_id]["successful_calls"] += s.successful_calls
        partner_stats[s.application_id]["failed_calls"] += s.failed_calls
    
    partner_list = sorted(
        partner_stats.values(),
        key=lambda x: x["total_calls"],
        reverse=True
    )[:limit]
    
    for p in partner_list:
        if p["total_calls"] > 0:
            p["success_rate"] = round(p["successful_calls"] / p["total_calls"] * 100, 2)
        else:
            p["success_rate"] = 0
    
    return ApiResponse(
        code=200,
        message="Success",
        data={"partners": partner_list}
    )
