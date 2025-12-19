#!/usr/bin/env python3
"""
BLE Panel Server - Serves static HTML and handles BLE transmission
Usage: python3 server.py <device-address> [--port 8080]

Example:
  macOS:  python3 server.py 8A9CA9B7-26BA-4640-B28B-F43035A25538
  Linux:  python3 server.py AA:BB:CC:DD:EE:FF
"""

import argparse
import asyncio
import binascii
import sys
from pathlib import Path

try:
    import websockets
    from websockets.server import serve as ws_serve
except ImportError:
    print("Error: websockets library required")
    print("Install with: pip install websockets")
    sys.exit(1)

try:
    from bleak import BleakClient, BleakScanner
    from bleak.exc import BleakError
except ImportError:
    print("Error: bleak library required")
    print("Install with: pip install bleak")
    sys.exit(1)

# Configuration
HTML_FILE = Path(__file__).parent / "snake.html"

# BLE UUIDs (from working display_session.py)
UUID_WRITE = "0000fa02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "0000fa03-0000-1000-8000-00805f9b34fb"

# Handshake bytes (from working display_session.py)
HANDSHAKE_FIRST = bytes.fromhex("08 00 01 80 0E 06 32 00")
HANDSHAKE_SECOND = bytes.fromhex("04 00 05 80")

# ACK patterns (from working display_session.py)
ACK_STAGE_ONE = bytes.fromhex("0C 00 01 80 81")  # First 5 bytes
ACK_STAGE_ONE_ALT = bytes.fromhex("0B 00 01 80 83")  # ACT1025 variant
ACK_STAGE_TWO = bytes.fromhex("08 00 05 80 0B")  # First 5 bytes
ACK_STAGE_TWO_ALT = bytes.fromhex("08 00 05 80 0E")  # ACT1025 variant
ACK_STAGE_THREE = bytes.fromhex("05 00 02 00 03")  # First 5 bytes


def build_frame(png_bytes: bytes) -> bytes:
    """Build BLE frame from PNG data."""
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


