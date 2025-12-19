import asyncio
import binascii
import os
from io import BytesIO
from typing import Optional
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from PIL import Image, ImageEnhance

DEFAULT_ADDRESS = os.getenv("BK_LIGHT_ADDRESS")
UUID_WRITE = "0000fa02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "0000fa03-0000-1000-8000-00805f9b34fb"
HANDSHAKE_FIRST = bytes.fromhex("08 00 01 80 0E 06 32 00")
HANDSHAKE_SECOND = bytes.fromhex("04 00 05 80")
ACK_STAGE_ONE = bytes.fromhex("0C 00 01 80 81 06 32 00 00 01 00 01")
ACK_STAGE_ONE_ALT = bytes.fromhex("0B 00 01 80 83 06 32 00 00 01 00")  # ACT1025 64x16 variant
ACK_STAGE_TWO = bytes.fromhex("08 00 05 80 0B 03 07 02")
ACK_STAGE_TWO_ALT = bytes.fromhex("08 00 05 80 0E 03 07 01")  # ACT1025 64x16 variant
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
        image = image.rotate(rotation % 360, expand=False)
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
        if payload == ACK_STAGE_ONE or payload == ACK_STAGE_ONE_ALT:
            self.stage_one.set()
        elif payload == ACK_STAGE_TWO or payload == ACK_STAGE_TWO_ALT:
            self.stage_two.set()
        elif payload == ACK_STAGE_THREE:
            self.stage_three.set()


async def wait_for_ack(event: asyncio.Event, label: str, verbose: bool) -> None:
    try:
        await asyncio.wait_for(event.wait(), timeout=5.0)
        if verbose:
            print(label + "_OK")
    except asyncio.TimeoutError as timeout_error:
        if verbose:
            print(label + "_TIMEOUT")
        raise timeout_error


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
        max_retries: int = 3,
        scan_timeout: float = 6.0,
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
        self.max_retries = max_retries
        self.scan_timeout = scan_timeout
        self.client: Optional[BleakClient] = None
        self.watcher = AckWatcher(log_notifications)

    async def _safe_disconnect(self) -> None:
        if self.client is None:
            return
        try:
            if self.client.is_connected:
                try:
                    await self.client.stop_notify(UUID_NOTIFY)
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            await self.client.disconnect()
        except Exception:
            pass
        finally:
            self.client = None

    async def _connect(self) -> None:
        attempt = 0
        while True:
            attempt += 1
            try:
                if self.client and self.client.is_connected:
                    return
                if self.client:
                    await self._safe_disconnect()
                try:
                    device = await BleakScanner.find_device_by_address(
                        self.address, timeout=self.scan_timeout, cached=False
                    )
                except TypeError:
                    device = await BleakScanner.find_device_by_address(
                        self.address, timeout=self.scan_timeout
                    )
                if device is None:
                    try:
                        device = await BleakScanner.find_device_by_address(
                            self.address, timeout=self.scan_timeout, cached=True
                        )
                    except TypeError:
                        device = await BleakScanner.find_device_by_address(
                            self.address, timeout=self.scan_timeout
                        )
                if device is None:
                    raise BleakError(f"Device with address {self.address} was not found")
                self.client = BleakClient(device)
                self.watcher = AckWatcher(self.log_notifications)
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
                if not self.auto_reconnect or attempt > self.max_retries:
                    await self._safe_disconnect()
                    raise error
                await asyncio.sleep(self.reconnect_delay)

    async def _ensure_connected(self) -> None:
        if not self.client or not self.client.is_connected:
            await self._connect()

    async def __aenter__(self) -> "BleDisplaySession":
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._safe_disconnect()

    async def send_png(self, png_bytes: bytes, delay: float = 0.2) -> None:
        processed = adjust_image(png_bytes, self.rotation, self.brightness)
        frame = build_frame(processed)
        await self.send_frame(frame, delay)

    async def send_frame(self, frame: bytes, delay: float = 0.2) -> None:
        attempt = 0
        while True:
            attempt += 1
            try:
                await self._ensure_connected()
                self.watcher.reset()
                await self.client.write_gatt_char(UUID_WRITE, HANDSHAKE_FIRST, response=False)
                await wait_for_ack(self.watcher.stage_one, "HANDSHAKE_STAGE_ONE", self.log_notifications)
                await asyncio.sleep(delay)
                self.watcher.stage_two.clear()
                skip_stage_two = False
                try:
                    await self.client.write_gatt_char(UUID_WRITE, HANDSHAKE_SECOND, response=False)
                    await wait_for_ack(self.watcher.stage_two, "HANDSHAKE_STAGE_TWO", self.log_notifications)
                except asyncio.TimeoutError:
                    skip_stage_two = True
                    if self.log_notifications:
                        print("HANDSHAKE_STAGE_TWO_SKIPPED")
                else:
                    await asyncio.sleep(delay)
                if skip_stage_two:
                    await asyncio.sleep(delay)
                await self.client.write_gatt_char(UUID_WRITE, frame, response=True)
                await wait_for_ack(self.watcher.stage_three, "FRAME_ACK", self.log_notifications)
                await asyncio.sleep(delay)
                # await self.client.write_gatt_char(UUID_WRITE, FRAME_VALIDATION, response=False)
                return
            except (asyncio.TimeoutError, BleakError, ConnectionError) as error:
                if not self.auto_reconnect or attempt > self.max_retries:
                    await self._safe_disconnect()
                    raise error
                await self._safe_disconnect()
                await asyncio.sleep(self.reconnect_delay)
            except Exception as error:
                if not self.auto_reconnect or attempt > self.max_retries:
                    await self._safe_disconnect()
                    raise error
                await self._safe_disconnect()
                await asyncio.sleep(self.reconnect_delay)

