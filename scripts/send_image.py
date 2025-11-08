import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Optional
from PIL import Image, ImageOps
from bk_light.config import AppConfig, image_options, load_config
from bk_light.panel_manager import PanelManager


def parse_bool(value: Optional[bool]) -> Optional[bool]:
    return value if value is not None else None


def prepare_image(
    source: Path,
    canvas: tuple[int, int],
    mode: str,
    rotate: int,
    mirror: bool,
    invert: bool,
) -> Image.Image:
    image = Image.open(source).convert("RGB")
    if rotate:
        image = image.rotate(rotate % 360, expand=False)
    if mirror:
        image = ImageOps.mirror(image)
    if invert:
        image = ImageOps.invert(image)
    if mode == "fit":
        image = ImageOps.fit(image, canvas, method=Image.Resampling.LANCZOS)
    elif mode == "cover":
        image = ImageOps.fit(image, canvas, method=Image.Resampling.BICUBIC)
    else:
        image = image.resize(canvas, Image.Resampling.LANCZOS)
    return image


async def send_image(config: AppConfig, source: Path, preset_name: str, overrides: dict[str, Optional[str]]) -> None:
    preset = image_options(config, preset_name, overrides)
    rotate_override = overrides.get("rotate")
    mirror_override = overrides.get("mirror")
    invert_override = overrides.get("invert")
    mode = overrides.get("mode") or preset.mode
    rotate = int(rotate_override) if rotate_override is not None else preset.rotate
    mirror = bool(mirror_override) if mirror_override is not None else preset.mirror
    invert = bool(invert_override) if invert_override is not None else preset.invert
    async with PanelManager(config) as manager:
        canvas = manager.canvas_size
        image = prepare_image(source, canvas, mode, rotate, mirror, invert)
        await manager.send_image(image, delay=0.2)
        await asyncio.sleep(0.2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--address")
    parser.add_argument("--preset")
    parser.add_argument("--mode", choices=("scale", "fit", "cover"))
    parser.add_argument("--rotate", type=int)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--invert", action="store_true")
    return parser.parse_args()


def build_override_map(args: argparse.Namespace) -> dict[str, Optional[str]]:
    overrides: dict[str, Optional[str]] = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.rotate is not None:
        overrides["rotate"] = str(args.rotate)
    if args.mirror:
        overrides["mirror"] = True
    if args.invert:
        overrides["invert"] = True
    return overrides


if __name__ == "__main__":
    args = parse_args()
    config = load_config(args.config)
    if args.address:
        config.device = replace(config.device, address=args.address)
    preset_name = args.preset or config.runtime.preset or "default"
    overrides = build_override_map(args)
    asyncio.run(send_image(config, args.image, preset_name, overrides))

