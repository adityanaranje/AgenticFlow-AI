class AgentFlowError(Exception):
    """Base exception for AgentFlow AI."""


class ConfigurationError(AgentFlowError):
    """Raised when required configuration is missing."""


class ExternalServiceError(AgentFlowError):
    """Raised when an external service cannot be reached."""

class AuthorizationError(AgentFlowError):
    """Raised when a user is not authorized."""

class ValidationError(AgentFlowError):
    """Raised when application data fials validation."""