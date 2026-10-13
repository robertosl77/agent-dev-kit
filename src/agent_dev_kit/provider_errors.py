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
    if status is None:
        # google-genai errors expose the HTTP status as ``code``.
        code = getattr(exc, "code", None)
        if isinstance(code, int):
            status = code

    class_name = exc.__class__.__name__.lower()
    message = str(exc)
    lowered = message.lower()

    missing_key_signal = any(
        token in lowered
        for token in (
            "missing credentials",
            "could not resolve authentication method",
            "missing key inputs",
        )
    )
    if missing_key_signal:
        return ProviderAuthenticationError(
            f"No API key available for provider '{provider}'.",
            provider=provider,
            original=exc,
        )

    invalid_key_signal = any(
        token in lowered
        for token in (
            "api key not valid",
            "api_key_invalid",
            "invalid x-api-key",
            "invalid api key",
            "incorrect api key",
        )
    )
    if status in {401, 403} or "authentication" in class_name or invalid_key_signal:
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
            "exceeded your current quota",
        )
    )
    if status == 402 or quota_signal:
        return ProviderQuotaExceeded(
            f"Provider '{provider}' has no available quota/credit.",
            provider=provider,
            original=exc,
        )

    if (
        status == 429
        or "ratelimit" in class_name
        or "rate limit" in lowered
        or "resource_exhausted" in lowered
    ):
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
            "overloaded",
        )
    )
    if unavailable_signal:
        return ProviderUnavailable(
            f"Provider '{provider}' is temporarily unavailable.",
            provider=provider,
            original=exc,
        )

    return ProviderExecutionError(
        f"Provider '{provider}' failed: {message}{_detail(exc, message)}",
        provider=provider,
        original=exc,
    )


def _detail(exc: Exception, message: str) -> str:
    """What the API (or a proxy in between) answered, when the SDK hides it.

    Some SDK messages are just "Error code: 400". The body usually says why
    (bad header, unknown parameter, a corporate proxy page...).
    """

    body = getattr(exc, "body", None)
    text = ""
    if isinstance(body, dict):
        error = body.get("error")
        text = str(error.get("message") if isinstance(error, dict) else error or "")
    elif isinstance(body, str):
        text = body
    if not text:
        response = getattr(exc, "response", None)
        try:
            text = str(getattr(response, "text", "") or "")
        except Exception:  # streamed/closed responses cannot be read again
            text = ""
    text = " ".join(text.split())[:300]
    if not text or text in message:
        return ""
    return f" — respuesta: {text}"
