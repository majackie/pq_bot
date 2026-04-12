import curses
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
    "x1": "./images/x1_button.png",  # close ad
    "x2": "./images/x2_button.png",  # close ad
    "x3": "./images/x3_button.png",  # close ad
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
    return templates


def find_button(screen: np.ndarray, template: np.ndarray) -> tuple[float, tuple]:
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_val, max_loc


def tap(x: int, y: int, duration_ms: int = 100):
    adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms))


def connect():
    subprocess.run(
        ["adb", "connect", ADB_HOST],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def draw_header(win, matches: int, avg_duration: float):
    avg_str = f"{avg_duration / 60:.1f}min" if matches > 0 else "n/a"
    width = win.getmaxyx()[1]
    text = f" matches: {matches}  |  avg match duration: {avg_str} "
    text = text.ljust(width - 1)
    win.erase()
    win.addstr(0, 0, text, curses.A_REVERSE)
    win.refresh()


def log(win, msg: str):
    win.addstr(msg + "\n")
    win.refresh()


def run(stdscr):
    curses.curs_set(0)
    height, width = stdscr.getmaxyx()

    header_win = curses.newwin(1, width, 0, 0)
    log_win = curses.newwin(height - 1, width, 1, 0)
    log_win.scrollok(True)

    draw_header(header_win, 0, 0)

    connect()
    adb("shell", "echo", "ok")  # verify connection

    templates = load_templates(TEMPLATES)

    leave_count = 0
    last_tapped = None
    last_leave_time = None
    leave_intervals = []
    accept_time = None        # set when 'accept' is tapped; cleared if anything else interrupts
    clean_sequence = False    # True only if no other taps occurred between accept and leave
    match_durations = []

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
                now = time.monotonic()

                if name == "accept":
                    accept_time = now
                    clean_sequence = True
                elif name == "leave" and last_tapped != "leave":
                    if accept_time is not None and clean_sequence:
                        match_durations.append(now - accept_time)
                    accept_time = None
                    clean_sequence = False

                    if last_leave_time is not None:
                        interval = now - last_leave_time
                        if interval <= 360:
                            leave_intervals.append(interval)
                    last_leave_time = now
                    leave_count += 1

                    avg_duration = sum(match_durations) / len(match_durations) if match_durations else 0
                    draw_header(header_win, len(match_durations), avg_duration)
                elif name not in ("leave",):
                    # any other tap (okay, auto_match, ads) invalidates the accept→leave window
                    if accept_time is not None:
                        clean_sequence = False

                ts = time.strftime("%H:%M:%S")
                log(log_win, f"[{ts}] '{name}' matched (conf={confidence:.2f}) → tapped ({cx}, {cy})")
                last_tapped = name
                clicked = True
                break

        if clicked:
            time.sleep(CLICK_COOLDOWN)


def main():
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
