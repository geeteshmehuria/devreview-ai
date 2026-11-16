"""
Typed exception hierarchy — keeps error handling consistent across routers.
All exceptions map to specific HTTP status codes.
"""

from fastapi import status


class AppException(Exception):
    """Base application exception."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected error occurred"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentication required"


class AIProviderError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "AI provider is currently unavailable"


class RepositoryNotIndexedError(AppException):
    status_code = status.HTTP_409_CONFLICT
    detail = "This repository isn't indexed yet. Index it first, then start chatting."


class EmbeddingError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "Embedding service is currently unavailable"


class GitHubError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "Failed to communicate with GitHub"
