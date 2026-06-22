class SettlementAutomationError(Exception):
    """Base exception for settlement automation errors."""


class ConfigurationError(SettlementAutomationError):
    """Raised when required configuration is missing or invalid."""


class MissingCredentialsError(ConfigurationError):
    """Raised when supplier portal credentials are missing."""

class BrowserAutomationError(SettlementAutomationError):
    """Raised when browser automation fails."""

class PortalDownloadError(BrowserAutomationError):
    """Raised when a portal report download fails."""

class SettlementAutomationError(Exception):
    """Base exception for settlement automation errors."""


class ConfigurationError(SettlementAutomationError):
    """Raised when required configuration is missing or invalid."""


class BrowserAutomationError(SettlementAutomationError):
    """Raised when browser automation fails."""


class PortalLoginError(BrowserAutomationError):
    """Raised when portal login fails."""


class PortalNavigationError(BrowserAutomationError):
    """Raised when portal navigation fails."""


class ReportRowNotFoundError(PortalDownloadError):
    """Raised when expected portal report row is missing."""


class ReportContentMismatchError(PortalDownloadError):
    """Raised when fetched report content is not the intended report."""


class ParserPipelineError(SettlementAutomationError):
    """Raised when fetched raw report cannot be parsed or validated."""