"""Tk-thread capability adapter. Workers receive data only."""

import os
import queue
import sys
import tempfile
from concurrent.futures import Future
from pathlib import Path
from tkinter import filedialog
from typing import Any

from pydesktools_sdk import PluginError
from pydeskui import Scheduler


class PlatformAdapter:
    def __init__(self, root):
        self.root = root
        self.requests: queue.Queue = queue.Queue(maxsize=8)
        self.closed = False
        self._dialog_token = None
        self.scheduler = Scheduler(root)
        self._panel = None
        self._finish_dialog = None

    def call(self, capability, arguments, *, plugin_id, cancellation, artifacts):
        if capability == "clipboard.write" and "artifact_id" in arguments:
            arguments = dict(arguments)
            arguments["text"] = artifacts.path(plugin_id, arguments.pop("artifact_id")).read_text(
                encoding="utf-8"
            )
        response: Future[Any] = Future()
        try:
            self.requests.put_nowait(
                (capability, arguments, plugin_id, cancellation, artifacts, response)
            )
        except queue.Full:
            raise PluginError("busy", "Too many interactive requests", code=-32004) from None
        while not self.closed:
            cancellation.raise_if_cancelled()
            try:
                selected = response.result(timeout=0.05)
                break
            except TimeoutError:
                continue
        else:
            raise PluginError("canceled", "Application closed", code=-32005)
        cancellation.raise_if_cancelled()
        if capability == "dialogs.save_file" and selected:
            source = artifacts.path(plugin_id, arguments["artifact_id"])
            destination = Path(selected)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=destination.parent, prefix=".pydesk-", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    with source.open("rb") as src:
                        while chunk := src.read(1024 * 1024):
                            cancellation.raise_if_cancelled()
                            stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Windows does not allow replacing an open NamedTemporaryFile.
                cancellation.raise_if_cancelled()
                os.replace(temporary, destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return selected

    def _dismiss_panel(self):
        panel = self._panel
        if panel is not None:
            parent = panel.sheetParent()
            if parent is not None:
                parent.endSheet_returnCode_(panel, 0)
            panel.orderOut_(None)
            if self._finish_dialog:
                self._finish_dialog(None)

    def _watch_dialog(self):
        token = self._dialog_token
        if token is None or self.closed:
            return
        if token.is_cancelled:
            self._dismiss_panel()
            return
        self.scheduler.call_later(50, self._watch_dialog)

    def _choose(self, capability, arguments, cancellation, response):
        def completed(value):
            if response.done():
                return
            self._finish_dialog = None
            self._dialog_token = None
            self._panel = None
            try:
                cancellation.raise_if_cancelled()
                if capability == "dialogs.open_files":
                    response.set_result(list(value or ()))
                else:
                    response.set_result(str(value) if value else None)
            except BaseException as error:
                response.set_exception(error)

        if sys.platform == "darwin":
            from AppKit import NSApplication, NSModalResponseOK, NSOpenPanel, NSSavePanel

            windows = NSApplication.sharedApplication().windows()
            parent = next(
                (window for window in windows if str(window.title()) == self.root.title()), None
            )
            if parent is None:
                raise RuntimeError("The application's native parent window is unavailable")
            panel = (
                NSSavePanel.savePanel()
                if capability == "dialogs.save_file"
                else NSOpenPanel.openPanel()
            )
            panel.setTitle_(arguments.get("title", "JSON"))
            if capability == "dialogs.save_file":
                panel.setNameFieldStringValue_(
                    Path(arguments.get("suggested_name", "output.json")).name
                )
            else:
                choose_directory = capability == "dialogs.choose_directory"
                panel.setCanChooseDirectories_(choose_directory)
                panel.setCanChooseFiles_(not choose_directory)
                panel.setAllowsMultipleSelection_(capability == "dialogs.open_files")
            self._dialog_token = cancellation
            self._panel = panel
            self._finish_dialog = completed

            def finished(result):
                if result != NSModalResponseOK:
                    completed([] if capability == "dialogs.open_files" else None)
                elif capability == "dialogs.open_files":
                    completed([str(url.path()) for url in panel.URLs()])
                else:
                    completed(panel.URL().path())

            panel.beginSheetModalForWindow_completionHandler_(parent, finished)
            self.scheduler.call_later(50, self._watch_dialog)
        else:
            if capability == "dialogs.open_files":
                value = list(
                    filedialog.askopenfilenames(
                        parent=self.root, title=arguments.get("title", "Open")
                    )
                )
            elif capability == "dialogs.choose_directory":
                value = (
                    filedialog.askdirectory(
                        parent=self.root, title=arguments.get("title", "Choose folder")
                    )
                    or None
                )
            else:
                value = (
                    filedialog.askopenfilename(
                        parent=self.root, title=arguments.get("title", "Open")
                    )
                    if capability == "dialogs.open_file"
                    else filedialog.asksaveasfilename(
                        parent=self.root,
                        title=arguments.get("title", "Save"),
                        initialfile=Path(arguments.get("suggested_name", "output.json")).name,
                        confirmoverwrite=True,
                    )
                )
            completed(value)

    def drain(self):
        if self.closed or self._dialog_token is not None:
            return
        try:
            capability, arguments, plugin, cancellation, artifacts, response = (
                self.requests.get_nowait()
            )
        except queue.Empty:
            return
        try:
            cancellation.raise_if_cancelled()
            if capability in (
                "dialogs.open_file",
                "dialogs.open_files",
                "dialogs.choose_directory",
                "dialogs.save_file",
            ):
                if capability == "dialogs.save_file":
                    artifacts.path(plugin, arguments["artifact_id"])
                self._choose(capability, arguments, cancellation, response)
                return
            if capability != "clipboard.write":
                raise PluginError(
                    "unsupported_capability", "Unsupported platform capability", code=-32601
                )
            if ("text" in arguments) == ("artifact_id" in arguments):
                raise ValueError("Supply exactly one clipboard payload")
            text = arguments.get("text")
            if text is None:
                text = artifacts.path(plugin, arguments["artifact_id"]).read_text(encoding="utf-8")
            cancellation.raise_if_cancelled()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            response.set_result(None)
        except BaseException as error:
            response.set_exception(error)

    def close(self):
        self.closed = True
        self.scheduler.close()
        if self._dialog_token is not None:
            self._dismiss_panel()
        while True:
            try:
                *_, response = self.requests.get_nowait()
                response.set_exception(PluginError("canceled", "Application closed", code=-32005))
            except queue.Empty:
                break
