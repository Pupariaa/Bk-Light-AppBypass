import argparse
import asyncio
from io import BytesIO
from PIL import Image
from bk_light.display_session import BleDisplaySession


def build_png() -> bytes:
    image = Image.new("RGB", (32, 32), (0, 0, 0))
    width, height = image.size
    corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
    for x, y in corners:
        image.putpixel((x, y), (255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


async def push_red_corners(address: str | None) -> None:
    try:
        async with BleDisplaySession(address) as session:
            await session.send_png(build_png())
        print("DONE")
    except Exception as error:
        print("ERROR", str(error))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--address")
    args = parser.parse_args()
    asyncio.run(push_red_corners(args.address))

