from __future__ import annotations


class VQEError(Exception):
    pass


class DataValidationError(VQEError):
    pass


class SourceError(VQEError):
    pass


class StorageError(VQEError):
    pass


class InsufficientDataError(VQEError):
    pass


class LookAheadError(VQEError):
    pass
