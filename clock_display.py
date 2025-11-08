import argparse
import asyncio
import math
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from display_session import BleDisplaySession


def parse_color(value: Optional[str]) -> Optional[tuple[int, int, int]]:
    if value is None:
        return None
    cleaned = value.replace("#", "").replace(" ", "")
    if "," in cleaned:
        parts = cleaned.split(",")
        return tuple(int(part) for part in parts[:3])
    if len(cleaned) == 6:
        return tuple(int(cleaned[i:i + 2], 16) for i in (0, 2, 4))
    raise ValueError("Invalid color")


def load_font(path: Optional[Path], size: int) -> ImageFont.ImageFont:
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def build_background(background: tuple[int, int, int], accent: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (32, 32), background)
    pixels = image.load()
    center = (15.5, 15.5)
    max_distance = math.sqrt(15.5 ** 2 * 2)
    for y in range(32):
        for x in range(32):
            distance = math.dist((x, y), center) / max_distance
            mix = max(0.0, min(1.0, distance))
            r = int(background[0] * (1 - mix) + accent[0] * mix)
            g = int(background[1] * (1 - mix) + accent[1] * mix)
            b = int(background[2] * (1 - mix) + accent[2] * mix)
            pixels[x, y] = (r, g, b)
    return image


def build_clock_png(now: datetime, color: tuple[int, int, int], accent: tuple[int, int, int], background: tuple[int, int, int], font_path: Optional[Path], size: int) -> bytes:
    base = build_background(background, accent)
    draw = ImageDraw.Draw(base)
    font = load_font(font_path, size)
    text = now.strftime("%H:%M")
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    origin_x = (32 - width) / 2 - bbox[0]
    origin_y = (32 - height) / 2 - bbox[1]
    light_color = tuple(min(255, int(channel * 1.1)) for channel in color)
    draw.text((origin_x, origin_y), text, fill=light_color, font=font)
    left_width = draw.textlength(text[:2], font=font)
    colon_width = draw.textlength(":", font=font)
    spacing = max(1.0, size * 0.06)
    colon_x = origin_x + left_width + colon_width / 2 + spacing
    digit_bbox = draw.textbbox((0, 0), "0", font=font)
    digit_height = digit_bbox[3] - digit_bbox[1]
    baseline = origin_y + digit_bbox[1] + digit_height / 2
    gap = digit_height * 0.32
    dot_radius = max(1.2, digit_height * 0.1)
    top_y = baseline - gap
    bottom_y = baseline + gap
    draw.ellipse((colon_x - dot_radius, top_y - dot_radius, colon_x + dot_radius, top_y + dot_radius), fill=accent)
    draw.ellipse((colon_x - dot_radius, bottom_y - dot_radius, colon_x + dot_radius, bottom_y + dot_radius), fill=accent)
    buffer = BytesIO()
    base.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def resolve_timezone(tz_name: Optional[str]) -> timezone:
    if not tz_name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        return datetime.now().astimezone().tzinfo or timezone.utc


def resolve_palette(theme: str, color: Optional[tuple[int, int, int]], accent: Optional[tuple[int, int, int]], background: Optional[tuple[int, int, int]]) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    palettes = {
        "dark": (
            (226, 232, 255),   # text
            (110, 125, 255),   # accent
            (7, 9, 18),        # background base
        ),
        "neon": (
            (240, 255, 255),
            (0, 255, 180),
            (5, 10, 18),
        ),
        "warm": (
            (255, 244, 230),
            (255, 153, 102),
            (12, 6, 2),
        ),
    }
    default_color, default_accent, default_background = palettes.get(theme, palettes["dark"])
    return (
        color or default_color,
        accent or default_accent,
        background or default_background,
    )


async def run_clock(address: Optional[str], color: Optional[tuple[int, int, int]], accent: Optional[tuple[int, int, int]], background: Optional[tuple[int, int, int]], font_path: Optional[Path], size: int, interval: float, tz_name: Optional[str], theme: str) -> None:
    tz = resolve_timezone(tz_name)
    resolved_color, resolved_accent, resolved_background = resolve_palette(theme, color, accent, background)
    previous = ""
    try:
        async with BleDisplaySession(address) as session:
            while True:
                now = datetime.now(tz)
                stamp = now.strftime("%H:%M")
                if stamp != previous:
                    png_bytes = build_clock_png(now, resolved_color, resolved_accent, resolved_background, font_path, size)
                    await session.send_png(png_bytes)
                    previous = stamp
                await asyncio.sleep(interval)
    except Exception as error:
        print("ERROR", str(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address")
    parser.add_argument("--color")
    parser.add_argument("--accent")
    parser.add_argument("--background")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--size", type=int, default=20)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--timezone")
    parser.add_argument("--theme", choices=("dark", "neon", "warm"), default="dark")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run_clock(
            args.address,
            parse_color(args.color),
            parse_color(args.accent),
            parse_color(args.background),
            args.font,
            args.size,
            args.interval,
            args.timezone,
            args.theme,
        )
    )

