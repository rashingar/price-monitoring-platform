from __future__ import annotations

from enum import Enum

from ..providers.base import ProviderError
from ..providers.models import ProviderStage
from .metadata import MetadataWriteError


class ServiceErrorCode(str, Enum):
    MISSING_ARTIFACT = "missing_artifact"
    PROVIDER_FAILURE = "provider_failure"
    PARSE_FAILURE = "parse_failure"
    VALIDATION_FAILURE = "validation_failure"
    PUBLISH_FAILURE = "publish_failure"
    UNEXPECTED_FAILURE = "unexpected_failure"


class ServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause: BaseException | None = None,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause
        self.retryable = retryable
        self.details = dict(details or {})


def _walk_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = getattr(current, "cause", None) or current.__cause__
    return chain


def _is_parse_failure_message(message: str) -> bool:
    return message in {
        "Total parse failure",
        "Missing presentation source sections for requested render sections",
        "No usable deterministic presentation sections for requested render sections",
    } or message.startswith("Unsupported ") or message.startswith("Too many missing deterministic presentation sections:")


def service_error_from_exception(exc: BaseException, *, operation: str) -> ServiceError:
    if isinstance(exc, ServiceError):
        return exc

    chain = _walk_exception_chain(exc)

    provider_error = next((item for item in chain if isinstance(item, ProviderError)), None)
    if provider_error is not None:
        code = (
            ServiceErrorCode.PARSE_FAILURE
            if provider_error.error.stage == ProviderStage.NORMALIZE
            else ServiceErrorCode.PROVIDER_FAILURE
        )
        return ServiceError(
            code.value,
            provider_error.error.message,
            cause=exc,
            retryable=provider_error.error.retryable,
            details={
                "provider_id": provider_error.error.provider_id,
                "provider_code": provider_error.error.code.value,
                "provider_stage": provider_error.error.stage.value,
                **provider_error.error.details,
            },
        )

    metadata_error = next((item for item in chain if isinstance(item, MetadataWriteError)), None)
    if metadata_error is not None:
        return ServiceError(
            ServiceErrorCode.UNEXPECTED_FAILURE.value,
            str(metadata_error),
            cause=exc,
            details={
                "metadata_path": str(metadata_error.metadata_path),
                "metadata_run_type": metadata_error.payload.run.run_type.value,
                "metadata_run_status": metadata_error.payload.run.status.value,
                "metadata_error_code": metadata_error.payload.run.error_code,
                "metadata_error_detail": metadata_error.payload.run.error_detail,
            },
        )

    file_error = next((item for item in chain if isinstance(item, FileNotFoundError)), None)
    if file_error is not None:
        details: dict[str, object] = {}
        filename = getattr(file_error, "filename", None)
        if filename:
            details["filename"] = str(filename)
        return ServiceError(
            ServiceErrorCode.MISSING_ARTIFACT.value,
            str(file_error),
            cause=exc,
            details=details,
        )

    if _is_parse_failure_message(str(exc)):
        return ServiceError(ServiceErrorCode.PARSE_FAILURE.value, str(exc), cause=exc)

    if operation == "render" and isinstance(exc, OSError):
        return ServiceError(ServiceErrorCode.PUBLISH_FAILURE.value, str(exc), cause=exc, retryable=True)

    return ServiceError(ServiceErrorCode.UNEXPECTED_FAILURE.value, str(exc), cause=exc)

