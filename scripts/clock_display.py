import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from bk_light.config import AppConfig, clock_options, load_config
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


def resolve_timezone(config: AppConfig, override: Optional[str]) -> timezone:
    tz_name = override or config.device.timezone
    if not tz_name or tz_name == "auto":
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        return datetime.now().astimezone().tzinfo or timezone.utc


def build_clock_image(
    canvas: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    accent: tuple[int, int, int],
    background: tuple[int, int, int],
    font_path: Optional[Path],
    size: int,
    colon_visible: bool,
) -> Image.Image:
    image = Image.new("RGB", canvas, background)
    draw = ImageDraw.Draw(image)
    font = load_font(font_path, size)
    display_text = text if colon_visible else text.replace(":", " ")
    bbox = draw.textbbox((0, 0), display_text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    origin_x = (canvas[0] - width) / 2 - bbox[0]
    origin_y = (canvas[1] - height) / 2 - bbox[1]
    draw.text((origin_x, origin_y), display_text, fill=color, font=font)
    if colon_visible and ":" in text:
        left = text.split(":")[0]
        left_width = draw.textlength(left, font=font)
        colon_x = origin_x + left_width + 1.5
        digit_bbox = draw.textbbox((0, 0), "0", font=font)
        digit_height = digit_bbox[3] - digit_bbox[1]
        baseline = origin_y + digit_bbox[1] + digit_height / 2
        gap = digit_height * 0.35
        top = int(round(baseline - gap))
        bottom = int(round(baseline + gap))
        draw.point((int(round(colon_x)), top), fill=accent)
        draw.point((int(round(colon_x)), bottom), fill=accent)
    return image


async def run_clock(config: AppConfig, preset_name: str, overrides: dict[str, Optional[str]]) -> None:
    preset = clock_options(config, preset_name, overrides)
    tz = resolve_timezone(config, overrides.get("timezone"))
    color = parse_color(overrides.get("color")) or parse_color(preset.color)
    accent = parse_color(overrides.get("accent")) or parse_color(preset.accent)
    background = parse_color(overrides.get("background")) or parse_color(preset.background)
    font_path = Path(overrides["font"]) if overrides.get("font") else Path(preset.font) if preset.font else None
    interval = preset.interval
    dot_flashing = preset.dot_flashing
    flash_period = preset.dot_flash_period
    last_stamp = ""
    last_colon = True
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    async with PanelManager(config) as manager:
        canvas = manager.canvas_size
        while True:
            now = datetime.now(tz)
            if preset.format == "12h":
                stamp = now.strftime("%I:%M")
                if stamp.startswith("0"):
                    stamp = stamp[1:]
            else:
                stamp = now.strftime("%H:%M")
            elapsed = loop.time() - start_time
            colon_visible = True
            if dot_flashing:
                colon_visible = int(elapsed / flash_period) % 2 == 0
            if stamp != last_stamp or colon_visible != last_colon:
                image = build_clock_image(
                    canvas,
                    stamp,
                    color,
                    accent,
                    background,
                    font_path,
                    preset.size,
                    colon_visible,
                )
                await manager.send_image(image, delay=0.15)
                last_stamp = stamp
                last_colon = colon_visible
            await asyncio.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--address")
    parser.add_argument("--preset")
    parser.add_argument("--timezone")
    parser.add_argument("--format", choices=("12h", "24h"))
    parser.add_argument("--color")
    parser.add_argument("--accent")
    parser.add_argument("--background")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--size", type=int)
    parser.add_argument("--interval", type=float)
    parser.add_argument("--dot-flashing", choices=("on", "off"))
    parser.add_argument("--dot-flash-period", type=float)
    return parser.parse_args()


def build_override_map(args: argparse.Namespace) -> dict[str, Optional[str]]:
    overrides: dict[str, Optional[str]] = {
        "timezone": args.timezone,
        "format": args.format,
        "color": args.color,
        "accent": args.accent,
        "background": args.background,
        "font": str(args.font) if args.font else None,
        "size": args.size,
        "interval": args.interval,
        "dot_flash_period": args.dot_flash_period,
    }
    if args.dot_flashing == "on":
        overrides["dot_flashing"] = True
    elif args.dot_flashing == "off":
        overrides["dot_flashing"] = False
    return overrides


if __name__ == "__main__":
    args = parse_args()
    config = load_config(args.config)
    if args.address:
        config.device = replace(config.device, address=args.address)
    preset_name = args.preset or config.runtime.preset or "default"
    overrides = build_override_map(args)
    asyncio.run(run_clock(config, preset_name, overrides))

