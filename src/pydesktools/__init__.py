"""PyDeskTools desktop application. Importing does not create a GUI."""

from ._version import VERSION

__version__ = VERSION


def create_application(config=None):
    from .app import create_application as create

    return create(config)
