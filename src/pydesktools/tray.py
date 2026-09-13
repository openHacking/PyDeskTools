"""Native Windows notification-area and macOS menu-bar integration."""

import ctypes
import queue
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Any

if sys.platform == "darwin":
    from Foundation import NSObject

    class _MacOSTrayTarget(NSObject):
        def show_(self, _sender):
            self.on_show()

        def quit_(self, _sender):
            self.on_quit()


class UnavailableTray:
    available = False

    def close(self):
        pass


class MacOSTray:
    available = True

    def __init__(self, root, name, icon_path, on_show, on_quit):
        from AppKit import NSImage, NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength

        self._status_bar = NSStatusBar.systemStatusBar()
        self._item = self._status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        target_type = globals()["_MacOSTrayTarget"]
        self._target = target_type.alloc().init()
        self._target.on_show = on_show
        self._target.on_quit = on_quit
        image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
        image.setSize_((18, 18))
        self._item.button().setImage_(image)
        self._item.button().setToolTip_(name)
        menu = NSMenu.alloc().init()
        show = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Show {name}", "show:", ""
        )
        show.setTarget_(self._target)
        menu.addItem_(show)
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {name}", "quit:", ""
        )
        quit_item.setTarget_(self._target)
        menu.addItem_(quit_item)
        self._item.setMenu_(menu)

    def close(self):
        if self._item is not None:
            self._status_bar.removeStatusItem_(self._item)
            self._item = None


class LinuxTray:
    """Run pystray's selected Linux backend away from Tk's main thread."""

    def __init__(self, root, name, icon_path, on_show, on_quit):
        from PIL import Image
        from pystray import Icon, Menu, MenuItem  # type: ignore[import-not-found]

        with Image.open(icon_path) as source:
            image = source.convert("RGBA").copy()
        self._root = root
        self.available = True
        self._stopping = False
        self._events: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._ready = threading.Event()
        self._error = None
        self._poll_id = None

        def enqueue(event):
            def callback(_icon, _item):
                self._events.put(event)

            return callback

        menu = Menu(
            MenuItem(f"Show {name}", enqueue("show"), default=True),
            Menu.SEPARATOR,
            MenuItem(f"Quit {name}", enqueue("quit")),
        )
        self._icon = Icon("pydesktools", image, name, menu)
        self._callbacks = {"show": on_show, "quit": on_quit}
        self._thread = threading.Thread(
            target=self._run, name="pydesk-linux-tray", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            self._icon.stop()
            self._thread.join(timeout=2)
            raise RuntimeError("Timed out while creating the Linux tray icon")
        if self._error is not None:
            self._thread.join(timeout=2)
            raise RuntimeError("Could not create the Linux tray icon") from self._error
        self._poll_id = self._root.after(50, self._poll)

    def _run(self):
        def setup(icon):
            try:
                icon.visible = True
            except BaseException as error:
                self._error = error
                icon.stop()
            finally:
                self._ready.set()

        try:
            self._icon.run(setup=setup)
        except BaseException as error:
            self._error = error
            self._ready.set()
        finally:
            if not self._stopping:
                self.available = False

    def _poll(self):
        self._poll_id = None
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._callbacks[event]()
        if self._thread.is_alive():
            self._poll_id = self._root.after(50, self._poll)

    def close(self):
        self._stopping = True
        self.available = False
        if self._poll_id is not None:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None
        self._icon.stop()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)


