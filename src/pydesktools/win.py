# reference: https://tkdocs.com/tutorial/firstexample.html

from tkinter import *
from tkinter import ttk
from pydeskui.button import TxButton

# main window
class Win:
    def __init__(self, root):

        # set title
        root.title("PyDeskTools")
        # screen width
        sw = root.winfo_screenwidth()
        # screen height
        sh = root.winfo_screenheight()
        # frame width
        ww = 600
        # # frame height
        wh = 600
        x = (sw - ww) / 2
        y = (sh - wh) / 2 - 20

        root.geometry("%dx%d+%d+%d" % (ww, wh, x, y))
        root.resizable(False, False)
        root.config(background="white")

        # create content frame
        mainFrame = ttk.Frame(root, padding="3 3 12 12")
        mainFrame.grid(column=0, row=0, sticky=(N, W, E, S))

        # The columnconfigure/rowconfigure bits tell Tk that the frame should expand to fill any extra space if the window is resized.
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # set first button
        ttk.Button(mainFrame, text="Screenshot", command=self.screenshot).grid(
            column=1, row=1, sticky=W
        )

        # set second button
        ttk.Button(mainFrame, text="Clipboard", command=self.clipboard).grid(
            column=1, row=2, sticky=W
        )

        primaryButton = TxButton(
            mainFrame, type="primary", size="large", command=self.useClassic
        )
        primaryButton.grid(column=1, row=3, sticky=W)

        # set padding
        for child in mainFrame.winfo_children():
            child.grid_configure(padx=5, pady=5)

    def screenshot(self, *args):
        try:
            print("screenshot click")
        except ValueError:
            pass

    def clipboard(self, *args):
        try:
            print("clipboard click")
        except ValueError:
            pass

    def useClassic(self, *args):
        try:
            print("useClassic click")
        except ValueError:
            pass
