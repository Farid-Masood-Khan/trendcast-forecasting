"""Exception taxonomy for TrendCast."""


class TrendCastError(Exception):
    """Base exception for TrendCast."""


class SeriesNotFound(TrendCastError):
    """Raised when a requested series_id is not in the catalogue."""


class InsufficientHistory(TrendCastError):
    """Raised when a series has fewer observations than required for reliable forecasting."""


class ModelFitError(TrendCastError):
    """Raised when a forecasting model fails to converge or fit the training slice."""


class StaleSnapshot(TrendCastError):
    """Raised or warned when snapshot data is older than the staleness limit."""

