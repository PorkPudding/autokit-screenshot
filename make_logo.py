"""
Generate the D.A.D's A.Ss logo + exe icon in a Dark-and-Darker-ish style:
chiseled gold capitals, dark outline, weathered texture.

Outputs:
    assets/logo.png      — wide transparent logo for the GUI header / README
    assets/icon.ico      — multi-size icon for the exe

Run after changing: python make_logo.py
"""
import numpy as np
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONT = ASSETS / "fonts" / "CinzelDecorative-Black.ttf"
TAG_FONT = ASSETS / "fonts" / "Cinzel-VF.ttf"

# Weathered-gold palette sampled off the Dark and Darker title treatment
GOLD_TOP = (244, 233, 200)
GOLD_MID = (201, 168, 102)
GOLD_LOW = (128, 95, 48)
GOLD_DEEP = (84, 60, 28)
OUTLINE = (22, 14, 6)
TAG_COLOR = (158, 138, 96)

SS = 4  # supersample factor


def _gradient_fill(size, alpha_mask):
    """Vertical gold gradient masked by the text alpha."""
    w, h = size
    rows = []
    stops = [(0.0, GOLD_TOP), (0.42, GOLD_MID), (0.75, GOLD_LOW), (1.0, GOLD_DEEP)]
    for y in range(h):
        t = y / max(1, h - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                rows.append(tuple(round(a + (b - a) * f) for a, b in zip(c0, c1)))
                break
    grad = np.array(rows, dtype=np.uint8)[:, None, :].repeat(w, axis=1)
    out = Image.fromarray(grad, "RGB").convert("RGBA")
    out.putalpha(alpha_mask)
    return out


def _grunge(img, seed=7, strength=70):
    """Speckled wear: darken random blotches inside the lettering."""
    rng = np.random.default_rng(seed)
    w, h = img.size
    noise = rng.random((h // 6, w // 6)).astype(np.float32)
    noise_img = Image.fromarray((noise * 255).astype(np.uint8), "L")
    noise_img = noise_img.resize((w, h), Image.BILINEAR).filter(
        ImageFilter.GaussianBlur(2 * SS))
    n = np.asarray(noise_img, dtype=np.float32) / 255.0
    # only the darkest blotches eat into the gold
    wear = np.clip((0.45 - n) / 0.45, 0, 1) * (strength / 255.0)

    arr = np.asarray(img, dtype=np.float32)
    arr[:, :, :3] *= (1.0 - wear[:, :, None])
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def render_text(text, font_px, pad=None):
    """Render one line of chiseled-gold text, transparent background."""
    font = ImageFont.truetype(str(FONT), font_px * SS)
    if pad is None:
        pad = font_px // 3
    pad *= SS

    probe = Image.new("L", (8, 8))
    d = ImageDraw.Draw(probe)
    x0, y0, x1, y1 = d.textbbox((0, 0), text, font=font)
    w = (x1 - x0) + 2 * pad
    h = (y1 - y0) + 2 * pad
    origin = (pad - x0, pad - y0)

    # text alpha mask
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text(origin, text, font=font, fill=255)

    # drop shadow
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh_mask = mask.filter(ImageFilter.GaussianBlur(3 * SS))
    black = Image.new("RGBA", (w, h), (0, 0, 0, 230))
    shadow.paste(black, (2 * SS, 3 * SS), sh_mask)

    # outline: stroke render slightly larger, in near-black
    outline = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(outline).text(origin, text, font=font,
                                 fill=OUTLINE + (255,),
                                 stroke_width=max(1, font_px * SS // 28))

    # gold body with bevel: light pass nudged up-left, dark pass down-right
    gold = _gradient_fill((w, h), mask)
    bevel_hi = Image.new("RGBA", (w, h), (255, 248, 222, 110))
    hi_mask = mask.copy().transform(mask.size, Image.AFFINE,
                                    (1, 0, 1.2 * SS, 0, 1, 1.2 * SS))
    hi_only = Image.composite(Image.new("L", mask.size, 255),
                              Image.new("L", mask.size, 0), mask)
    hi_edge = np.asarray(hi_only, dtype=np.int16) - np.asarray(hi_mask, dtype=np.int16)
    hi_edge = Image.fromarray(np.clip(hi_edge, 0, 255).astype(np.uint8), "L")
    gold.paste(bevel_hi, (0, 0), hi_edge)

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out = Image.alpha_composite(out, shadow)
    out = Image.alpha_composite(out, outline)
    out = Image.alpha_composite(out, gold)
    out = _grunge(out)
    return out


def make_logo():
    title = render_text("D.A.D's A.Ss", 110)

    # tagline in lighter letterspaced caps
    tag_text = "D A R K   A N D   D A R K E R   A U T O   S C R E E N S H O T"
    tag_font = ImageFont.truetype(str(TAG_FONT), 17 * SS)
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    tb = probe.textbbox((0, 0), tag_text, font=tag_font)
    tag_w, tag_h = tb[2] - tb[0], tb[3] - tb[1]

    w = max(title.width, tag_w + 40 * SS)
    h = title.height + tag_h + 14 * SS
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(title, ((w - title.width) // 2, 0), title)
    d = ImageDraw.Draw(canvas)
    d.text(((w - tag_w) // 2 - tb[0], title.height + 2 * SS - tb[1]),
           tag_text, font=tag_font, fill=TAG_COLOR + (255,))

    canvas = canvas.resize((w // SS, h // SS), Image.LANCZOS)
    canvas.save(ASSETS / "logo.png")
    print(f"logo.png  {canvas.size}")


def make_icon():
    line1 = render_text("D.A.D's", 96)
    line2 = render_text("A.Ss", 96)

    side = max(line1.width, line2.width, line1.height + line2.height) + 24 * SS
    bg = Image.new("RGBA", (side, side), (16, 14, 20, 255))
    # subtle vignette ring border
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([3 * SS, 3 * SS, side - 3 * SS, side - 3 * SS],
                        radius=side // 8, outline=GOLD_LOW + (255,), width=2 * SS)

    gap = 2 * SS
    total_h = line1.height + gap + line2.height
    y = (side - total_h) // 2
    bg.paste(line1, ((side - line1.width) // 2, y), line1)
    bg.paste(line2, ((side - line2.width) // 2, y + line1.height + gap), line2)

    # round the canvas corners so the taskbar icon isn't a hard square
    corner_mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(corner_mask).rounded_rectangle(
        [0, 0, side, side], radius=side // 8, fill=255)
    bg.putalpha(corner_mask)

    icon = bg.resize((256, 256), Image.LANCZOS)
    icon.save(ASSETS / "icon.ico",
              sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    icon.save(ASSETS / "icon_preview.png")
    print(f"icon.ico  (256..16) + icon_preview.png")


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    make_logo()
    make_icon()
