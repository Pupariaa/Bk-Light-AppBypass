import asyncio
from io import BytesIO
from pathlib import Path
from typing import List
from bleak import BleakScanner
from PIL import Image, ImageOps
from display_session import BleDisplaySession

PREFIXES = ("LED_BLE_", "BK_LIGHT", "BJ_LED")


def build_logo_png() -> bytes:
    asset_path = Path(__file__).resolve().parent / "assets" / "bklight-boot.png"
    image = Image.open(asset_path).convert("RGB")
    fitted = ImageOps.fit(image, (32, 32), method=Image.Resampling.LANCZOS)
    buffer = BytesIO()
    fitted.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


async def scan_devices(timeout: float = 8.0) -> List:
    devices = await BleakScanner.discover(timeout=timeout)
    compatible = []
    seen = set()
    for device in devices:
        name = device.name or ""
        if any(name.startswith(prefix) for prefix in PREFIXES):
            if device.address not in seen:
                seen.add(device.address)
                compatible.append(device)
    return compatible


async def main() -> None:
    print("Scanning for BK-Light 32x32 displays...")
    devices = await scan_devices()
    if not devices:
        print("No compatible displays found.")
        return
    print("Compatible devices:")
    for index, device in enumerate(devices, start=1):
        print(f"{index}. {device.name} {device.address}")
    target = devices[0]
    print(f"Connecting to {target.name} {target.address}")
    try:
        async with BleDisplaySession(target.address) as session:
            png_bytes = build_logo_png()
            await session.send_png(png_bytes)
        print("Logo sent.")
    except Exception as error:
        print("ERROR", str(error))


if __name__ == "__main__":
    asyncio.run(main())

