from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "APP_ERROR", details: dict = None):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            status_code=404,
            code="NOT_FOUND",
            details={"resource": resource, "identifier": identifier}
        )


class ConflictError(AppException):
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            status_code=409,
            code="CONFLICT",
            details=details
        )


class BusinessRuleError(AppException):
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            status_code=422,
            code="BUSINESS_RULE_VIOLATION",
            details=details
        )


class InsufficientStockError(BusinessRuleError):
    def __init__(self, product_name: str, requested: int, available: int):
        super().__init__(
            message=f"Insufficient stock for {product_name}: requested {requested}, available {available}",
            details={"product": product_name, "requested": requested, "available": available}
        )


class CreditLimitExceededError(BusinessRuleError):
    def __init__(self, retailer_name: str, order_amount: float, credit_limit: float, available_credit: float):
        super().__init__(
            message=f"Credit limit exceeded for {retailer_name}",
            details={
                "retailer": retailer_name,
                "order_amount": order_amount,
                "credit_limit": credit_limit,
                "available_credit": available_credit
            }
        )


class ExpiryTooSoonError(BusinessRuleError):
    def __init__(self, product_name: str, batch_number: str, expiry_date: str, days_to_expiry: int, threshold: int):
        super().__init__(
            message=f"Product {product_name} (batch {batch_number}) expires in {days_to_expiry} days, minimum {threshold} days required",
            details={
                "product": product_name,
                "batch": batch_number,
                "expiry_date": expiry_date,
                "days_to_expiry": days_to_expiry,
                "threshold": threshold
            }
        )


class InvalidStateTransitionError(BusinessRuleError):
    def __init__(self, entity: str, current_state: str, attempted_state: str):
        super().__init__(
            message=f"Invalid state transition for {entity}: cannot move from {current_state} to {attempted_state}",
            details={"entity": entity, "current_state": current_state, "attempted_state": attempted_state}
        )


def register_exception_handlers(app: FastAPI) -> None:
    
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details
                }
            }
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": exc.detail,
                    "details": {}
                }
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(x) for x in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": errors}
                }
            }
        )
    
    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(x) for x in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Data validation failed",
                    "details": {"errors": errors}
                }
            }
        )
    
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.error(f"Database integrity error: {exc}")
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "DATABASE_CONFLICT",
                    "message": "A database constraint was violated. This may be due to a duplicate entry.",
                    "details": {}
                }
            }
        )
    
    @app.exception_handler(OperationalError)
    async def operational_error_handler(request: Request, exc: OperationalError):
        logger.error(f"Database operational error: {exc}")
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Database is temporarily unavailable. Please try again later.",
                    "details": {}
                }
            }
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {}
                }
            }
        )