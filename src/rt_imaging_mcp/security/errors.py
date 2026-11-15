"""Errors with fixed messages.

Rule R6: error messages never contain data read from files. To make that
impossible by construction, these exceptions take no arguments and always
carry the static ``message`` of their class.
"""

from __future__ import annotations


class RtImagingMcpError(Exception):
    """Base class. The message is a fixed string, never built from file content."""

    message = "internal error"

    def __init__(self) -> None:
        super().__init__(self.message)


class ConfigError(RtImagingMcpError):
    message = "invalid configuration"


class InvalidPathError(RtImagingMcpError):
    message = "invalid path"


class PathOutsideRootError(RtImagingMcpError):
    message = "path is outside the configured root"


class PathNotFoundError(RtImagingMcpError):
    message = "path does not exist"


class WrongPathKindError(RtImagingMcpError):
    message = "path is not of the expected kind"


class TagNotAllowedError(RtImagingMcpError):
    message = "tag is not allowed"


class FileTooLargeError(RtImagingMcpError):
    message = "file exceeds the configured size limit"


class NotDicomError(RtImagingMcpError):
    message = "file is not a readable DICOM file"


class NotNiftiError(RtImagingMcpError):
    message = "file is not a readable NIfTI file"


class NotRtStructError(RtImagingMcpError):
    message = "file is not a readable RT structure set"


class NotRtDoseError(RtImagingMcpError):
    message = "file is not a readable RT dose file"


class NotRtPlanError(RtImagingMcpError):
    message = "file is not a readable RT plan file"
