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
    "stuck": "./images/stuck_button.png",  # restart queue
}
THRESHOLD = 0.85  # match confidence (0–1); lower = more lenient
CLICK_COOLDOWN = 2.0  # seconds to wait after a tap before checking again
STUCK_DELAY = 120.0  # seconds after auto_match before checking for the stuck prompt
STUCK_CONF = 0.92  # require higher confidence for stuck to avoid false positives
TAP_DURATION_MS = 100  # milliseconds for each tap swipe


def adb(*args) -> bytes:
    result = subprocess.run(
        ["adb", "-s", ADB_HOST, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
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


def tap(x: int, y: int, duration_ms: int = TAP_DURATION_MS):
    adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms))


def connect():
    subprocess.run(
        ["adb", "connect", ADB_HOST],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def draw_header(win, matches: int, avg_duration: float):
    try:
        avg_str = f"{avg_duration / 60:.1f}min" if matches > 0 else "n/a"
        _, width = win.getmaxyx()
        if width <= 0:
            return
        text = f" matches: {matches}  |  avg match duration: {avg_str} "
        n = max(0, width - 2)
        text = text.ljust(n) if len(text) < n else text[:n]

        win.erase()
        if len(text) > 0 and width > 1:
            try:
                win.addnstr(0, 0, text, n, curses.A_REVERSE)
            except curses.error:
                win.addnstr(0, 0, text, n)
        win.refresh()
    except curses.error:
        pass


def log(win, msg: str):
    win.addstr(msg + "\n")
    win.refresh()


def close_ads_and_resume(log_win, templates: dict) -> bool:
    """
    After a dismissal tap (okay or stuck), check for and close any ad overlays,
    then tap auto_match if visible. Returns True if auto_match was tapped.
    """
    screen = screencap()
    for xn in ("x3", "x2", "x1"):
        conf_x, loc_x = find_button(screen, templates[xn])
        if conf_x >= THRESHOLD:
            th_x, tw_x = templates[xn].shape[:2]
            cx_x = loc_x[0] + tw_x // 2
            cy_x = loc_x[1] + th_x // 2
            tap(cx_x, cy_x)
            ts = time.strftime("%H:%M:%S")
            log(log_win, f"[{ts}] {xn.ljust(10)} matched (conf={conf_x:.2f}) → tapped ({cx_x}, {cy_x})")
            time.sleep(0.5)
            screen = screencap()

    conf_am, loc_am = find_button(screen, templates["auto_match"])
    if conf_am >= THRESHOLD:
        th_am, tw_am = templates["auto_match"].shape[:2]
        cx_am = loc_am[0] + tw_am // 2
        cy_am = loc_am[1] + th_am // 2
        tap(cx_am, cy_am)
        ts = time.strftime("%H:%M:%S")
        log(log_win, f"[{ts}] {'auto_match'.ljust(10)} matched (conf={conf_am:.2f}) → tapped ({cx_am}, {cy_am})")
        return True

    return False


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

    last_tapped = None
    accept_time = None  # time accept was tapped; cleared on leave or interruption
    clean_sequence = False  # True only if no other taps occurred between accept and leave
    match_durations = []

    in_matchmaking = False  # True from auto_match tap until leave tap
    last_auto_match_time = None  # used to gate stuck detection by STUCK_DELAY

    while True:
        screen = screencap()

        clicked = False
        for name, template in templates.items():
            if name == "stuck":
                # only check for stuck while actively matchmaking and after STUCK_DELAY
                if not in_matchmaking:
                    continue
                if last_auto_match_time is None:
                    continue
                if (time.monotonic() - last_auto_match_time) < STUCK_DELAY:
                    continue

            confidence, loc = find_button(screen, template)

            if name == "stuck":
                # require higher confidence for stuck
                if confidence < STUCK_CONF:
                    continue
                # if auto_match is also visible at this confidence, we are on the main
                # menu and this is a false positive; skip
                conf_am, _ = find_button(screen, templates["auto_match"])
                if conf_am >= THRESHOLD:
                    continue

            if confidence < THRESHOLD:
                continue

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
                in_matchmaking = False
                last_auto_match_time = None

                avg_duration = sum(match_durations) / len(match_durations) if match_durations else 0
                draw_header(header_win, len(match_durations), avg_duration)

            elif name == "auto_match":
                in_matchmaking = True
                last_auto_match_time = now

            elif name == "okay":
                if accept_time is not None:
                    clean_sequence = False
                try:
                    time.sleep(0.5)
                    # okay may reveal the stuck prompt before ads; check first
                    new_screen = screencap()
                    conf_stuck, loc_stuck = find_button(new_screen, templates["stuck"])
                    if conf_stuck >= STUCK_CONF:
                        th_s, tw_s = templates["stuck"].shape[:2]
                        cx_s = loc_stuck[0] + tw_s // 2
                        cy_s = loc_stuck[1] + th_s // 2
                        tap(cx_s, cy_s)
                        ts = time.strftime("%H:%M:%S")
                        log(
                            log_win,
                            f"[{ts}] {'stuck'.ljust(10)} matched (conf={conf_stuck:.2f}) → tapped ({cx_s}, {cy_s})",
                        )
                        time.sleep(0.5)
                    resumed = close_ads_and_resume(log_win, templates)
                    if resumed:
                        last_auto_match_time = time.monotonic()
                        in_matchmaking = True
                except Exception:
                    pass

            elif name == "stuck":
                if accept_time is not None:
                    clean_sequence = False
                # reset timer so stuck is not immediately re-detected
                last_auto_match_time = now
                try:
                    time.sleep(0.5)
                    resumed = close_ads_and_resume(log_win, templates)
                    if resumed:
                        last_auto_match_time = time.monotonic()
                        in_matchmaking = True
                except Exception:
                    pass

            else:
                # ad close buttons (x1, x2, x3)
                if accept_time is not None:
                    clean_sequence = False

            ts = time.strftime("%H:%M:%S")
            log(log_win, f"[{ts}] {name.ljust(10)} matched (conf={confidence:.2f}) → tapped ({cx}, {cy})")
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
