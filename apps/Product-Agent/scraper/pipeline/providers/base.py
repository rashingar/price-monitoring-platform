from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ProviderDefinition, ProviderErrorCode, ProviderErrorInfo, ProviderInputIdentity, ProviderResult, ProviderSnapshot, ProviderStage


class ProviderError(RuntimeError):
    def __init__(self, error: ProviderErrorInfo, *, cause: BaseException | None = None) -> None:
        super().__init__(error.message)
        self.error = error
        self.cause = cause

    @classmethod
    def build(
        cls,
        *,
        provider_id: str,
        code: ProviderErrorCode,
        stage: ProviderStage,
        message: str,
        retryable: bool = False,
        details: dict[str, object] | None = None,
        cause: BaseException | None = None,
    ) -> "ProviderError":
        return cls(
            ProviderErrorInfo(
                provider_id=provider_id,
                code=code,
                stage=stage,
                message=message,
                retryable=retryable,
                details=dict(details or {}),
            ),
            cause=cause,
        )


class ProductProvider(ABC):
    definition: ProviderDefinition

    @property
    def provider_id(self) -> str:
        return self.definition.provider_id

    @property
    def source_name(self) -> str:
        return self.definition.source_name

    def supports_identity(self, identity: ProviderInputIdentity) -> bool:
        del identity
        return True

    @abstractmethod
    def fetch_snapshot(self, identity: ProviderInputIdentity) -> ProviderSnapshot:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, snapshot: ProviderSnapshot, identity: ProviderInputIdentity) -> ProviderResult:
        raise NotImplementedError
