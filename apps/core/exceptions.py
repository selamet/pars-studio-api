"""
DRF exception handler producing a stable error envelope.

Validation errors keep DRF's per-field mapping under `errors`; every other
error is `{"detail": str, "code": str}` so the frontend can branch on `code`.
"""

from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        response.data = {
            "detail": "Validation failed.",
            "code": "validation_error",
            "errors": response.data,
        }
        return response

    detail = response.data.get("detail", "") if isinstance(response.data, dict) else response.data
    code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
    response.data = {"detail": str(detail), "code": str(code)}
    return response
