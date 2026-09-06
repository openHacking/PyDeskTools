"""Compile application and plugin gettext catalogs using development-only Babel."""

from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

root = Path(__file__).resolve().parents[1]
packages = {
    "pydesktools": "src/pydesktools",
    "org.pydesk.json-tools": "plugins/json-tools/src/pydesk_json_tools",
}
for domain, package in packages.items():
    for source in (root / "locales" / domain).glob("*/LC_MESSAGES/*.po"):
        target = (
            root
            / package
            / "locales"
            / source.relative_to(root / "locales" / domain).with_suffix(".mo")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as stream:
            catalog = read_po(stream)
        with target.open("wb") as stream:
            write_mo(stream, catalog)
