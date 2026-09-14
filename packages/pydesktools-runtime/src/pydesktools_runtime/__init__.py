"""Headless services; importing this package never imports tkinter."""

from .services import CloseHandle, RuntimeConfig, ServiceContainer, TaskHandle, create_services
from .storage import ProfileInUseError

__version__ = "0.1.1"
__all__ = [
    "RuntimeConfig",
    "ServiceContainer",
    "TaskHandle",
    "CloseHandle",
    "ProfileInUseError",
    "create_services",
]
