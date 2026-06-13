from typing import Optional, Dict
from sqlalchemy.orm import Session
from fastapi import HTTPException, Request
from models.database import ErrorCode, Application, ApiEndpoint
from schemas.schemas import ErrorResponse

class ErrorService:
    ERROR_CODES = {
        "AUTH_001": {"message": "Invalid app code or secret", "http_status": 401, "solution": "Please check your credentials"},
        "AUTH_002": {"message": "Token expired", "http_status": 401, "solution": "Please refresh your token"},
        "AUTH_003": {"message": "Invalid signature", "http_status": 401, "solution": "Check signature generation method"},
        "AUTH_004": {"message": "Application suspended", "http_status": 403, "solution": "Contact support to reactivate"},
        "AUTH_005": {"message": "Application inactive", "http_status": 403, "solution": "Activate your application first"},
        
        "ACCESS_001": {"message": "No access to this API", "http_status": 403, "solution": "Request access to this API endpoint"},
        "ACCESS_002": {"message": "Access not approved", "http_status": 403, "solution": "Wait for admin approval"},
        
        "RATE_001": {"message": "Daily quota exceeded", "http_status": 429, "solution": "Wait until tomorrow or request quota increase"},
        "RATE_002": {"message": "API rate limit exceeded", "http_status": 429, "solution": "Reduce request frequency"},
        
        "VALIDATION_001": {"message": "Invalid parameters", "http_status": 400, "solution": "Check parameter types and formats"},
        "VALIDATION_002": {"message": "Missing required parameter", "http_status": 400, "solution": "Provide all required parameters"},
        "VALIDATION_003": {"message": "Invalid parameter value", "http_status": 400, "solution": "Check parameter constraints"},
        
        "RESOURCE_001": {"message": "Resource not found", "http_status": 404, "solution": "Verify resource identifier"},
        "RESOURCE_002": {"message": "Order not found", "http_status": 404, "solution": "Check order ID"},
        "RESOURCE_003": {"message": "Customer not found", "http_status": 404, "solution": "Check customer ID"},
        
        "SYSTEM_001": {"message": "Internal server error", "http_status": 500, "solution": "Try again later"},
        "SYSTEM_002": {"message": "Service unavailable", "http_status": 503, "solution": "Try again later"},
        "SYSTEM_003": {"message": "Database error", "http_status": 500, "solution": "Try again later"},
        
        "CALLBACK_001": {"message": "Callback delivery failed", "http_status": 500, "solution": "Verify callback URL"},
        "CALLBACK_002": {"message": "Max retries exceeded", "http_status": 500, "solution": "Manually trigger callback replay"}
    }

    @staticmethod
    def initialize_error_codes(db: Session):
        for code, info in ErrorService.ERROR_CODES.items():
            existing = db.query(ErrorCode).filter(ErrorCode.code == code).first()
            if not existing:
                error_code = ErrorCode(
                    code=code,
                    message=info["message"],
                    http_status=info["http_status"],
                    solution=info.get("solution", "")
                )
                db.add(error_code)
        db.commit()

    @staticmethod
    def get_error_info(db: Session, error_code: str) -> Optional[Dict]:
        error = db.query(ErrorCode).filter(
            ErrorCode.code == error_code,
            ErrorCode.is_active == True
        ).first()
        
        if error:
            return {
                "code": error.code,
                "message": error.message,
                "http_status": error.http_status,
                "solution": error.solution
            }
        
        return ErrorService.ERROR_CODES.get(error_code)

    @staticmethod
    def create_error_response(
        error_code: str,
        request_id: Optional[str] = None,
        custom_message: Optional[str] = None
    ) -> Dict:
        error_info = ErrorService.ERROR_CODES.get(error_code, {
            "message": "Unknown error",
            "http_status": 500,
            "solution": "Contact support"
        })
        
        return {
            "code": error_info["http_status"],
            "message": custom_message or error_info["message"],
            "error_code": error_code,
            "request_id": request_id,
            "solution": error_info.get("solution")
        }

    @staticmethod
    def raise_http_exception(error_code: str, request_id: Optional[str] = None, detail: Optional[str] = None):
        error_info = ErrorService.ERROR_CODES.get(error_code, {
            "message": "Unknown error",
            "http_status": 500
        })
        
        message = detail or error_info["message"]
        
        raise HTTPException(
            status_code=error_info["http_status"],
            detail=ErrorService.create_error_response(error_code, request_id, message)
        )

class ValidationService:
    @staticmethod
    def validate_order_id(order_id: str) -> bool:
        if not order_id or len(order_id) < 6 or len(order_id) > 50:
            return False
        return True

    @staticmethod
    def validate_customer_id(customer_id: str) -> bool:
        if not customer_id or len(customer_id) < 6 or len(customer_id) > 50:
            return False
        return True

    @staticmethod
    def validate_pagination(skip: int, limit: int) -> tuple[int, int]:
        skip = max(0, skip)
        limit = max(1, min(limit, 100))
        return skip, limit
