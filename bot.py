import subprocess
import sys
import time
import cv2
import numpy as np

ADB_HOST = "192.168.240.112:5555"  # waydroid adb address
TEMPLATES = {
    "okay": "./images/okay_button.png",  # dismisses "Lost connection to the party" prompt
    "accept": "./images/accept_button.png",  # accept match found prompt (after matchmaking)
    "auto_match": "./images/auto_match_button.png",  # start matchmaking from the main menu
    "leave": "./images/leave_button.png",  # dismisses "Leave the party?" prompt after a match
}
THRESHOLD = 0.85  # match confidence (0–1); lower = more lenient
CLICK_COOLDOWN = 2.0  # seconds to wait after a tap before checking again


def adb(*args) -> bytes:
    result = subprocess.run(
        ["adb", "-s", ADB_HOST, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # suppress harmless amdgpu warning
    )
    if result.returncode != 0:
        sys.exit(f"ADB error (exit {result.returncode}): {' '.join(args)}")
    return result.stdout


def screencap() -> np.ndarray:
    adb("shell", "screencap", "-p", "/sdcard/screen.png")
    adb("pull", "/sdcard/screen.png", "/tmp/pq_bot_screen.png")
    img = cv2.imread("/tmp/pq_bot_screen.png")
    if img is None:
        sys.exit("ERROR: screencap returned invalid image data.")
    return img


def load_templates(paths: dict) -> dict:
    templates = {}
    for name, path in paths.items():
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            sys.exit(f"ERROR: could not load template '{path}'")
        templates[name] = img
        print(f"  loaded '{name}': {img.shape[1]}x{img.shape[0]}px")
    return templates


def find_button(screen: np.ndarray, template: np.ndarray) -> tuple[float, tuple]:
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_val, max_loc


def tap(x: int, y: int, duration_ms: int = 100):
    adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms))


def main():
    print(f"Connecting to {ADB_HOST}...")
    adb("shell", "echo", "ok")  # verify connection
    print("Connected.\n")

    print("Loading templates...")
    templates = load_templates(TEMPLATES)
    print(f"\nPress Ctrl+C to stop.\n")

    while True:
        screen = screencap()

        clicked = False
        for name, template in templates.items():
            confidence, loc = find_button(screen, template)

            if confidence >= THRESHOLD:
                th, tw = template.shape[:2]
                cx = loc[0] + tw // 2
                cy = loc[1] + th // 2
                tap(cx, cy)
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] '{name}' matched (conf={confidence:.2f}) → tapped ({cx}, {cy})")
                clicked = True
                break

        if clicked:
            time.sleep(CLICK_COOLDOWN)


if __name__ == "__main__":
    main()
