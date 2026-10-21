"""Application-specific exceptions mapped to HTTP responses."""


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, *, code: str = "app_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="not_found")


class ValidationAppError(AppError):
    def __init__(self, message: str, *, code: str = "validation_error") -> None:
        super().__init__(message, code=code)


class CardResolutionError(ValidationAppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="card_resolution_error")


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="conflict")
