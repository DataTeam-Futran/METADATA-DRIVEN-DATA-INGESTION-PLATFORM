"""
Common exception hierarchy for the Metadata-Driven Data Ingestion Platform.
"""


class IngestionPlatformError(Exception):
    """Base exception for all ingestion platform failures."""

class AuthorizationError(IngestionPlatformError):
    """
    Raised when the ingestion runtime does not have
    sufficient permissions to perform the requested operation.
    """


class MetadataResolutionError(IngestionPlatformError):
    """Metadata or execution configuration could not be resolved."""


class MappingResolutionError(IngestionPlatformError):
    """Source-to-target mapping could not be resolved."""


class ConnectionResolutionError(IngestionPlatformError):
    """Source or target connection could not be established."""


class SchemaValidationError(IngestionPlatformError):
    """Source or target physical schema does not match the mapping."""


class SourceReadError(IngestionPlatformError):
    """Source extraction/read operation failed."""


class TargetWriteError(IngestionPlatformError):
    """Target truncate/write operation failed."""


class DataQualityError(IngestionPlatformError):
    """Source or target data-quality validation failed."""


class TransactionError(IngestionPlatformError):
    """Transaction begin/commit/rollback operation failed."""


class LoadVerificationError(IngestionPlatformError):
    """Post-load verification/reconciliation failed."""


class NetworkError(IngestionPlatformError):
    """Network-related ingestion operation failed."""


class AuditUpdateError(IngestionPlatformError):
    """Runtime/audit status update failed."""


class NoSourceDataError(IngestionPlatformError):
    """FULL load source returned zero records."""
