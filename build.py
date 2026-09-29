#!/usr/bin/env python3
"""Build the wedding card from src/template.html.

Inlines every {{name}} placeholder with src/img/<name>.jpg as a data URI and writes:
  index.html       - page body for the Claude artifact (the publisher adds the skeleton)
  docs/index.html  - standalone page served by GitHub Pages
"""
import base64
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "src"

HEAD = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#e3d5c7">
<meta name="description" content="سهیل و ملیکا، چهارشنبه ۱۵ مهر ۱۴۰۵، ساعت ۷ شب، باغ تالار لاوین">
<meta property="og:type" content="website">
<meta property="og:title" content="جشن عقد سهیل و ملیکا">
<meta property="og:description" content="چهارشنبه ۱۵ مهر ۱۴۰۵، ساعت ۷ شب، باغ تالار لاوین">
"""


def data_uri(name: str) -> str:
    raw = (SRC / "img" / f"{name}.jpg").read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def main() -> None:
    page = (SRC / "template.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{([\w-]+)\}\}", lambda m: data_uri(m.group(1)), page)
    (ROOT / "index.html").write_text(page, encoding="utf-8")

    head, sep, body = page.partition("</style>\n")
    standalone = HEAD + head + sep + "</head>\n<body>\n" + body + "</body>\n</html>\n"
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(standalone, encoding="utf-8")


if __name__ == "__main__":
    main()
