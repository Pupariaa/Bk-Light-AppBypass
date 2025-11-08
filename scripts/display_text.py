import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from bk_light.config import AppConfig, load_config, text_options
from bk_light.panel_manager import PanelManager


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


def build_text_image(
    canvas: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    background: tuple[int, int, int],
    font_path: Optional[Path],
    size: int,
    spacing: int,
) -> Image.Image:
    image = Image.new("RGB", canvas, background)
    draw = ImageDraw.Draw(image)
    font = load_font(font_path, size)
    formatted = text.replace("\\n", "\n")
    bbox = draw.multiline_textbbox((0, 0), formatted, font=font, spacing=spacing, align="center")
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    origin = ((canvas[0] - width) / 2, (canvas[1] - height) / 2)
    draw.multiline_text(origin, formatted, fill=color, font=font, spacing=spacing, align="center")
    return image


async def display_text(config: AppConfig, message: str, preset_name: str, overrides: dict[str, Optional[str]]) -> None:
    preset = text_options(config, preset_name, overrides)
    color = parse_color(overrides.get("color")) or parse_color(preset.color)
    background = parse_color(overrides.get("background")) or parse_color(preset.background)
    font_path = Path(overrides["font"]) if overrides.get("font") else Path(preset.font) if preset.font else None
    size = overrides.get("size") or preset.size
    spacing = overrides.get("spacing") or preset.spacing
    size = int(size)
    spacing = int(spacing)
    async with PanelManager(config) as manager:
        canvas = manager.canvas_size
        image = build_text_image(canvas, message, color, background, font_path, size, spacing)
        await manager.send_image(image, delay=0.15)
        await asyncio.sleep(0.2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--address")
    parser.add_argument("--preset")
    parser.add_argument("--color")
    parser.add_argument("--background")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--size", type=int)
    parser.add_argument("--spacing", type=int)
    return parser.parse_args()


def build_override_map(args: argparse.Namespace) -> dict[str, Optional[str]]:
    return {
        "color": args.color,
        "background": args.background,
        "font": str(args.font) if args.font else None,
        "size": args.size,
        "spacing": args.spacing,
    }


if __name__ == "__main__":
    args = parse_args()
    config = load_config(args.config)
    if args.address:
        config.device = replace(config.device, address=args.address)
    preset_name = args.preset or config.runtime.preset or "default"
    overrides = build_override_map(args)
    asyncio.run(display_text(config, args.text, preset_name, overrides))

