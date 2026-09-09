"""Compose the GitHub social preview from real, repository-owned assets."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"


def font(size, *, bold=False):
    candidates = [
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def main():
    canvas = Image.new("RGB", (1280, 640), "#F3F7FD")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((36, 36, 1244, 604), radius=32, fill="#FFFFFF", outline="#DDE8F7", width=2)

    logo = Image.open(ROOT / "src/pydesktools/assets/logo.png").convert("RGBA")
    logo.thumbnail((112, 112), Image.Resampling.LANCZOS)
    canvas.paste(logo, (100, 130), logo)
    draw.text((100, 270), "PyDeskTools", font=font(58, bold=True), fill="#151922")
    draw.text((100, 350), "Private desktop tools.", font=font(28), fill="#3D4B63")
    draw.text((100, 392), "Fast. Local. Extensible.", font=font(28), fill="#3D4B63")
    draw.rounded_rectangle((100, 475, 310, 523), radius=24, fill="#1677FF")
    draw.text((132, 484), "OFFLINE FIRST", font=font(20, bold=True), fill="#FFFFFF")

    screenshot = Image.open(ASSETS / "pydesktools-home.png").convert("RGB")
    screenshot.thumbnail((700, 500), Image.Resampling.LANCZOS)
    x = 500
    y = (640 - screenshot.height) // 2
    shadow = Image.new("RGBA", (screenshot.width + 28, screenshot.height + 28), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((10, 10, screenshot.width + 18, screenshot.height + 18), radius=18, fill=(21, 44, 80, 30))
    canvas.paste(shadow, (x - 14, y - 10), shadow)
    canvas.paste(screenshot, (x, y))

    output = ASSETS / "social-preview.png"
    canvas.save(output, optimize=True)
    print(output)


if __name__ == "__main__":
    main()
