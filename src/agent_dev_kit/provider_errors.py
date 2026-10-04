class ProviderError(RuntimeError):
    """Base error for provider-neutral failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        original: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.original = original


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRecoverableError(ProviderError):
    """Base for failures where another provider may be attempted."""


class ProviderQuotaExceeded(ProviderRecoverableError):
    pass


class ProviderRateLimited(ProviderRecoverableError):
    pass


class ProviderUnavailable(ProviderRecoverableError):
    pass


class ProviderExecutionError(ProviderError):
    pass


class ProviderFallbackRequired(ProviderError):
    def __init__(
        self,
        *,
        current_provider: str,
        next_provider: str,
        cause: ProviderRecoverableError,
    ) -> None:
        super().__init__(
            f"Provider '{current_provider}' cannot continue: {cause}. "
            f"Fallback '{next_provider}' is available but requires approval.",
            provider=current_provider,
            original=cause,
        )
        self.current_provider = current_provider
        self.next_provider = next_provider
        self.cause = cause


def normalize_provider_exception(
    exc: Exception,
    *,
    provider: str,
) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc

    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)

    class_name = exc.__class__.__name__.lower()
    message = str(exc)
    lowered = message.lower()

    if status in {401, 403} or "authentication" in class_name:
        return ProviderAuthenticationError(
            f"Authentication failed for provider '{provider}'.",
            provider=provider,
            original=exc,
        )

    quota_signal = any(
        token in lowered
        for token in (
            "insufficient_quota",
            "quota exceeded",
            "quota_exceeded",
            "billing hard limit",
            "credit balance",
            "credits exhausted",
        )
    )
    if status == 402 or quota_signal:
        return ProviderQuotaExceeded(
            f"Provider '{provider}' has no available quota/credit.",
            provider=provider,
            original=exc,
        )

    if status == 429 or "ratelimit" in class_name or "rate limit" in lowered:
        return ProviderRateLimited(
            f"Provider '{provider}' is rate limited.",
            provider=provider,
            original=exc,
        )

    unavailable_signal = (
        status is not None and int(status) >= 500
    ) or any(
        token in lowered
        for token in (
            "temporarily unavailable",
            "service unavailable",
            "connection error",
            "timeout",
        )
    )
    if unavailable_signal:
        return ProviderUnavailable(
            f"Provider '{provider}' is temporarily unavailable.",
            provider=provider,
            original=exc,
        )

    return ProviderExecutionError(
        f"Provider '{provider}' failed: {message}",
        provider=provider,
        original=exc,
    )
