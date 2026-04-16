"""
Custom exceptions for the API.
"""

from typing import Any, Dict, Optional

from fastapi import status


class APIException(Exception):
    """Base exception for API errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        self.headers = headers or {}
        super().__init__(self.message)


class ValidationException(APIException):
    """Raised when input validation fails."""

    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class NotFoundException(APIException):
    """Raised when a resource is not found."""

    def __init__(self, resource: str, identifier: str = ""):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} '{identifier}' not found"

        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UnauthorizedException(APIException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(APIException):
    """Raised when access is forbidden."""

    def __init__(self, message: str = "Access forbidden"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictException(APIException):
    """Raised when there's a conflict (e.g., duplicate resource)."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class TooManyRequestsException(APIException):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class ServiceUnavailableException(APIException):
    """Raised when a service is unavailable."""

    def __init__(self, service: str):
        super().__init__(
            message=f"{service} is currently unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class TradingException(APIException):
    """Raised for trading-related errors."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class BrokerException(APIException):
    """Raised for broker connection/operation errors."""

    def __init__(self, broker: str, message: str):
        super().__init__(
            message=f"{broker} broker error: {message}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class InsufficientFundsException(TradingException):
    """Raised when there are insufficient funds for a trade."""

    def __init__(self, available: float, required: float):
        message = f"Insufficient funds: ${available} available, ${required} required"
        super().__init__(message)


class PositionSizeException(TradingException):
    """Raised when position size exceeds limits."""

    def __init__(self, requested: float, maximum: float):
        message = f"Position size exceeds limit: {requested} > {maximum}"
        super().__init__(message)
