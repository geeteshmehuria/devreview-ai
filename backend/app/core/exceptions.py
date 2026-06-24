"""
Typed exception hierarchy — keeps error handling consistent across routers.
All exceptions map to specific HTTP status codes.
"""

from fastapi import HTTPException, status


class AppException(Exception):
    """Base application exception."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected error occurred"

    def __init__(self, detail: str | None = None, **kwargs):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)

    def to_http(self) -> HTTPException:
        return HTTPException(status_code=self.status_code, detail=self.detail)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentication required"


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "You do not have permission to perform this action"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    detail = "Resource already exists"


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = "Validation failed"


class AIProviderError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "AI provider is currently unavailable"


class RateLimitError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Rate limit exceeded. Please try again later."


class GitHubError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "Failed to communicate with GitHub"
