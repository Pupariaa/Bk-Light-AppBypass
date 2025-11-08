import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from bk_light.config import AppConfig, counter_options, load_config, text_options
from bk_light.panel_manager import PanelManager


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


def build_counter_image(
    canvas: tuple[int, int],
    value: int,
    color: tuple[int, int, int],
    background: tuple[int, int, int],
    font_path: Optional[Path],
    size: int,
) -> Image.Image:
    image = Image.new("RGB", canvas, background)
    draw = ImageDraw.Draw(image)
    font = load_font(font_path, size)
    text = str(value)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    origin = ((canvas[0] - width) / 2, (canvas[1] - height) / 2)
    draw.text(origin, text, fill=color, font=font)
    return image


async def run_counter(config: AppConfig, preset_name: str, overrides: dict[str, Optional[str]]) -> None:
    counter_preset = counter_options(config, preset_name, overrides)
    text_preset = text_options(config, preset_name, {})
    color = parse_color(text_preset.color)
    background = parse_color(text_preset.background)
    font_path = Path(text_preset.font) if text_preset.font else None
    size = text_preset.size
    start = overrides.get("start")
    count = overrides.get("count")
    delay = overrides.get("delay")
    start_value = int(start) if start is not None else counter_preset.start
    total = int(count) if count is not None else counter_preset.count
    interval = float(delay) if delay is not None else counter_preset.delay
    async with PanelManager(config) as manager:
        canvas = manager.canvas_size
        value = start_value
        for _ in range(total):
            image = build_counter_image(canvas, value, color, background, font_path, size)
            await manager.send_image(image, delay=0.15)
            value += 1
            await asyncio.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--address")
    parser.add_argument("--preset")
    parser.add_argument("--start", type=int)
    parser.add_argument("--count", type=int)
    parser.add_argument("--delay", type=float)
    return parser.parse_args()


def build_override_map(args: argparse.Namespace) -> dict[str, Optional[str]]:
    overrides: dict[str, Optional[str]] = {}
    if args.start is not None:
        overrides["start"] = str(args.start)
    if args.count is not None:
        overrides["count"] = str(args.count)
    if args.delay is not None:
        overrides["delay"] = str(args.delay)
    return overrides


if __name__ == "__main__":
    args = parse_args()
    config = load_config(args.config)
    if args.address:
        config.device = replace(config.device, address=args.address)
    preset_name = args.preset or config.runtime.preset or "default"
    overrides = build_override_map(args)
    asyncio.run(run_counter(config, preset_name, overrides))

