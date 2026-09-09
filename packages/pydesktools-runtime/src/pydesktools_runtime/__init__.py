"""Headless services; importing this package never imports tkinter."""

from .services import CloseHandle, RuntimeConfig, ServiceContainer, TaskHandle, create_services

__version__ = "0.1.1"
__all__ = ["RuntimeConfig", "ServiceContainer", "TaskHandle", "CloseHandle", "create_services"]
