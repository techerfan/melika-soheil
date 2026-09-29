#!/usr/bin/env python3
"""Turn the flower crops from the mockup into transparent PNGs.

For each crop in src/img/*.bmp (24-bit, exported with `sips -s format bmp`):
  - the paper colour is keyed out to transparency, so the flowers sit on the
    card's own background instead of a pasted rectangle
  - the frame line baked into the crop is cut out, so the CSS frame is the
    only line on the page
  - edges that face the card interior are feathered

Writes src/img/<name>.png. No third-party libraries: BMP in, PNG out by hand.
"""
import pathlib
import struct
import sys
import zlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "img"

# Which edges of each crop face the card interior (and should fade out).
FEATHER = {
    "fl-l": ("top", "bottom", "right"),
    "fl-r": ("top", "bottom", "left"),
    "fl-bl": ("top", "right"),
    "fl-br": ("top", "left"),
    "sprig-l": ("top", "bottom", "left", "right"),
    "sprig-r": ("top", "bottom", "left", "right"),
}
FEATHER_PX = 14

# Where the mockup's frame line runs inside each crop (columns, rows), measured
# on the mockup: x=18.5 and x=833.5, bottom line y=1256. Detection alone also
# catches stems, so the positions are pinned here.
LINES = {
    "fl-l": ([18, 19], []),
    "fl-r": ([70, 71], []),
    "fl-bl": ([18, 19], [301, 302]),
    "fl-br": ([], []),          # replaced by a clean source image (src/img/fl-br-src.png), no line in it
    "sprig-l": ([], []),
    "sprig-r": ([], []),
}
KEY_LOW, KEY_HIGH = 9, 30   # max channel distance from paper: fully clear .. fully opaque
LINE_PAD = 5                # band cleared each side of a frame line: the mockup line has a faint
                            # parallel echo 3-4px away near the corners, so the band must cover it
PETAL_LIFT = 40             # sum(rgb) above local paper that marks a petal; paper highlights stay under ~33
OUTSIDE = LINE_PAD + 3      # how far outside the band to look when deciding a band pixel sits on plain paper
TILE = 16                   # local paper estimate: median per tile, so the vignette keys out too


def read_bmp(path):
    d = path.read_bytes()
    off = struct.unpack_from("<I", d, 10)[0]
    w, h = struct.unpack_from("<ii", d, 18)
    bpp = struct.unpack_from("<H", d, 28)[0]
    assert bpp == 24, f"{path.name}: expected 24-bit BMP"
    H = abs(h)
    stride = (w * 3 + 3) // 4 * 4
    rows = []
    for y in range(H):
        yy = H - 1 - y if h > 0 else y
        base = off + yy * stride
        rows.append([(d[base + x * 3 + 2], d[base + x * 3 + 1], d[base + x * 3]) for x in range(w)])
    return w, H, rows


def write_png(path, w, h, rgba_rows):
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rgba_rows)
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def median(vals):
    s = sorted(vals)
    return s[len(s) // 2]


def paper_colour(rows):
    px = [p for row in rows for p in row]
    return tuple(median([p[c] for p in px]) for c in range(3))


def local_paper(w, h, rows, global_paper):
    """Median colour per TILE, falling back to the global paper where a tile is mostly flowers."""
    tiles = {}
    for ty in range(0, h, TILE):
        for tx in range(0, w, TILE):
            px = [rows[y][x] for y in range(ty, min(ty + TILE, h)) for x in range(tx, min(tx + TILE, w))]
            m = tuple(median([p[c] for p in px]) for c in range(3))
            far = max(abs(m[c] - global_paper[c]) for c in range(3))
            tiles[(tx // TILE, ty // TILE)] = m if far < 18 else global_paper
    return lambda x, y: tiles[(x // TILE, y // TILE)]


def find_lines(w, h, rows, paper):
    """Columns/rows that are darker than the paper along most of their length."""
    lum = lambda p: (p[0] + p[1] + p[2]) / 3
    pl = lum(paper)
    cols = [x for x in range(w) if sum(lum(rows[y][x]) < pl - 14 for y in range(h)) > 0.55 * h]
    rws = [y for y in range(h) if sum(lum(rows[y][x]) < pl - 14 for x in range(w)) > 0.55 * w]
    return cols, rws


def key(name):
    w, h, rows = read_bmp(SRC / f"{name}.bmp")
    paper = paper_colour(rows)
    paper_at = local_paper(w, h, rows, paper)
    detected = find_lines(w, h, rows, paper)
    cols, rws = LINES[name]
    clear_x = {x + dx for x in cols for dx in range(-LINE_PAD, LINE_PAD + 1)}
    clear_y = {y + dy for y in rws for dy in range(-LINE_PAD, LINE_PAD + 1)}
    edges = FEATHER[name]

    def paper_like(x, y):
        x = min(max(x, 0), w - 1); y = min(max(y, 0), h - 1)
        r, g, b = rows[y][x]; pp = paper_at(x, y)
        return max(abs(r - pp[0]), abs(g - pp[1]), abs(b - pp[2])) < KEY_HIGH

    out = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b = rows[y][x]
            pp = paper_at(x, y)
            dist = max(abs(r - pp[0]), abs(g - pp[1]), abs(b - pp[2]))
            a = min(1, max(0, (dist - KEY_LOW) / (KEY_HIGH - KEY_LOW)))
            if (r + g + b) > (pp[0] + pp[1] + pp[2]) + PETAL_LIFT:
                a = 1.0   # petals are lighter than paper: keep them solid so they cover the frame line
            # In the band: clear the line, its echo, its halo and the paper, but only where the
            # surroundings are paper. Where the line crosses a leaf or petal the mockup paints the
            # flower over it, so those pixels stay untouched.
            if x in clear_x and paper_like(x - OUTSIDE, y) and paper_like(x + OUTSIDE, y):
                a = 0
            if y in clear_y and paper_like(x, y - OUTSIDE) and paper_like(x, y + OUTSIDE):
                a = 0
            if "top" in edges:    a *= min(1, y / FEATHER_PX)
            if "bottom" in edges: a *= min(1, (h - 1 - y) / FEATHER_PX)
            if "left" in edges:   a *= min(1, x / FEATHER_PX)
            if "right" in edges:  a *= min(1, (w - 1 - x) / FEATHER_PX)
            row.append((r, g, b, round(a * 255)))
        out.append(row)
    write_png(SRC / f"{name}.png", w, h, out)
    print(f"{name}: {w}x{h} paper=#{paper[0]:02x}{paper[1]:02x}{paper[2]:02x} cleared cols={cols} rows={rws} (detected {detected})")


if __name__ == "__main__":
    for n in sys.argv[1:] or FEATHER:
        key(n)
