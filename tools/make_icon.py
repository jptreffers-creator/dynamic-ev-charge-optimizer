"""Generates the brand icon.

Kept in the repository so the icon is reproducible rather than a binary nobody
can edit: change a colour or a bar height here and re-run. Home Assistant reads
the result from custom_components/ev_charge_planner/brand/.

    python tools/make_icon.py

The mark is a price profile. Six settlement periods, the two cheapest picked out
in amber: that is the whole integration in one picture — it looks at the day's
prices and charges in the valleys.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

CANVAS = 1024
TEAL = (15, 110, 92, 255)
AMBER = (245, 166, 35, 255)

#: Height of each bar, and whether it is one of the cheap ones we charge in.
PROFILE = (
    (0.86, False),
    (0.62, False),
    (0.30, True),
    (0.22, True),
    (0.48, False),
    (0.74, False),
)

OUT = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "ev_charge_planner" / "brand"
)


def render() -> Image.Image:
    im = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    left, right, bottom = 0.02, 0.98, 0.98
    span = (right - left) / len(PROFILE)
    width = span * 0.78
    for i, (height, cheap) in enumerate(PROFILE):
        x = left + i * span
        draw.rounded_rectangle(
            [x * CANVAS, (bottom - height * bottom) * CANVAS,
             (x + width) * CANVAS, bottom * CANVAS],
            radius=width * CANVAS * 0.42,
            fill=AMBER if cheap else TEAL,
        )
    return im


def main() -> None:
    im = render()
    im = im.crop(im.getbbox())
    w, h = im.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(im, ((side - w) // 2, (side - h) // 2))

    OUT.mkdir(parents=True, exist_ok=True)
    square.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png", optimize=True)
    square.resize((512, 512), Image.LANCZOS).save(OUT / "icon@2x.png", optimize=True)
    # Small preview, enlarged without smoothing, to judge legibility in a list.
    square.resize((40, 40), Image.LANCZOS).resize((240, 240), Image.NEAREST).save(
        Path(__file__).resolve().parent / "icon-preview.png"
    )
    print(f"written to {OUT}")


if __name__ == "__main__":
    main()
