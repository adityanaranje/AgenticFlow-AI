class AgentFlowError(Exception):
    """Base exception for AgentFlow AI."""


class ConfigurationError(AgentFlowError):
    """Raised when required configuration is missing."""


class ExternalServiceError(AgentFlowError):
    """Raised when an external service cannot be reached."""

class AuthorizationError(AgentFlowError):
    """Raised when a user is not authorized."""


class ConflictError(AgentFlowError):
    """Raised when an operation conflicts with existing state."""

class ValidationError(AgentFlowError):
    """Raised when application data fails validation."""


class AdmissionError(AgentFlowError):
    """Raised when a request is rejected by a usage guardrail.

    Token quota (hourly/daily per user) or the per-user concurrent-run
    limit. The API maps this to HTTP 429.
    """


class BudgetExhaustedError(AgentFlowError):
    """Raised mid-run when the run's token budget is reached.

    The run is marked failed with a clear message; the work already done
    is persisted, so nothing is silently lost.
    """