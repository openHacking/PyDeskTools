from logging import Logger
from typing import Optional, List

from model import Meta, Device


class IPluginRegistry(type):
    plugin_registries: List[type] = list()

    def __init__(cls, name, bases, attrs):
        super().__init__(cls)
        if name != 'PluginCore':
            IPluginRegistry.plugin_registries.append(cls)


class PluginCore(object, metaclass=IPluginRegistry):
    """
    Plugin core class
    """

    meta: Optional[Meta]

    def __init__(self, logger: Logger) -> None:
        """Entry init block for plugins

        Args:
            logger (Logger): logger that plugins can make use of
        """

        self._logger = logger

    def invoke(self, **args) -> Device:
        """Starts main plugin flow
        Args:
            args: possible arguments for the plugin
        Returns:
            Device: a device for the plugin
        """

        pass
