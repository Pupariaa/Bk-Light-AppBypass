from __future__ import annotations
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _merge_dict(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class ClockPreset:
    format: str = "24h"
    theme: str = "dark"
    color: str = "#E2E8FF"
    accent: str = "#6E7DFF"
    background: str = "#000000"
    font: Optional[str] = None
    size: int = 20
    interval: float = 0.5
    dot_flashing: bool = True
    dot_flash_period: float = 1.0


@dataclass
class TextPreset:
    color: str = "#FF0000"
    background: str = "#000000"
    font: Optional[str] = None
    size: int = 16
    spacing: int = 1


@dataclass
class ImagePreset:
    mode: str = "fit"
    rotate: int = 0
    mirror: bool = False
    invert: bool = False


@dataclass
class CounterPreset:
    start: int = 0
    count: int = 10
    delay: float = 1.0


@dataclass
class DeviceConfig:
    address: Optional[str] = None
    auto_reconnect: bool = True
    reconnect_delay: float = 2.0
    mtu: int = 512
    rotate: int = 0
    brightness: float = 0.85
    timezone: str = "auto"


@dataclass
class DisplayConfig:
    frame_interval: float = 5.0
    max_retries: int = 3
    log_notifications: bool = False


@dataclass
class PanelDescriptor:
    name: str
    address: str
    grid_x: int = 0
    grid_y: int = 0
    rotation: Optional[int] = None
    brightness: Optional[float] = None


@dataclass
class PanelsConfig:
    tile_width: int = 32
    tile_height: int = 32
    columns: int = 1
    rows: int = 1
    items: list[PanelDescriptor] = field(default_factory=list)


@dataclass
class PresetLibrary:
    clock: Dict[str, ClockPreset] = field(default_factory=dict)
    text: Dict[str, TextPreset] = field(default_factory=dict)
    image: Dict[str, ImagePreset] = field(default_factory=dict)
    counter: Dict[str, CounterPreset] = field(default_factory=dict)


@dataclass
class RuntimeConfig:
    mode: str = "clock"
    preset: str = "default"
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    device: DeviceConfig = DeviceConfig()
    display: DisplayConfig = DisplayConfig()
    panels: PanelsConfig = PanelsConfig()
    presets: PresetLibrary = PresetLibrary()
    runtime: RuntimeConfig = RuntimeConfig()


DEFAULTS: Dict[str, Any] = {
    "device": {
        "address": None,
        "auto_reconnect": True,
        "reconnect_delay": 2.0,
        "mtu": 512,
        "rotate": 0,
        "brightness": 0.85,
        "timezone": "auto",
    },
    "panels": {
        "tile_width": 32,
        "tile_height": 32,
        "layout": {"columns": 1, "rows": 1},
        "list": [],
    },
    "display": {
        "frame_interval": 5.0,
        "max_retries": 3,
        "log_notifications": False,
    },
    "presets": {
        "clock": {
            "default": {
                "format": "24h",
                "theme": "dark",
                "color": "#E2E8FF",
                "accent": "#6E7DFF",
                "background": "#000000",
                "font": None,
                "size": 20,
                "interval": 0.5,
                "dot_flashing": True,
                "dot_flash_period": 1.0,
            }
        },
        "text": {
            "default": {
                "color": "#FF0000",
                "background": "#000000",
                "font": None,
                "size": 16,
                "spacing": 1,
            }
        },
        "image": {
            "default": {
                "mode": "fit",
                "rotate": 0,
                "mirror": False,
                "invert": False,
            }
        },
        "counter": {
            "default": {
                "start": 0,
                "count": 10,
                "delay": 1.0,
            }
        },
    },
    "runtime": {
        "mode": "clock",
        "preset": "default",
        "options": {},
    },
}


def _build_clock_presets(data: Dict[str, Dict[str, Any]]) -> Dict[str, ClockPreset]:
    presets: Dict[str, ClockPreset] = {}
    for name, values in data.items():
        preset = ClockPreset(**values)
        if preset.dot_flashing and preset.interval > 0.5:
            preset.interval = 0.5
        preset.interval = max(preset.interval, 0.1)
        if preset.format not in {"12h", "24h"}:
            preset.format = "24h"
        preset.dot_flash_period = max(preset.dot_flash_period, 0.2)
        presets[name] = preset
    if "default" not in presets:
        presets["default"] = ClockPreset()
    return presets


def _build_text_presets(data: Dict[str, Dict[str, Any]]) -> Dict[str, TextPreset]:
    presets: Dict[str, TextPreset] = {}
    for name, values in data.items():
        presets[name] = TextPreset(**values)
    if "default" not in presets:
        presets["default"] = TextPreset()
    return presets


def _build_image_presets(data: Dict[str, Dict[str, Any]]) -> Dict[str, ImagePreset]:
    presets: Dict[str, ImagePreset] = {}
    for name, values in data.items():
        preset = ImagePreset(**values)
        if preset.mode not in {"fit", "cover", "scale"}:
            preset.mode = "fit"
        if preset.rotate not in {0, 90, 180, 270}:
            preset.rotate = 0
        presets[name] = preset
    if "default" not in presets:
        presets["default"] = ImagePreset()
    return presets


def _build_counter_presets(data: Dict[str, Dict[str, Any]]) -> Dict[str, CounterPreset]:
    presets: Dict[str, CounterPreset] = {}
    for name, values in data.items():
        presets[name] = CounterPreset(**values)
    if "default" not in presets:
        presets["default"] = CounterPreset()
    return presets


def _build_panels(data: Dict[str, Any]) -> PanelsConfig:
    tile_width = data.get("tile_width", 32)
    tile_height = data.get("tile_height", 32)
    layout = data.get("layout", {})
    columns = layout.get("columns")
    rows = layout.get("rows")
    items_data = data.get("list", []) or []
    items: list[PanelDescriptor] = []
    max_x = 0
    max_y = 0
    for entry in items_data:
        if isinstance(entry, str):
            address = entry
            name = f"panel_{len(items) + 1}"
            grid_x = 0
            grid_y = 0
            rotation = None
            brightness = None
        elif isinstance(entry, dict):
            name = entry.get("name") or f"panel_{len(items) + 1}"
            address = entry.get("address")
            if not address:
                continue
            grid_x = int(entry.get("grid_x", 0))
            grid_y = int(entry.get("grid_y", 0))
            rotation = entry.get("rotation")
            if rotation not in {None, 0, 90, 180, 270}:
                rotation = None
            brightness = entry.get("brightness")
            if brightness is not None:
                brightness = _clamp(float(brightness), 0.1, 1.0)
        else:
            continue
        items.append(
            PanelDescriptor(
                name=name,
                address=address,
                grid_x=grid_x,
                grid_y=grid_y,
                rotation=rotation,
                brightness=brightness,
            )
        )
        max_x = max(max_x, grid_x)
        max_y = max(max_y, grid_y)
    if columns is None:
        columns = max_x + 1 if items else 1
    if rows is None:
        rows = max_y + 1 if items else 1
    return PanelsConfig(
        tile_width=tile_width,
        tile_height=tile_height,
        columns=columns,
        rows=rows,
        items=items,
    )


def load_config(path: Optional[Path] = None) -> AppConfig:
    path = path or Path("config.yaml")
    overrides = _load_yaml(path)
    merged = _merge_dict(DEFAULTS, overrides)
    device_data = merged.get("device", {})
    device = DeviceConfig(**device_data)
    brightness = _clamp(device.brightness, 0.1, 1.0)
    if device.rotate not in {0, 90, 180, 270}:
        device = replace(device, rotate=0)
    device = replace(device, brightness=brightness)
    env_address = os.getenv("BK_LIGHT_ADDRESS")
    if env_address:
        device = replace(device, address=env_address)
    display = DisplayConfig(**merged.get("display", {}))
    panels = _build_panels(merged.get("panels", {}))
    presets_data = merged.get("presets", {})
    preset_library = PresetLibrary(
        clock=_build_clock_presets(presets_data.get("clock", {})),
        text=_build_text_presets(presets_data.get("text", {})),
        image=_build_image_presets(presets_data.get("image", {})),
        counter=_build_counter_presets(presets_data.get("counter", {})),
    )
    runtime_data = merged.get("runtime", {})
    runtime = RuntimeConfig(
        mode=runtime_data.get("mode", "clock"),
        preset=runtime_data.get("preset", "default"),
        options=runtime_data.get("options", {}) or {},
    )
    return AppConfig(
        device=device,
        display=display,
        panels=panels,
        presets=preset_library,
        runtime=runtime,
    )


def clock_options(config: AppConfig, preset_name: str, overrides: Dict[str, Any]) -> ClockPreset:
    library = config.presets.clock
    base = library.get(preset_name) or library.get(config.runtime.preset) or library.get("default") or ClockPreset()
    data = dict(base.__dict__)
    for key, value in overrides.items():
        if value is not None and key in data:
            data[key] = value
    preset = ClockPreset(**data)
    if preset.dot_flashing and preset.interval > 0.5:
        preset.interval = 0.5
    preset.interval = max(preset.interval, 0.1)
    return preset


def text_options(config: AppConfig, preset_name: str, overrides: Dict[str, Any]) -> TextPreset:
    library = config.presets.text
    base = library.get(preset_name) or library.get(config.runtime.preset) or library.get("default") or TextPreset()
    data = dict(base.__dict__)
    for key, value in overrides.items():
        if value is not None and key in data:
            data[key] = value
    return TextPreset(**data)


def image_options(config: AppConfig, preset_name: str, overrides: Dict[str, Any]) -> ImagePreset:
    library = config.presets.image
    base = library.get(preset_name) or library.get(config.runtime.preset) or library.get("default") or ImagePreset()
    data = dict(base.__dict__)
    for key, value in overrides.items():
        if value is not None and key in data:
            data[key] = value
    preset = ImagePreset(**data)
    if preset.mode not in {"fit", "cover", "scale"}:
        preset.mode = "fit"
    if preset.rotate not in {0, 90, 180, 270}:
        preset.rotate = 0
    return preset


def counter_options(config: AppConfig, preset_name: str, overrides: Dict[str, Any]) -> CounterPreset:
    library = config.presets.counter
    base = library.get(preset_name) or library.get(config.runtime.preset) or library.get("default") or CounterPreset()
    data = dict(base.__dict__)
    for key, value in overrides.items():
        if value is not None and key in data:
            data[key] = value
    return CounterPreset(**data)

