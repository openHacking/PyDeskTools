"""GUI-independent plugin SDK, protocol major 1."""

from .api import CancellationToken, CommandResult, InvocationContext, PluginContext, PluginError

__version__ = "0.1.1"
__all__ = [
    "CancellationToken",
    "CommandResult",
    "PluginError",
    "PluginContext",
    "InvocationContext",
]

from .api import CommandDescriptor, Descriptor, Plugin

__all__ += ["CommandDescriptor", "Descriptor", "Plugin"]
