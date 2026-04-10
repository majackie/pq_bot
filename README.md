# pq_bot

Automatically clicks the Accept and Auto Match buttons in Maplestory Idle RPG on Waydroid.

## Description

Watches the Waydroid screen via ADB and taps the following buttons whenever they appear:

- **Auto Match** — queues for a party quest match
- **Accept** — accepts an incoming party quest match
- **OK** — dismisses the "Lost connection to the party" prompt
- **Leave** — dismisses the clear screen after a match ends

Does not move the mouse cursor and works with Waydroid running in the background.

## Installation

### Dependencies

- Python 3.10+
- OpenCV (`opencv-python`)
- ADB (`android-tools`)

### Install Python dependencies
```
pip install -r requirements.txt
```

### Install ADB
```
sudo dnf install android-tools
```

## Setup

### 1. Enable Developer Mode and USB Debugging in Waydroid

Launch Waydroid and open the Android **Settings** app.

Enable Developer Mode:
1. Go to **About phone**
2. Tap **Build number** seven times until you see "You are now a developer"

Enable USB Debugging:
1. Go back to **Settings** → **System** → **Developer options**
2. Toggle on **USB debugging**

Allow the connection from your computer:
1. Connect ADB (see step 2 below)
2. A prompt will appear in Waydroid asking "Allow USB debugging from this computer?"
3. Tap **Allow** (check "Always allow from this computer" to avoid this prompt in the future)

### 2. Connect ADB to Waydroid

First, check if Waydroid is already connected:
```
adb devices
```

If you see an entry like `192.168.240.112:5555    device`, skip to step 3.

If nothing is listed, find your Waydroid IP with:
```
waydroid status
```

Look for the `IP` field, then connect manually:
```
adb connect <ip>:5555
```

Run `adb devices` again to confirm the connection.

### 3. Update the IP address in bot.py

Open `bot.py` and update `ADB_HOST` at the top of the file to match your Waydroid IP:

```python
ADB_HOST = "192.168.240.112:5555"
```

### 4. Open Maplestory Idle RPG

Open Maplestory Idle RPG and navigate to the Party Quest page with the Auto Match button visible.

### 5. Run the bot

```
python3 bot.py
```

Press **Ctrl+C** to stop.

## Configuration

Edit the constants at the top of `bot.py`:

- **`ADB_HOST`** — Waydroid ADB address
- **`THRESHOLD`** — Match confidence from 0 to 1. Lower if buttons aren't being detected. Raise if it's clicking the wrong spot
- **`CLICK_COOLDOWN`** — Seconds to wait after a tap before checking again (default: 2)

> **Note:** The bot checks the screen as fast as possible. Detection latency is ~1.4s due to the time Android takes to capture a screenshot via ADB.

## Troubleshooting

If the bot is not detecting buttons:
1. **Lower the threshold** — Set `THRESHOLD` to `0.80` or lower in `bot.py`
2. **Check ADB connection** — Run `adb devices` and confirm Waydroid is listed
3. **Keep Waydroid visible** — Waydroid may suspend the game when minimized, preventing buttons from appearing

## Contributors

Jackie Ma
