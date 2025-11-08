import argparse
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from display_session import BleDisplaySession


def build_png(value: int) -> bytes:
    image = Image.new("RGB", (32, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    text = str(value)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    position = ((32 - width) / 2, (32 - height) / 2)
    draw.text(position, text, fill=(255, 0, 0), font=font)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


async def run_counter(start: int, count: int, delay: float, address: str | None) -> None:
    try:
        async with BleDisplaySession(address) as session:
            value = start
            for _ in range(count):
                print("SENDING", value)
                await session.send_png(build_png(value))
                value += 1
                await asyncio.sleep(delay)
    except Exception as error:
        print("ERROR", str(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--address")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_counter(args.start, args.count, args.delay, args.address))

