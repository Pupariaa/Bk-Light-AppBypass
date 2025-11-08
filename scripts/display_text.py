import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

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


def build_text_bitmap(text: str, font_path: Optional[Path], size: int, spacing: int, color: tuple[int, int, int]) -> Image.Image:
    font = load_font(font_path, size)
    formatted = text.replace("\\n", "\n")
    dummy = Image.new("L", (1, 1), 0)
    draw = ImageDraw.Draw(dummy)
    bbox = draw.multiline_textbbox((0, 0), formatted, font=font, spacing=spacing, align="left")
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    bitmap = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    draw_bitmap = ImageDraw.Draw(bitmap)
    draw_bitmap.multiline_text((-bbox[0], -bbox[1]), formatted, fill=(*color, 255), font=font, spacing=spacing, align="left")
    return bitmap


def render_static_frame(
    canvas: tuple[int, int],
    text_bitmap: Image.Image,
    background: tuple[int, int, int],
    offset_x: int,
    offset_y: int,
) -> Image.Image:
    frame = Image.new("RGBA", canvas, tuple(background) + (255,))
    x = (canvas[0] - text_bitmap.width) // 2 + offset_x
    y = (canvas[1] - text_bitmap.height) // 2 + offset_y
    frame.paste(text_bitmap, (x, y), text_bitmap)
    return frame.convert("RGB")


def render_scroll_frame(
    canvas: tuple[int, int],
    text_bitmap: Image.Image,
    background: tuple[int, int, int],
    direction: str,
    speed: float,
    gap: int,
    offset_x: int,
    offset_y: int,
    elapsed: float,
) -> Image.Image:
    strip_width = max(1, text_bitmap.width + gap)
    strip = Image.new("RGBA", (strip_width, canvas[1]), tuple(background) + (255,))
    y = (canvas[1] - text_bitmap.height) // 2 + offset_y
    strip.paste(text_bitmap, (0, y), text_bitmap)
    shift = int((elapsed * speed) % strip_width)
    base = offset_x - shift if direction == "left" else offset_x + shift
    frame = Image.new("RGBA", canvas, tuple(background) + (255,))
    x = base
    while x > -strip_width:
        x -= strip_width
    while x < canvas[0]:
        frame.paste(strip, (int(x), 0), strip)
        x += strip_width
    return frame.convert("RGB")


async def display_text(config: AppConfig, message: str, preset_name: str, overrides: dict[str, Optional[str]]) -> None:
    preset = text_options(config, preset_name, overrides)
    color = parse_color(overrides.get("color")) or parse_color(preset.color)
    background = parse_color(overrides.get("background")) or parse_color(preset.background)
    font_path = Path(overrides["font"]) if overrides.get("font") else Path(preset.font) if preset.font else None
    text_bitmap = build_text_bitmap(message, font_path, preset.size, preset.spacing, color)
    try:
        async with PanelManager(config) as manager:
            canvas = manager.canvas_size
            if preset.mode == "scroll":
                loop = asyncio.get_running_loop()
                start = loop.time()
                while True:
                    elapsed = loop.time() - start
                    frame = render_scroll_frame(
                        canvas,
                        text_bitmap,
                        background,
                        preset.direction,
                        preset.speed,
                        preset.gap,
                        preset.offset_x,
                        preset.offset_y,
                        elapsed,
                    )
                    await manager.send_image(frame, delay=0.1)
                    await asyncio.sleep(preset.interval)
            else:
                frame = render_static_frame(
                    canvas,
                    text_bitmap,
                    background,
                    preset.offset_x,
                    preset.offset_y,
                )
                await manager.send_image(frame, delay=0.15)
                await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        print("ERROR", str(error))


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
    parser.add_argument("--mode", choices=("static", "scroll"))
    parser.add_argument("--direction", choices=("left", "right"))
    parser.add_argument("--speed", type=float)
    parser.add_argument("--gap", type=int)
    parser.add_argument("--offset-x", type=int)
    parser.add_argument("--offset-y", type=int)
    parser.add_argument("--interval", type=float)
    return parser.parse_args()


def build_override_map(args: argparse.Namespace) -> dict[str, Optional[str]]:
    return {
        "color": args.color,
        "background": args.background,
        "font": str(args.font) if args.font else None,
        "size": args.size,
        "spacing": args.spacing,
        "mode": args.mode,
        "direction": args.direction,
        "speed": args.speed,
        "gap": args.gap,
        "offset_x": args.offset_x,
        "offset_y": args.offset_y,
        "interval": args.interval,
    }


if __name__ == "__main__":
    args = parse_args()
    config = load_config(args.config)
    if args.address:
        config.device = replace(config.device, address=args.address)
    preset_name = args.preset or config.runtime.preset or "default"
    overrides = build_override_map(args)
    try:
        asyncio.run(display_text(config, args.text, preset_name, overrides))
    except KeyboardInterrupt:
        pass

