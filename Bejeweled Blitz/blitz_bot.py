"""Open Bejeweled Blitz in Chrome and play successive rounds on Windows."""

import argparse
import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time

from native_pixels import Capture, read_image
from gem_vision import read_board, read_flames, countdown_visible, timer_active, find_board
from menu_buttons import MenuButtons


SIZE = 8
COLORS = (1, 2, 3, 4, 5, 6, 7)
F2, F8 = 0x71, 0x77
LOG = logging.getLogger(__name__)
LOG_PATH = Path(__file__).with_name("blitz-last-run.log")


def runs(board):
    found = []
    for vertical in (False, True):
        for line in range(SIZE):
            cells = [(i, line) if vertical else (line, i) for i in range(SIZE)]
            start = 0
            while start < SIZE:
                row, col = cells[start]
                color = board[row][col]
                end = start + 1
                while end < SIZE:
                    row, col = cells[end]
                    if board[row][col] != color:
                        break
                    end += 1
                if color is not None and end - start >= 3:
                    found.append(set(cells[start:end]))
                start = end
    return found


def predict_value(board, matches, can_predict_cascades):
    # Use only visible gems when estimating cascades. New gems are unknown.
    value = 0
    for step in range(4 if can_predict_cascades else 1):
        if not matches:
            break
        removed = set.union(*matches)
        longest = max(map(len, matches))
        intersects = sum(map(len, matches)) > len(removed)
        special_bonus = 12 if longest >= 5 else 8 if intersects else 4 if longest == 4 else 0
        value += (2 * len(removed) + special_bonus) / (step + 1)
        for col in range(SIZE):
            kept = [board[row][col] for row in range(SIZE) if (row, col) not in removed]
            for row, gem in enumerate([None] * (SIZE - len(kept)) + kept):
                board[row][col] = gem
        matches = runs(board)
    return value


def best_move(board, flames=frozenset()):
    best = None
    best_value = (-1, -1)
    complete = all(None not in row for row in board)
    for row in range(SIZE):
        for col in range(SIZE):
            source = board[row][col]
            if source is None:
                continue
            for r, c in ((row + 1, col), (row, col + 1)):
                if r >= SIZE or c >= SIZE or board[r][c] in (source, None):
                    continue
                trial = [list(line) for line in board]
                trial[row][col], trial[r][c] = trial[r][c], trial[row][col]
                matches = runs(trial)
                if not any((row, col) in run or (r, c) in run for run in matches):
                    continue
                source_cell, target_cell = (row, col), (r, c)
                moved_flames = {
                    target_cell if cell == source_cell else source_cell if cell == target_cell else cell
                    for cell in flames
                }
                triggered = len(set.union(*matches) & moved_flames)
                # Explosion outcomes need new screen evidence, so avoid predicting their cascades.
                value = (triggered, predict_value(trial, matches, complete and not triggered))
                if value > best_value:
                    best = ((row, col), (r, c))
                    best_value = value
    return best


