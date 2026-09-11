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