class WindowsTray:
    available = True
    _WM_TRAY = 0x8000 + 20
    _WM_CLOSE = 0x0010
    _WM_DESTROY = 0x0002
    _WM_LBUTTONUP = 0x0202
    _WM_LBUTTONDBLCLK = 0x0203
    _WM_RBUTTONUP = 0x0205
    _NIM_ADD = 0
    _NIM_DELETE = 2
    _NIF_MESSAGE = 1
    _NIF_ICON = 2
    _NIF_TIP = 4

    def __init__(self, root, name, icon_path, on_show, on_quit):
        self._root = root
        self._name = name
        self._icon_path = Path(icon_path)
        self._on_show = on_show
        self._on_quit = on_quit
        self._events: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._ready = threading.Event()
        self._error = None
        self._hwnd = None
        self._thread = threading.Thread(
            target=self._message_loop, name="pydesk-tray", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Timed out while creating the notification-area icon")
        if self._error is not None:
            self._thread.join(timeout=2)
            raise RuntimeError("Could not create the notification-area icon") from self._error
        self._poll_id = self._root.after(50, self._poll)

    def _message_loop(self):
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.CreatePopupMenu.argtypes = []
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_size_t,
            wintypes.LPCWSTR,
        ]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.GetCursorPos.argtypes = [wintypes.LPPOINT]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.LPRECT,
        ]
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON),
            ]

        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        shell32.Shell_NotifyIconW.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(NOTIFYICONDATAW),
        ]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        notify: Any = None
        icon = None
        atom = None
        instance = None
        class_name = None

        @wndproc_type
        def wndproc(hwnd, message, wparam, lparam):
            if message == self._WM_TRAY:
                event = int(lparam)
                if event in (self._WM_LBUTTONUP, self._WM_LBUTTONDBLCLK):
                    self._events.put("show")
                elif event == self._WM_RBUTTONUP:
                    menu = user32.CreatePopupMenu()
                    user32.AppendMenuW(menu, 0, 1, f"Show {self._name}")
                    user32.AppendMenuW(menu, 0x0800, 0, None)
                    user32.AppendMenuW(menu, 0, 2, f"Quit {self._name}")
                    point = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(point))
                    user32.SetForegroundWindow(hwnd)
                    command = user32.TrackPopupMenu(
                        menu, 0x0100 | 0x0002, point.x, point.y, 0, hwnd, None
                    )
                    user32.DestroyMenu(menu)
                    if command == 1:
                        self._events.put("show")
                    elif command == 2:
                        self._events.put("quit")
                return 0
            if message == self._WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        try:
            instance = kernel32.GetModuleHandleW(None)
            class_name = f"PyDeskToolsTray-{id(self):x}"
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = wndproc
            window_class.hInstance = instance
            window_class.lpszClassName = class_name
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if not atom:
                raise ctypes.WinError()
            hwnd = user32.CreateWindowExW(
                0, class_name, self._name, 0, 0, 0, 0, 0, None, None, instance, None
            )
            if not hwnd:
                raise ctypes.WinError()
            self._hwnd = hwnd
            icon = user32.LoadImageW(
                None, str(self._icon_path), 1, 0, 0, 0x0010 | 0x0040
            )
            if not icon:
                raise ctypes.WinError()
            notify = NOTIFYICONDATAW()
            # The V2 structure contains every field used here and works with older shells too.
            notify.cbSize = NOTIFYICONDATAW.guidItem.offset
            notify.hWnd = hwnd
            notify.uID = 1
            notify.uFlags = self._NIF_MESSAGE | self._NIF_ICON | self._NIF_TIP
            notify.uCallbackMessage = self._WM_TRAY
            notify.hIcon = icon
            notify.szTip = self._name
            if not shell32.Shell_NotifyIconW(self._NIM_ADD, ctypes.byref(notify)):
                raise OSError(
                    "Shell_NotifyIconW rejected "
                    f"hwnd={hwnd!r} valid={bool(user32.IsWindow(hwnd))} "
                    f"icon={icon!r} size={notify.cbSize}"
                )
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as error:
            self._error = error
            self._ready.set()
        finally:
            if notify is not None:
                shell32.Shell_NotifyIconW(self._NIM_DELETE, ctypes.byref(notify))
            if icon is not None:
                user32.DestroyIcon(icon)
            if self._hwnd is not None:
                user32.DestroyWindow(self._hwnd)
            if atom and instance and class_name:
                user32.UnregisterClassW(class_name, instance)
            self._hwnd = None

    def _poll(self):
        self._poll_id = None
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            (self._on_show if event == "show" else self._on_quit)()
        if self._hwnd is not None:
            self._poll_id = self._root.after(50, self._poll)

    def close(self):
        if self._poll_id is not None:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None
        hwnd = self._hwnd
        if hwnd is not None:
            ctypes.windll.user32.PostMessageW(hwnd, self._WM_CLOSE, 0, 0)
            self._thread.join(timeout=2)


def create_tray(root, name, assets, on_show, on_quit):
    """Create a native tray where the platform supports one, with a safe fallback."""
    try:
        if sys.platform == "win32":
            return WindowsTray(root, name, Path(assets) / "logo.ico", on_show, on_quit)
        if sys.platform == "darwin":
            return MacOSTray(root, name, Path(assets) / "logo.png", on_show, on_quit)
        if sys.platform.startswith("linux"):
            return LinuxTray(root, name, Path(assets) / "logo.png", on_show, on_quit)
    except Exception:
        # A missing shell integration must never leave users with an inaccessible app.
        return UnavailableTray()
    return UnavailableTray()
