import argparse

from engine import PluginEngine
from pydesktools.win import Win
from util import FileSystem

from tkinter import *
from tkinter import ttk


def __description() -> str:
    return "Create your own anime meta data"


def __usage() -> str:
    return "Vrv-meta.py --setvice vrv"


def __init_cli() -> argparse:
    parser = argparse.ArgumentParser(description=__description(), usage=__usage())
    parser.add_argument(
        "-l",
        "--log",
        default="DEBUG",
        help="""
        Specify log level which should use. Default will always be DEBUG, choose between the following options
        CRITICAL, ERROR, WARNING, INFO, DEBUG
        """,
    )

    print("FileSystem", FileSystem)
    parser.add_argument(
        "-d",
        "--directory",
        default=f"{FileSystem.get_plugins_directory()}",
        help="""
        (Optional) Supply a directory where plugins should be loaded from. The default is ./plugins
        """,
    )
    return parser


def __print_program_end() -> None:
    print("---End of execution---")


def __init_app(parameters: dict) -> None:
    PluginEngine(options=parameters).start()


def __init_win() -> None:
    # sets up the main application window
    root = Tk()
    # init function
    Win(root)
    # necessary for everything to appear onscreen and allow users to interact with it.
    root.mainloop()


if __name__ == "__main__":
    __cli_args = __init_cli().parse_args()
    __init_app({"log_level": __cli_args.log, "directory": __cli_args.directory})
    __init_win()
