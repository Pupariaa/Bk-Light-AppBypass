import asyncio
import binascii
import os
from io import BytesIO
from typing import Optional
from bleak import BleakClient
from PIL import Image, ImageEnhance

DEFAULT_ADDRESS = os.getenv("BK_LIGHT_ADDRESS")
UUID_WRITE = "0000fa02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "0000fa03-0000-1000-8000-00805f9b34fb"
HANDSHAKE_FIRST = bytes.fromhex("08 00 01 80 0E 06 32 00")
HANDSHAKE_SECOND = bytes.fromhex("04 00 05 80")
ACK_STAGE_ONE = bytes.fromhex("0C 00 01 80 81 06 32 00 00 01 00 01")
ACK_STAGE_TWO = bytes.fromhex("08 00 05 80 0B 03 07 02")
ACK_STAGE_THREE = bytes.fromhex("05 00 02 00 03")
FRAME_VALIDATION = bytes.fromhex("05 00 00 01 00")


def bytes_to_hex(data: bytes) -> str:
    return "-".join(f"{value:02X}" for value in data)


def build_frame(png_bytes: bytes) -> bytes:
    data_length = len(png_bytes)
    total_length = data_length + 15
    frame = bytearray()
    frame += total_length.to_bytes(2, "little")
    frame.append(0x02)
    frame += b"\x00\x00"
    frame += data_length.to_bytes(2, "little")
    frame += b"\x00\x00"
    frame += binascii.crc32(png_bytes).to_bytes(4, "little")
    frame += b"\x00\x65"
    frame += png_bytes
    return bytes(frame)


def adjust_image(png_bytes: bytes, rotation: int, brightness: float) -> bytes:
    image = Image.open(BytesIO(png_bytes)).convert("RGB")
    if rotation:
        image = image.rotate(rotation, expand=False)
    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(brightness)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


class AckWatcher:
    def __init__(self, verbose: bool) -> None:
        self.stage_one = asyncio.Event()
        self.stage_two = asyncio.Event()
        self.stage_three = asyncio.Event()
        self.verbose = verbose

    def reset(self) -> None:
        self.stage_one.clear()
        self.stage_two.clear()
        self.stage_three.clear()

    def handler(self, _sender: int, data: bytearray) -> None:
        payload = bytes(data)
        if self.verbose:
            print("NOTIF", bytes_to_hex(payload))
        if payload == ACK_STAGE_ONE:
            self.stage_one.set()
        elif payload == ACK_STAGE_TWO:
            self.stage_two.set()
        elif payload == ACK_STAGE_THREE:
            self.stage_three.set()


async def wait_for_ack(event: asyncio.Event, label: str, verbose: bool) -> None:
    try:
        await asyncio.wait_for(event.wait(), timeout=5.0)
        if verbose:
            print(label + "_OK")
    except asyncio.TimeoutError:
        print(label + "_TIMEOUT")


class BleDisplaySession:
    def __init__(
        self,
        address: Optional[str] = None,
        auto_reconnect: bool = True,
        reconnect_delay: float = 2.0,
        rotation: int = 0,
        brightness: float = 1.0,
        mtu: int = 512,
        log_notifications: bool = False,
    ) -> None:
        resolved = address or DEFAULT_ADDRESS
        if not resolved:
            raise ValueError("Missing target address. Pass it explicitly or set BK_LIGHT_ADDRESS.")
        self.address = resolved
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.rotation = rotation
        self.brightness = brightness
        self.mtu = mtu
        self.log_notifications = log_notifications
        self.client = BleakClient(resolved)
        self.watcher = AckWatcher(log_notifications)

    async def _connect(self) -> None:
        while True:
            try:
                await self.client.connect()
                if not self.client.is_connected:
                    raise ConnectionError("Bluetooth link failed")
                if self.mtu:
                    try:
                        await self.client.exchange_mtu(self.mtu)
                    except Exception:
                        pass
                await self.client.start_notify(UUID_NOTIFY, self.watcher.handler)
                return
            except Exception as error:
                if not self.auto_reconnect:
                    raise error
                await asyncio.sleep(self.reconnect_delay)

    async def __aenter__(self) -> "BleDisplaySession":
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self.client.is_connected:
                await self.client.stop_notify(UUID_NOTIFY)
                await asyncio.sleep(0.2)
        finally:
            await self.client.disconnect()

    async def send_png(self, png_bytes: bytes, delay: float = 0.2) -> None:
        processed = adjust_image(png_bytes, self.rotation, self.brightness)
        frame = build_frame(processed)
        await self.send_frame(frame, delay)

    async def send_frame(self, frame: bytes, delay: float = 0.2) -> None:
        try:
            self.watcher.reset()
            await self.client.write_gatt_char(UUID_WRITE, HANDSHAKE_FIRST, response=False)
            await wait_for_ack(self.watcher.stage_one, "HANDSHAKE_STAGE_ONE", self.log_notifications)
            await asyncio.sleep(delay)
            self.watcher.stage_two.clear()
            await self.client.write_gatt_char(UUID_WRITE, HANDSHAKE_SECOND, response=False)
            await wait_for_ack(self.watcher.stage_two, "HANDSHAKE_STAGE_TWO", self.log_notifications)
            await asyncio.sleep(delay)
            await self.client.write_gatt_char(UUID_WRITE, frame, response=True)
            await wait_for_ack(self.watcher.stage_three, "FRAME_ACK", self.log_notifications)
            await asyncio.sleep(delay)
            await self.client.write_gatt_char(UUID_WRITE, FRAME_VALIDATION, response=False)
        except Exception:
            if self.auto_reconnect:
                await asyncio.sleep(self.reconnect_delay)
                await self._connect()
                await self.send_frame(frame, delay)
            else:
                raise

