# GestureHUD

Real-time hand gesture control with a transparent HUD overlay for Windows. Uses a webcam to track hand landmarks via MediaPipe and translates gestures into mouse actions cursor movement, clicks, drag, and scroll while rendering a see-through heads-up display over your desktop.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Cursor control** — index fingertip drives the system cursor
- **Left click** — pinch index finger to thumb
- **Right click** — pinch middle finger to thumb
- **Drag** — close fist to hold left button
- **Scroll** — peace/V-sign gesture, move hand up/down
- **HUD overlay** — transparent, click-through fullscreen overlay with:
  - Hand skeleton wireframe
  - Animated cursor reticle
  - System telemetry (CPU, RAM, battery)
  - Gesture state indicators

## How it works

| Module | Role |
|--------|------|
| `tracker.py` | Runs MediaPipe Hands in a background thread. Detects pinch gestures using a hysteresis state machine with 1-Euro filtered distance measurements. |
| `filter.py` | Implements the [1-Euro filter](https://cristal.univ-lille.fr/~casiez/1euro/) for adaptive signal smoothing. |
| `controls.py` | Converts normalized hand coordinates to Win32 `SendInput` mouse events. |
| `overlay.py` | Pygame-based transparent overlay using Win32 layered window APIs. |
| `telemetry.py` | Polls CPU/RAM/battery via psutil. |
| `main.py` | Wires everything together in a 60 fps render loop. |

## Setup

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

Pass `--gpu` to request GPU acceleration for MediaPipe (requires compatible hardware):

```bash
python main.py --gpu
```

Press **ESC** to quit.

## Gesture Reference

| Gesture | Action | Description |
|---------|--------|-------------|
| Point | Move cursor | Index finger extended, cursor follows fingertip |
| Index pinch | Left click | Touch index fingertip to thumb tip |
| Middle pinch | Right click | Touch middle fingertip to thumb tip |
| Closed fist | Drag | All fingers curled, holds left mouse button |
| Peace sign | Scroll | Index + middle extended, vertical motion scrolls |
| Open palm | Release | All fingers open, releases drag and resets scroll |

## Requirements

- Windows 10/11
- Python 3.10+
- Webcam
- Dependencies listed in `requirements.txt`

## Architecture

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│  Webcam  │───▶│ Tracker  │───▶│  Main    │
│          │    │ (thread) │    │  Loop    │
└──────────┘    └──────────┘    └────┬─────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ Controls │    │ Overlay  │    │Telemetry │
              │(SendInput)│    │ (Pygame) │    │ (psutil) │
              └──────────┘    └──────────┘    └──────────┘
```

## License

MIT