class Windows:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SetProcessDPIAware()
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user.mouse_event.argtypes = [wintypes.DWORD] * 4 + [ctypes.c_size_t]

    def pressed(self, key):
        return bool(self.user.GetAsyncKeyState(key) & 0x8000)

    def check(self):
        if self.pressed(F8):
            raise KeyboardInterrupt

    def wait_in_game(self, window=None):
        while True:
            while not self.pressed(F2):
                self.check()
                time.sleep(0.015)
            while self.pressed(F2):
                self.check()
                time.sleep(0.015)
            self.check()
            active = self.game_window()
            if active is not None and (window is None or active == window):
                return active
            LOG.warning("這次 F2 已略過。請切回原本的 Chrome 遊戲分頁再按 F2。")

    def game_window(self):
        window = self.user.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(512)
        self.user.GetWindowTextW(window, title, len(title))
        if "bejeweled blitz" not in title.value.lower() or "chrome" not in title.value.lower():
            return None
        return window

    def find_game_window(self):
        found = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(window, parameter):
            title = ctypes.create_unicode_buffer(512)
            self.user.GetWindowTextW(window, title, len(title))
            text = title.value.lower()
            if self.user.IsWindowVisible(window) and "bejeweled blitz" in text and "chrome" in text:
                found.append(window)
            return True
        callback = callback_type(visit)
        self.user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self.user.EnumWindows(callback, 0)
        return found[0] if found else None

    def open_game(self):
        window = self.find_game_window()
        if window is None:
            candidates = [shutil.which("chrome")]
            for base in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
                candidates.append(str(Path(os.environ.get(base, "")) / "Google/Chrome/Application/chrome.exe"))
            executable = next((p for p in candidates if p and Path(p).is_file()), None)
            if executable is None:
                raise ValueError("找不到 Google Chrome，請先在 Chrome 開啟 Bejeweled Blitz。")
            subprocess.Popen(
                [executable, "--new-window", "--start-maximized", "https://apps.facebook.com/bejeweledblitz"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        LOG.info("正在等待 Chrome 遊戲頁面。若 Facebook 要求登入，請完成登入。")
        deadline = time.monotonic() + 120
        while window is None and time.monotonic() < deadline:
            self.check()
            window = self.find_game_window()
            time.sleep(0.1)
        if window is None:
            raise ValueError("兩分鐘內未找到遊戲頁面，請確認已登入 Facebook。")
        self.user.ShowWindow(window, 3)
        self.user.SetForegroundWindow(window)
        return window

    def click(self, window, point):
        self.check()
        if self.game_window() != window:
            return False
        self.move_cursor(point)
        if self.game_window() != window:
            return False
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            time.sleep(0.06)
        finally:
            self.user.mouse_event(0x0004, 0, 0, 0, 0)
        return True

    def cursor(self):
        point = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        return point.x, point.y

    def window_region(self, window, desktop):
        bounds = wintypes.RECT()
        if not self.user.GetWindowRect(window, ctypes.byref(bounds)):
            raise ctypes.WinError(ctypes.get_last_error())
        left = max(bounds.left, desktop["left"])
        top = max(bounds.top, desktop["top"])
        right = min(bounds.right, desktop["left"] + desktop["width"])
        bottom = min(bounds.bottom, desktop["top"] + desktop["height"])
        if right <= left or bottom <= top:
            raise ValueError("Chrome 遊戲視窗在螢幕範圍外。")
        return dict(left=left, top=top, width=right - left, height=bottom - top)

    def move_cursor(self, point):
        if not self.user.SetCursorPos(*point):
            raise ctypes.WinError(ctypes.get_last_error())

    def swap(self, window, source, target):
        self.check()
        if self.game_window() != window:
            return False
        self.move_cursor(source)
        self.check()
        if self.game_window() != window:
            return False
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            for step in range(1, 5):
                time.sleep(0.012)
                self.check()
                if self.game_window() != window:
                    return False
                self.move_cursor(tuple(a + (b - a) * step // 4 for a, b in zip(source, target)))
        finally:
            self.user.mouse_event(0x0004, 0, 0, 0, 0)
        return True


def print_board(board, flames=frozenset()):
    for r, row in enumerate(board):
        print(" ".join(str(color or 0) + ("F" if (r, c) in flames else " ")
                       for c, color in enumerate(row)))


def describe(move):
    return " → ".join(f"第 {r + 1} 列第 {c + 1} 欄" for r, c in move)


def calibrate(win):
    LOG.info("切到 Chrome 的 Bejeweled Blitz。指向棋盤左上角，按 F2。")
    window = win.wait_in_game()
    left, top = win.cursor()
    LOG.info("已記錄左上角 (%d, %d)。指向棋盤右下角，再按 F2。", left, top)
    win.wait_in_game(window)
    right, bottom = win.cursor()
    width, height = right - left, bottom - top
    LOG.info("已記錄右下角 (%d, %d)。框選大小 %d × %d。", right, bottom, width, height)
    if min(width, height) < 160 or abs(width - height) > 0.08 * max(width, height):
        raise ValueError("框選範圍應為包含 8×8 格的正方形棋盤，請重新啟動。")
    LOG.info("按第三次 F2 待命，再用滑鼠按遊戲的開始按鈕。隨時按 F8 停止。")
    win.wait_in_game(window)
    return window, (left, top, width, height)


def play(dry_run, manual=False, wait_key=False, window=None):
    win = Windows()
    automatic = not (manual or wait_key or dry_run)
    if manual:
        window, bounds = calibrate(win)
    elif not automatic:
        LOG.info("切到 Chrome 的 Bejeweled Blitz，按一次 F2 待命，再用滑鼠開局。F8 停止。")
        window = win.wait_in_game()
        bounds = None
    else:
        window = window or win.open_game()
        bounds = None
    LOG.info("等待開局。F8 可隨時停止。")
    started = time.monotonic()
    deadline = started + (180 if automatic else 30)
    previous = last_move_board = None
    previous_flames = set()
    moves = 0
    idle_since = started
    last_timer_seen = None
    away = False
    region = None
    menus = MenuButtons() if automatic else None
    last_button_time = 0
    pending_button = None
    with Capture() as capture:
        while time.monotonic() < deadline:
            win.check()
            if win.game_window() != window:
                if not away:
                    LOG.info("已暫停。切回原本的 Chrome 遊戲分頁即可繼續。")
                    away = True
                previous = None
                time.sleep(0.05)
                continue
            if away:
                LOG.info("已切回遊戲分頁，繼續偵測棋盤。")
                away = False
                idle_since = time.monotonic()
            if bounds is None:
                search = win.window_region(window, capture.monitors[0])
                screen = capture.grab(search)
                if menus is not None:
                    button = menus.find(screen)
                    if button is not None:
                        name, point = button
                        now = time.monotonic()
                        stable_button = (
                            pending_button is not None and name == pending_button[0]
                            and max(abs(a-b) for a,b in zip(point, pending_button[1])) <= 3
                        )
                        if stable_button and now - last_button_time > 2:
                            position = (search["left"] + point[0], search["top"] + point[1])
                            if win.click(window, position):
                                LOG.info("已自動按下 %s。", name)
                                last_button_time = now
                                pending_button = None
                        else:
                            pending_button = button
                        time.sleep(0.12)
                        continue
                    pending_button = None
                location = find_board(screen)
                if location is None:
                    time.sleep(0.08)
                    continue
                x, y, width, height = location
                bounds = (search["left"] + x, search["top"] + y, width, height)
                LOG.info("已自動找到棋盤：左上角 (%d, %d)，大小 %d × %d。", *bounds)
            if region is None:
                left, top, width, height = bounds
                region = dict(left=left, top=top, width=width, height=height + round(height * 0.065))
                bar_start = height + round(height * 0.024)
                bar_end = height + round(height * 0.056)
            frame = capture.grab(region)
            board_frame = frame.crop(0, 0, width, height)
            now = time.monotonic()
            # Sample the left end of the bar, which stays filled until late in the round.
            if timer_active(frame.crop(width // 80, bar_start, width // 25 - width // 80, bar_end - bar_start)):
                if last_timer_seen is None:
                    LOG.info("已偵測到時間條。")
                    deadline = now + 63
                    idle_since = now
                last_timer_seen = now
            else:
                previous = None
                if last_timer_seen is not None and now - last_timer_seen > 1.4:
                    break
                time.sleep(0.03)
                continue
            if countdown_visible(board_frame):
                previous = None
                time.sleep(0.03)
                continue
            board = read_board(board_frame)
            flames = read_flames(board_frame, board)
            confirmed_flames = flames & previous_flames
            previous_flames = flames
            unknown = sum(row.count(None) for row in board)
            readable = unknown <= 2 and not runs(board)
            if readable and board == previous and board != last_move_board:
                move = best_move(board, confirmed_flames)
                if move is not None:
                    if dry_run:
                        print_board(board, confirmed_flames)
                        print(f"建議交換 {describe(move)}", flush=True)
                    else:
                        points = [
                            (left + int((c + 0.5) * width / SIZE), top + int((r + 0.5) * height / SIZE))
                            for r, c in move
                        ]
                        if not win.swap(window, *points):
                            previous = None
                            continue
                        moves += 1
                        LOG.debug("第 %d 次交換 %s；火焰格 %s；編號棋盤 %s", moves, describe(move), sorted(confirmed_flames), board)
                    last_move_board = board
                    idle_since = time.monotonic()
            previous = board if readable else None
            if not dry_run and now - idle_since > 6:
                if board == last_move_board:
                    raise ValueError("已送出交換，但六秒後棋盤仍相同。請確認遊戲仍在進行。")
                if unknown > 2:
                    raise ValueError(f"棋盤有 {unknown} 格無法辨識。請確認棋盤完整可見並重新框選。")
                raise ValueError("六秒內沒有找到可執行的走法。請確認框選範圍。")
            time.sleep(0.035)
    if last_timer_seen is None:
        raise ValueError("等待逾時，未找到完整棋盤。請確認遊戲已載入、畫面完整可見，或使用 --wait-key 手動開局。")
    LOG.info("本輪已停止。送出 %d 次交換，分數請查看遊戲結算畫面。", moves)
    return window


def configure_log():
    LOG.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    LOG.addHandler(console)
    try:
        log_file = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    except OSError as error:
        LOG.warning("無法寫入診斷記錄：%s", error)
        return
    log_file.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    LOG.addHandler(log_file)
    LOG.info("診斷記錄存於 %s。", LOG_PATH)


def main():
    parser = argparse.ArgumentParser(description="Bejeweled Blitz 棋盤辨識與自動交換")
    parser.add_argument("--dry-run", action="store_true", help="只列出辨識結果和建議走法")
    parser.add_argument("--manual", action="store_true", help="以 F2 手動框選棋盤")
    parser.add_argument("--wait-key", action="store_true", help="按 F2 待命並手動開局")
    parser.add_argument("--once", action="store_true", help="只玩一局後結束")
    parser.add_argument("--inspect", help="離線讀取一張截圖")
    parser.add_argument("--board", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    args = parser.parse_args()
    if args.inspect:
        if not args.board:
            parser.error("--inspect 需要 --board X Y W H")
        image = read_image(args.inspect)
        x, y, width, height = args.board
        if min(x, y) < 0 or min(width, height) < 8 or (
            x + width > image.width or y + height > image.height
        ):
            parser.error("截圖或棋盤範圍無效")
        frame = image.crop(x, y, width, height)
        board = read_board(frame)
        flames = read_flames(frame, board)
        print_board(board, flames)
        if countdown_visible(frame):
            print("開局倒數遮住棋盤，略過走法。")
        elif any(None in row for row in board) or runs(board):
            print("棋盤尚未辨識完整或有寶石正在消除。")
        else:
            move = best_move(board, flames)
            print(f"建議交換 {describe(move)}" if move else "沒有找到合法交換。")
        return 0
    configure_log()
    try:
        window = play(args.dry_run, args.manual, args.wait_key)
        while not (args.once or args.dry_run or args.manual or args.wait_key):
            window = play(False, window=window)
    except KeyboardInterrupt:
        LOG.info("已停止。")
    except (OSError, ValueError) as error:
        LOG.error("停止原因：%s", error)
        return 1
    except Exception:
        LOG.exception("程式發生未預期的錯誤。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
