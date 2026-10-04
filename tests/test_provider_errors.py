from agent_dev_kit.provider_errors import (
    ProviderAuthenticationError,
    ProviderExecutionError,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderUnavailable,
    normalize_provider_exception,
)


class FakeHttpError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def test_quota_error_is_normalized_before_generic_429():
    error = normalize_provider_exception(
        FakeHttpError("insufficient_quota", status_code=429),
        provider="example",
    )

    assert isinstance(error, ProviderQuotaExceeded)


def test_rate_limit_is_normalized():
    error = normalize_provider_exception(
        FakeHttpError("rate limit reached", status_code=429),
        provider="example",
    )

    assert isinstance(error, ProviderRateLimited)


def test_authentication_is_normalized():
    error = normalize_provider_exception(
        FakeHttpError("unauthorized", status_code=401),
        provider="example",
    )

    assert isinstance(error, ProviderAuthenticationError)


def test_unavailable_is_normalized():
    error = normalize_provider_exception(
        FakeHttpError("service unavailable", status_code=503),
        provider="example",
    )

    assert isinstance(error, ProviderUnavailable)


def test_unknown_failure_is_normalized():
    error = normalize_provider_exception(
        RuntimeError("unexpected"),
        provider="example",
    )

    assert isinstance(error, ProviderExecutionError)
