from __future__ import annotations
import asyncio
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional
from PIL import Image
from .config import AppConfig, PanelDescriptor
from .display_session import BleDisplaySession


@dataclass
class PanelSession:
    descriptor: Optional[PanelDescriptor]
    session: BleDisplaySession


class PanelManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.sessions: List[PanelSession] = []
        self.multi_panel = bool(config.panels.items)
        self.tile_width = config.panels.tile_width
        self.tile_height = config.panels.tile_height
        self.columns = config.panels.columns if self.multi_panel else 1
        self.rows = config.panels.rows if self.multi_panel else 1

    @property
    def canvas_size(self) -> tuple[int, int]:
        return (self.columns * self.tile_width, self.rows * self.tile_height)

    async def __aenter__(self) -> "PanelManager":
        if self.multi_panel:
            await self._connect_panels()
        else:
            await self._connect_single()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        while self.sessions:
            descriptor_session = self.sessions.pop()
            try:
                await descriptor_session.session.__aexit__(exc_type, exc, tb)
            except Exception:
                pass

    async def _connect_single(self) -> None:
        address = self.config.device.address
        if not address:
            raise ValueError("No panel configured. Set device.address or define panels list in config.yaml.")
        session = BleDisplaySession(
            address=address,
            auto_reconnect=self.config.device.auto_reconnect,
            reconnect_delay=self.config.device.reconnect_delay,
            rotation=self.config.device.rotate,
            brightness=self.config.device.brightness,
            mtu=self.config.device.mtu,
            log_notifications=self.config.display.log_notifications,
        )
        await session.__aenter__()
        self.sessions.append(PanelSession(None, session))

    async def _connect_panels(self) -> None:
        tasks = []
        for descriptor in self.config.panels.items:
            rotation = descriptor.rotation if descriptor.rotation is not None else self.config.device.rotate
            brightness = descriptor.brightness if descriptor.brightness is not None else self.config.device.brightness
            session = BleDisplaySession(
                address=descriptor.address,
                auto_reconnect=self.config.device.auto_reconnect,
                reconnect_delay=self.config.device.reconnect_delay,
                rotation=rotation,
                brightness=brightness,
                mtu=self.config.device.mtu,
                log_notifications=self.config.display.log_notifications,
            )
            tasks.append(self._connect_panel(descriptor, session))
        await asyncio.gather(*tasks)

    async def _connect_panel(self, descriptor: PanelDescriptor, session: BleDisplaySession) -> None:
        await session.__aenter__()
        self.sessions.append(PanelSession(descriptor, session))

    async def send_image(self, image: Image.Image, delay: float = 0.2) -> None:
        if self.multi_panel:
            await self._send_multi(image, delay)
        else:
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=False)
            await self.sessions[0].session.send_png(buffer.getvalue(), delay)

    async def _send_multi(self, image: Image.Image, delay: float) -> None:
        expected_width, expected_height = self.canvas_size
        if image.size != (expected_width, expected_height):
            image = image.resize((expected_width, expected_height))
        tasks = []
        for panel_session in self.sessions:
            descriptor = panel_session.descriptor
            if descriptor is None:
                continue
            left = descriptor.grid_x * self.tile_width
            top = descriptor.grid_y * self.tile_height
            right = left + self.tile_width
            bottom = top + self.tile_height
            region = image.crop((left, top, right, bottom))
            buffer = BytesIO()
            region.save(buffer, format="PNG", optimize=False)
            tasks.append(panel_session.session.send_png(buffer.getvalue(), delay))
        await asyncio.gather(*tasks)

