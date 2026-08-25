from __future__ import annotations


class ModelAdapterError(Exception):
    """A safe, stable failure category from a model provider boundary."""

    error_code = "MODEL_INVOCATION_ERROR"
    retryable = False


class ModelTimeoutError(ModelAdapterError):
    error_code = "MODEL_TIMEOUT"
    retryable = True


class ModelConnectionError(ModelAdapterError):
    error_code = "MODEL_CONNECTION_ERROR"
    retryable = True


class ModelRateLimitedError(ModelAdapterError):
    error_code = "MODEL_RATE_LIMITED"
    retryable = True


class ModelHttpError(ModelAdapterError):
    error_code = "MODEL_HTTP_ERROR"
    retryable = True


class ModelInvalidResponseError(ModelAdapterError):
    error_code = "MODEL_INVALID_RESPONSE"

