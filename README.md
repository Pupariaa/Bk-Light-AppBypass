# BLE LED Display Toolkit

Utilities for driving the BK-Light ACT1026 32×32 RGB LED matrix over Bluetooth Low Energy using the command sequence extracted from the provided logs. Other panels are not supported.

Everything is now configurable through `config.yaml`, so you can define presets, multi-panel layouts, and runtime modes without touching code.

## Requirements
- Python 3.10+
- `pip install bleak Pillow PyYAML`
- Bluetooth adapter with BLE support enabled
- Hardware capabilities:
  - BLE 4.0 or newer with GATT/ATT support
  - Central role / GATT client mode
  - LE 1M PHY
  - Long ATT write support (Prepare/Execute or Write-with-response handling for fragmented payloads)
  - MTU negotiation and L2CAP fragmentation

The tools assume the screen advertises as `LED_BLE_*` (BK-Light firmware). Update the MAC address in `config.yaml` (or via `BK_LIGHT_ADDRESS`) if your unit differs.

## Project Structure
- `config.yaml` – device defaults, multi-panel layout, presets, runtime mode.
- `config.py` – loader/validators for the configuration tree.
- `panel_manager.py` – orchestrates single/multi-panel sessions and image slicing.
- `display_session.py` – BLE transport: handshake, ACK tracking, brightness/rotation, auto-reconnect.
- `production.py` – production entrypoint that reads `config.yaml` and runs the selected mode/preset.
- Toolkit scripts (still usable standalone):
  - `clock_display.py`
  - `display_text.py`
  - `send_image.py`
  - `increment_counter.py`
  - `identify_panels.py`
- Legacy smoke tests: `bootstrap_demo.py`, `red_corners.py`.

## Quick Start
1. Install dependencies:
   ```bash
   pip install bleak Pillow PyYAML
   ```
2. Edit `config.yaml`.
   - Single panel:
     ```yaml
     device:
       address: "F0:27:3C:1A:8B:C3"
     panels:
       list: ["F0:27:3C:1A:8B:C3"]
     ```
   - Multi-panel:
     ```yaml
     panels:
       tile_width: 32
       tile_height: 32
       layout:
         columns: 2
         rows: 1
       list:
         - name: left
           address: "F0:27:3C:1A:8B:C3"
           grid_x: 0
           grid_y: 0
         - name: right
           address: "F0:27:3C:1A:8B:C4"
           grid_x: 1
           grid_y: 0
     ```
     (A bare MAC string is accepted; defaults are inferred.)
3. Pick the runtime mode and preset:
   ```yaml
   runtime:
     mode: clock
     preset: default
     options:
       timezone: "Europe/Paris"
   ```
4. Launch the production entrypoint:
   ```bash
   python scripts/production.py
   ```
   Override anything ad hoc:
   ```bash
   python scripts/production.py --mode text --text "HELLO" --option color=#00FFAA
   ```
5. Need to identify MAC ↔ panel placement or force a clean BLE reset? Run:
   ```bash
   python scripts/identify_panels.py
   ```
   (Chaque panneau affiche un numéro puis se déconnecte proprement.)

## Toolkit Scripts
- `scripts/clock_display.py` – async HH:MM clock (supports 12/24h, dot flashing, themes). Quittez avec `Ctrl+C` : la session BLE est fermée proprement, vous pouvez relancer immédiatement.
- `scripts/display_text.py` – renders text using presets (colour/background/font/spacing) or marquee scrolls.
  - Example scrolling preset in `config.yaml`:
    ```yaml
    text:
      marquee_left:
        mode: scroll
        direction: left
        speed: 30.0      # pixels per second
        gap: 32          # space between repetitions
        offset_y: 0      # vertical tweak in pixels
        interval: 0.04   # frame interval (seconds)
    ```
  - Launch: `python scripts/display_text.py "HELLO" --preset marquee_left`
- `scripts/send_image.py` – uploads any image with fit/cover/scale + rotate/mirror/invert.
- `scripts/increment_counter.py` – numeric animation for diagnostics.
- `scripts/identify_panels.py` – flashes digits on each configured panel.

Each script honours `--config`, `--address`, and preset overrides so you can reuse the same YAML in development or production.

## Building New Effects
Use Pillow to draw onto a canvas sized to `columns × rows` tiles, then:
```python
async with PanelManager(load_config()) as manager:
    await manager.send_image(image)
```
`PanelManager` slices the image per tile and `BleDisplaySession` handles BLE writes/ACKs for each panel automatically. Sessions se reconnectent automatiquement en cas de redémarrage du panneau (retries via `reconnect_delay` / `max_retries` / `scan_timeout`).

## Attribution & License
- Created by Puparia — GitHub: [Pupariaa](https://github.com/Pupariaa).
- Code is open-source and contributions are welcome; open a pull request with improvements or new effects.
- If you reuse this toolkit (or derivatives) in your own projects, credit “Puparia / https://github.com/Pupariaa” and link back to the original repository.
- Licensed under the [MIT License](./LICENSE).
