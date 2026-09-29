"""Consistent API error model and domain exceptions.

Every handled error surfaces to the client through the same envelope::

    {
        "error": {
            "code": "CASE_NOT_FOUND",
            "message": "Case was not found",
            "request_id": "01J..."
            "details": { ... }     # optional
        }
    }

Machine-readable ``code`` values are stable identifiers that the frontend can
branch on.  They never expose stack traces, SQL, or secrets.
"""

from __future__ import annotations

import traceback
from typing import Any

from starlette.requests import Request


class AppError(Exception):
    """Base class for all domain errors."""

    code = "ERROR"
    message = "An unexpected error occurred."
    status_code = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


# ------------------------------------------------------------------ 400s
class ValidationError_(AppError):
    code = "VALIDATION_ERROR"
    message = "Request validation failed."
    status_code = 422


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    status_code = 400


class AuthenticationError(AppError):
    code = "UNAUTHENTICATED"
    message = "Authentication required."
    status_code = 401


class AuthorizationError(AppError):
    code = "FORBIDDEN"
    message = "You do not have permission to perform this action."
    status_code = 403


class NotFoundError(AppError):
    code = "NOT_FOUND"
    message = "The requested resource was not found."
    status_code = 404


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    message = "Too many requests. Please slow down."
    status_code = 429


class SensitiveDataError(AppError):
    code = "SENSITIVE_DATA"
    message = "Request refused because it contained sensitive unsupported fields."
    status_code = 400


# ------------------------------------------------------------------ 5xx
class ExternalDependencyError(AppError):
    code = "EXTERNAL_DEPENDENCY_UNAVAILABLE"
    status_code = 502


class ModelInferenceError(AppError):
    code = "MODEL_INFERENCE_FAILED"
    status_code = 500


class TrainingError(AppError):
    code = "MODEL_TRAINING_FAILED"
    status_code = 500


class NotImplementedYet(AppError):
    code = "NOT_IMPLEMENTED"
    status_code = 501


# ------------------------------------------------------------- helpers
def error_payload(error: AppError, request_id: str | None = None) -> dict[str, Any]:
    """Build the serialisable error envelope for an :class:`AppError`."""
    body: dict[str, Any] = {
        "error": {
            "code": error.code,
            "message": error.message,
            "request_id": request_id or "",
        }
    }
    if error.details:
        body["error"]["details"] = error.details
    return body


def request_id_of(request: Request) -> str:
    """Return the request id propagated through the request middleware."""
    return getattr(request.state, "request_id", "") or ""


def format_traceback(exc: BaseException) -> str:
    """Render a traceback for server-side logs (never sent to the client)."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


# --------------------------------------------------------- convenience
CASE_NOT_FOUND = NotFoundError("Case was not found", code="CASE_NOT_FOUND")
COMPLAINT_NOT_FOUND = NotFoundError("Complaint was not found", code="COMPLAINT_NOT_FOUND")
TRANSACTION_NOT_FOUND = NotFoundError("Transaction was not found", code="TRANSACTION_NOT_FOUND")
ATM_NOT_FOUND = NotFoundError("ATM was not found", code="ATM_NOT_FOUND")
ALERT_NOT_FOUND = NotFoundError("Alert was not found", code="ALERT_NOT_FOUND")
PREDICTION_NOT_FOUND = NotFoundError("Prediction was not found", code="PREDICTION_NOT_FOUND")
USER_NOT_FOUND = NotFoundError("User was not found", code="USER_NOT_FOUND")
ENTITY_NOT_FOUND = NotFoundError("Entity was not found", code="ENTITY_NOT_FOUND")
SIMULATION_NOT_FOUND = NotFoundError("Simulation was not found", code="SIMULATION_NOT_FOUND")
INTERVENTION_NOT_FOUND = NotFoundError("Intervention was not found", code="INTERVENTION_NOT_FOUND")
MODEL_NOT_FOUND = NotFoundError("Model was not found", code="MODEL_NOT_FOUND")
OUTCOME_NOT_FOUND = NotFoundError("Outcome was not found", code="OUTCOME_NOT_FOUND")
INVESTIGATION_NOT_FOUND = NotFoundError("Investigation was not found", code="INVESTIGATION_NOT_FOUND")


__all__ = [
    # A few common pre-built instances
    "ALERT_NOT_FOUND",
    "ATM_NOT_FOUND",
    "CASE_NOT_FOUND",
    "COMPLAINT_NOT_FOUND",
    "ENTITY_NOT_FOUND",
    "INTERVENTION_NOT_FOUND",
    "INVESTIGATION_NOT_FOUND",
    "MODEL_NOT_FOUND",
    "OUTCOME_NOT_FOUND",
    "PREDICTION_NOT_FOUND",
    "SIMULATION_NOT_FOUND",
    "TRANSACTION_NOT_FOUND",
    "USER_NOT_FOUND",
    "AppError",
    "AuthenticationError",
    "AuthorizationError",
    "BadRequestError",
    "ConflictError",
    "ExternalDependencyError",
    "ModelInferenceError",
    "ModelNotActiveError",
    "NotFoundError",
    "NotImplementedYet",
    "RateLimitedError",
    "SensitiveDataError",
    "TrainingError",
    "ValidationError_",
    "error_payload",
    "format_traceback",
    "request_id_of",
]


class ModelNotActiveError(AppError):
    code = "MODEL_NOT_ACTIVE"
    message = "No active trained model is available for this task."
    status_code = 503
