# BLE LED Display Toolkit

Utilities for driving the BK-Light ACT1026 32×32 RGB LED matrix over Bluetooth Low Energy using the command sequence extracted from the provided logs. Other panels are not supported.

These scripts form a functional test toolkit and reference implementation; an official API/library layer will follow.

## Requirements
- Python 3.10+
- `pip install bleak Pillow`
- Bluetooth adapter with BLE support enabled
- Hardware capabilities:
  - BLE 4.0 or newer with GATT/ATT support
  - Central role / GATT client mode
  - LE 1M PHY
  - Long ATT write support (Prepare/Execute or Write-with-response handling for fragmented payloads)
  - MTU negotiation and L2CAP fragmentation

The tools assume the screen advertises as `LED_BLE_*` (BK-Light firmware) and is available at `F0:27:3C:1A:8B:C3`. Update the address in `display_session.py` if your unit differs.

## Project Structure
- `bootstrap_demo.py` – scans for ACT1026 panels, connects to the first one, and shows the GitHub splash from `assets/bklight-boot.png`.
- `assets/bklight-boot.png` – source artwork for the bootstrap splash screen.
- `display_session.py` – shared session and frame builder used by every tool.
- `red_corners.py` – sends a 32×32 frame with red pixels in each corner.
- `increment_counter.py` – renders an incrementing number and streams it to the screen.
- `send_image.py` – pushes any image file with optional fit/transform options.
- `display_text.py` – renders custom text with configurable colors and font.
- `clock_display.py` – pushes a stylised HH:MM clock that follows the host timezone.

## Quick Start
Set the panel MAC address once (PowerShell example):
```powershell
$env:BK_LIGHT_ADDRESS="F0:27:3C:1A:8B:C3"
```
or export it in your shell profile. Each command accepts an explicit address if you prefer to pass it manually.

```bash
python red_corners.py
```

If the connection works you should see notifications for each ACK and a final `DONE`. Add `--address XX:XX:XX:XX:XX:XX` to override the environment variable for one-off runs.

To automatically locate a panel and push the GitHub splash screen:
```bash
python bootstrap_demo.py
```

All utilities default to the `BK_LIGHT_ADDRESS` environment variable. If it is missing you will be prompted to provide the address explicitly via script parameters (see the `BleDisplaySession` constructor).

## Tools
### Incrementing counter
```bash
python increment_counter.py --start 0 --count 20 --delay 1.0
```
- `--start` initial value.
- `--count` number of frames to send.
- `--delay` pause (seconds) between frames.
- `--address` optional MAC override.

### Push an image
```bash
python send_image.py assets/example.png --mode fit --rotate 90 --mirror
```
- `--mode` `scale` (default), `fit`, or `cover`.
- `--rotate` rotation in degrees.
- `--mirror` horizontal mirror.
- `--invert` color inversion before upload.
- `--address` optional MAC override.

### Display custom text
```bash
python display_text.py "HELLO\\nWORLD" --color "#FF0066" --background "#000000" --size 18
```
- `--color` and `--background` accept `#RRGGBB` or `r,g,b`.
- `--font` path to a TrueType font file.
- `--size` font size when using a TrueType font.
- `--spacing` line spacing for multiline text.
- `--address` optional MAC override.

### Stylised clock
```bash
python clock_display.py --theme dark --interval 5.0
```
- `--theme` palette preset (`dark` default, `neon`, `warm`).
- `--color` primary time color override.
- `--accent` highlight color override for the colon and gradient.
- `--background` base gradient override.
- `--font` optional TrueType font path.
- `--size` font size when using a TrueType font.
- `--interval` refresh cadence in seconds.
- `--timezone` optional IANA timezone name override.
- `--address` optional MAC override.

## Building New Effects
`BleDisplaySession` exposes a simple `send_png` helper. Generate a 32×32 PNG in memory (any drawing logic with Pillow) and call:
```python
async with BleDisplaySession() as session:
    await session.send_png(png_bytes)
```
The class performs the handshake (`fa02` characteristic) and validates the acknowledgements streamed through `fa03` automatically.

## Attribution & License
- Created by Puparia — GitHub: [Pupariaa](https://github.com/Pupariaa).
- Code is open-source and contributions are welcome; open a pull request with improvements or new effects.
- If you reuse this toolkit (or derivatives) in your own projects, credit “Puparia / https://github.com/Pupariaa” and link back to the original repository.
- Licensed under the [MIT License](./LICENSE).