class BLEPanel:
    """BLE Panel connection manager."""

    def __init__(self, address: str, verbose: bool = False):
        self.address = address
        self.verbose = verbose
        self.client: BleakClient | None = None
        self.ack_stage = 0
        self.ack_event = asyncio.Event()
        self._send_lock = asyncio.Lock()

    def _notification_handler(self, _sender: int, data: bytearray) -> None:
        """Handle BLE notifications."""
        payload = bytes(data)
        if self.verbose:
            hex_str = " ".join(f"{b:02X}" for b in payload[:16])
            print(f"RX [{len(payload)}]: {hex_str}")

        # Check ACK patterns (match first 5 bytes)
        if len(payload) >= 5:
            prefix = payload[:5]
            if prefix == ACK_STAGE_ONE or prefix == ACK_STAGE_ONE_ALT:
                self.ack_stage = 1
                if self.verbose:
                    print("-> ACK Stage 1")
            elif prefix == ACK_STAGE_TWO or prefix == ACK_STAGE_TWO_ALT:
                self.ack_stage = 2
                if self.verbose:
                    print("-> ACK Stage 2")
            elif prefix == ACK_STAGE_THREE:
                self.ack_stage = 3
                if self.verbose:
                    print("-> ACK Stage 3 (Frame OK)")
            self.ack_event.set()

    async def connect(self) -> bool:
        """Connect to BLE device."""
        try:
            print(f"Scanning for {self.address}...")
            device = await BleakScanner.find_device_by_address(
                self.address, timeout=10.0
            )
            if device is None:
                print(f"Device {self.address} not found")
                return False

            print(f"Connecting to {device.name or self.address}...")
            self.client = BleakClient(device)
            await self.client.connect()

            if not self.client.is_connected:
                print("Connection failed")
                return False

            # Enable notifications
            await self.client.start_notify(UUID_NOTIFY, self._notification_handler)
            print("Connected and notifications enabled")
            return True

        except Exception as e:
            print(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from BLE device."""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(UUID_NOTIFY)
            except Exception:
                pass
            await self.client.disconnect()
        self.client = None

    async def _wait_for_ack(self, expected_stage: int, timeout: float = 2.0) -> bool:
        """Wait for ACK stage."""
        self.ack_event.clear()
        deadline = asyncio.get_event_loop().time() + timeout
        while self.ack_stage < expected_stage:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(self.ack_event.wait(), timeout=remaining)
                self.ack_event.clear()
            except asyncio.TimeoutError:
                return False
        return True

    async def send_png(self, png_data: bytes) -> bool:
        """Send PNG frame to panel."""
        if not self.client or not self.client.is_connected:
            return False

        async with self._send_lock:
            try:
                self.ack_stage = 0

                # Stage 1: First handshake
                await self.client.write_gatt_char(
                    UUID_WRITE, HANDSHAKE_FIRST, response=False
                )
                if not await self._wait_for_ack(1, 5.0):
                    if self.verbose:
                        print("Stage 1 timeout")
                    return False

                await asyncio.sleep(0.1)  # Small delay between stages

                # Stage 2: Second handshake (optional)
                await self.client.write_gatt_char(
                    UUID_WRITE, HANDSHAKE_SECOND, response=False
                )
                await self._wait_for_ack(2, 0.5)  # Don't fail on timeout

                await asyncio.sleep(0.1)  # Small delay before frame

                # Stage 3: Send frame
                frame = build_frame(png_data)
                await self.client.write_gatt_char(UUID_WRITE, frame, response=True)
                if not await self._wait_for_ack(3, 5.0):
                    if self.verbose:
                        print("Frame ACK timeout")
                    return False

                return True

            except Exception as e:
                if self.verbose:
                    print(f"Send error: {e}")
                return False


# Global panel instance
panel: BLEPanel | None = None
last_frame_time: float = 0
MIN_FRAME_INTERVAL = 0.08  # ~12 fps max to avoid overwhelming the panel


async def handle_websocket(websocket):
    """Handle WebSocket connection from browser."""
    global last_frame_time
    print(f"Client connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            if isinstance(message, bytes) and panel:
                # Rate limit: skip frames if too fast
                now = asyncio.get_event_loop().time()
                if now - last_frame_time >= MIN_FRAME_INTERVAL:
                    last_frame_time = now
                    await panel.send_png(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    print(f"Client disconnected: {websocket.remote_address}")


async def handle_http(reader, writer):
    """Simple HTTP server for static files."""
    try:
        data = await reader.read(4096)
        request = data.decode("utf-8", errors="ignore")

        if "GET / " in request or "GET /snake.html" in request:
            if HTML_FILE.exists():
                content = HTML_FILE.read_bytes()
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/html; charset=utf-8\r\n"
                    b"Content-Length: " + str(len(content)).encode() + b"\r\n"
                    b"Connection: close\r\n\r\n" + content
                )
            else:
                response = b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\nsnake.html not found"
        else:
            response = b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\nNot found"

        writer.write(response)
        await writer.drain()
    except Exception as e:
        print(f"HTTP error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    global panel

    parser = argparse.ArgumentParser(description="BLE Panel Server")
    parser.add_argument("address", help="BLE device address (UUID on macOS, MAC on Linux)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket port (default: 8765)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose BLE output")
    args = parser.parse_args()

    # Connect to BLE panel
    panel = BLEPanel(args.address, verbose=args.verbose)
    if not await panel.connect():
        print("Failed to connect to BLE device")
        sys.exit(1)

    print("Ready!")

    # Start HTTP server
    http_server = await asyncio.start_server(handle_http, "0.0.0.0", args.port)
    print(f"HTTP server: http://localhost:{args.port}/")

    # Start WebSocket server
    ws_server = await ws_serve(handle_websocket, "0.0.0.0", args.ws_port)
    print(f"WebSocket server: ws://localhost:{args.ws_port}/")

    print(f"\nOpen http://localhost:{args.port} in your browser to play Snake!")

    try:
        await asyncio.gather(
            http_server.serve_forever(),
            ws_server.wait_closed(),
        )
    except asyncio.CancelledError:
        pass
    finally:
        await panel.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
