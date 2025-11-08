import argparse
import asyncio
from io import BytesIO
from pathlib import Path
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


def load_font(path: Path | None, size: int) -> ImageFont.ImageFont:
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def build_png(text: str, color: tuple[int, int, int], background: tuple[int, int, int], font_path: Path | None, size: int, spacing: int) -> bytes:
    image = Image.new("RGB", (32, 32), background)
    draw = ImageDraw.Draw(image)
    font = load_font(font_path, size)
    formatted = text.replace("\\n", "\n")
    bbox = draw.multiline_textbbox((0, 0), formatted, font=font, spacing=spacing, align="center")
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    position = ((32 - width) / 2, (32 - height) / 2)
    draw.multiline_text(position, formatted, fill=color, font=font, spacing=spacing, align="center")
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


async def push_text(text: str, color: tuple[int, int, int], background: tuple[int, int, int], font_path: Path | None, size: int, spacing: int, address: str | None) -> None:
    png_bytes = build_png(text, color, background, font_path, size, spacing)
    try:
        async with BleDisplaySession(address) as session:
            await session.send_png(png_bytes)
        print("DONE")
    except Exception as error:
        print("ERROR", str(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("--color", default="#FF0000")
    parser.add_argument("--background", default="#000000")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--size", type=int, default=16)
    parser.add_argument("--spacing", type=int, default=1)
    parser.add_argument("--address")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        push_text(
            args.text,
            parse_color(args.color),
            parse_color(args.background),
            args.font,
            args.size,
            args.spacing,
            args.address,
        )
    )

