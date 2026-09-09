"""Render the code-native toolbox SVG into transparent desktop icon formats."""

import tkinter as tk
from pathlib import Path

from PIL import Image


def main():
    assets = Path(__file__).resolve().parents[1] / "src/pydesktools/assets"
    root = tk.Tk()
    root.withdraw()
    try:
        photo = tk.PhotoImage(master=root, data=(assets / "logo.svg").read_text(), format="svg")
        photo.write(str(assets / "logo.png"), format="png")
        with Image.open(assets / "logo.png") as image:
            image.save(assets / "logo.icns")
            image.save(assets / "logo.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
