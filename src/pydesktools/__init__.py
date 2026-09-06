"""PyDeskTools desktop application. Importing does not create a GUI."""

__version__ = "0.1.0"


def create_application(config=None):
    from .app import create_application as create

    return create(config)
