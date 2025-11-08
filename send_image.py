import argparse
import asyncio
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from display_session import BleDisplaySession


def build_png(path: Path, mode: str, rotate: int, mirror: bool, invert: bool) -> bytes:
    image = Image.open(path).convert("RGB")
    if rotate:
        image = image.rotate(rotate % 360, expand=False)
    if mirror:
        image = ImageOps.mirror(image)
    if invert:
        image = ImageOps.invert(image)
    if mode == "fit":
        image = ImageOps.fit(image, (32, 32))
    elif mode == "cover":
        image = ImageOps.fit(image, (32, 32), method=Image.Resampling.BICUBIC)
    else:
        image = image.resize((32, 32), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


async def push_image(path: Path, mode: str, rotate: int, mirror: bool, invert: bool, address: str | None) -> None:
    png_bytes = build_png(path, mode, rotate, mirror, invert)
    try:
        async with BleDisplaySession(address) as session:
            await session.send_png(png_bytes)
        print("DONE")
    except Exception as error:
        print("ERROR", str(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--mode", choices=("scale", "fit", "cover"), default="scale")
    parser.add_argument("--rotate", type=int, default=0)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--address")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(push_image(args.image, args.mode, args.rotate, args.mirror, args.invert, args.address))

