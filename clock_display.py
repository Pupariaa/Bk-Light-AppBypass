import argparse
import asyncio
import math
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from display_session import BleDisplaySession


def parse_color(value: str) -> tuple[int, int, int]:
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
    shadow_color = tuple(max(0, channel - 40) for channel in color)
    draw.text((origin_x + 1, origin_y + 1), text, fill=shadow_color, font=font)
    draw.text((origin_x, origin_y), text, fill=color, font=font)
    left_width = draw.textlength(text[:2], font=font)
    colon_width = draw.textlength(":", font=font)
    colon_x = origin_x + left_width + colon_width / 2
    digit_bbox = draw.textbbox((0, 0), "0", font=font)
    digit_height = digit_bbox[3] - digit_bbox[1]
    baseline = origin_y + digit_bbox[1] + digit_height / 2
    gap = digit_height * 0.28
    dot_radius = max(1.5, digit_height * 0.12)
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


async def run_clock(address: Optional[str], color: tuple[int, int, int], accent: tuple[int, int, int], background: tuple[int, int, int], font_path: Optional[Path], size: int, interval: float, tz_name: Optional[str]) -> None:
    tz = resolve_timezone(tz_name)
    previous = ""
    try:
        async with BleDisplaySession(address) as session:
            while True:
                now = datetime.now(tz)
                stamp = now.strftime("%H:%M")
                if stamp != previous:
                    png_bytes = build_clock_png(now, color, accent, background, font_path, size)
                    await session.send_png(png_bytes)
                    previous = stamp
                await asyncio.sleep(interval)
    except Exception as error:
        print("ERROR", str(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address")
    parser.add_argument("--color", default="#FFFFFF")
    parser.add_argument("--accent", default="#FF2C75")
    parser.add_argument("--background", default="#120510")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--size", type=int, default=20)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--timezone")
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
        )
    )

