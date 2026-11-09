"""Play a manually started Bejeweled Blitz round in Chrome on Windows."""

import argparse
import ctypes
from ctypes import wintypes
import logging
from pathlib import Path
import time

import cv2
import mss
import numpy as np


SIZE = 8
COLORS = "ROYGBPW"
F2, F8 = 0x71, 0x77
LOG = logging.getLogger(__name__)
LOG_PATH = Path(__file__).with_name("blitz-last-run.log")


def read_board(frame):
    hsv = cv2.cvtColor(cv2.resize(frame, (256, 256)), cv2.COLOR_BGR2HSV)
    tiles = hsv.reshape(8, 32, 8, 32, 3).transpose(0, 2, 1, 3, 4)
    hue, sat, value = tiles[:, :, 7:25, 7:25, :].transpose(4, 0, 1, 2, 3)
    bright = (sat >= 100) & (value >= 95)
    masks = (
        bright & ((hue <= 8) | (hue >= 172)),
        bright & (hue >= 9) & (hue <= 21),
        bright & (hue >= 22) & (hue <= 38),
        bright & (hue >= 39) & (hue <= 82),
        bright & (hue >= 83) & (hue <= 125),
        bright & (hue >= 126) & (hue <= 171),
        (sat <= 80) & (value >= 145),
    )
    counts = np.stack([mask.sum(axis=(2, 3)) for mask in masks])
    ranked = np.sort(counts, axis=0)
    clear = (ranked[-1] >= 100) & (ranked[-1] - ranked[-2] >= 55)
    return tuple(
        tuple(COLORS[color] if valid else None for color, valid in zip(row, good))
        for row, good in zip(counts.argmax(axis=0), clear)
    )


def countdown_visible(frame):
    height, width = frame.shape[:2]
    middle = frame[3 * height // 8:5 * height // 8, width // 3:2 * width // 3]
    blue, green, red = middle.transpose(2, 0, 1)
    return np.mean((green >= 250) & (blue <= 4) & (red <= 4)) > 0.035


def timer_mask(frame):
    hue, sat, value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).transpose(2, 0, 1)
    return (hue >= 83) & (hue <= 107) & (sat >= 100) & (value >= 100)


def find_board(frame):
    # At the start of a round the filled bar spans almost the entire grid.
    mask = timer_mask(frame).astype(np.uint8)
    _, _, components, _ = cv2.connectedComponentsWithStats(mask)
    for x, y, length, thickness, area in sorted(components[1:], key=lambda item: item[2], reverse=True):
        if length < 150 or not 14 * thickness <= length <= 29 * thickness:
            continue
        if area < 0.7 * length * thickness:
            continue
        side = round(length * 1.013)
        left = int(x) - round(side * 0.008)
        top = int(y) - round(side * 0.018) - side
        if left < 0 or top < 0 or left + side > frame.shape[1]:
            continue
        board_frame = frame[top:top + side, left:left + side]
        gems = [gem for row in read_board(board_frame) for gem in row if gem is not None]
        if len(gems) >= 60 and len(set(gems)) >= 5:
            return left, top, side, side
    return None


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


def best_move(board):
    best = None
    best_value = 0
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
                value = predict_value(trial, matches, complete)
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


def print_board(board):
    for row in board:
        print(" ".join(color or "?" for color in row))


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


def play(dry_run, manual=False):
    win = Windows()
    if manual:
        window, bounds = calibrate(win)
    else:
        LOG.info("切到 Chrome 的 Bejeweled Blitz，按一次 F2 待命，再用滑鼠開局。F8 停止。")
        window = win.wait_in_game()
        bounds = None
    LOG.info("已待命，等待開局。")
    started = time.monotonic()
    deadline = started + 30
    previous = last_move_board = None
    moves = 0
    idle_since = started
    last_timer_seen = None
    away = False
    region = None
    with mss.MSS() as capture:
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
                screen = np.asarray(capture.grab(search))[:, :, :3]
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
            frame = np.asarray(capture.grab(region))[:, :, :3]
            board_frame = frame[:height]
            now = time.monotonic()
            # Sample the left end of the bar, which stays filled until late in the round.
            if timer_mask(frame[bar_start:bar_end, width // 80:width // 25]).mean() > 0.25:
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
            unknown = sum(row.count(None) for row in board)
            readable = unknown <= 2 and not runs(board)
            if readable and board == previous and board != last_move_board:
                move = best_move(board)
                if move is not None:
                    if dry_run:
                        print_board(board)
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
                        LOG.debug("第 %d 次交換 %s", moves, describe(move))
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
        raise ValueError("待命 30 秒仍未找到棋盤和時間條。請保持棋盤完整可見，並在開局前先按 F2。")
    LOG.info("本輪已停止。送出 %d 次交換，分數請查看遊戲結算畫面。", moves)


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
    parser.add_argument("--inspect", help="離線讀取一張截圖")
    parser.add_argument("--board", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    args = parser.parse_args()
    if args.inspect:
        if not args.board:
            parser.error("--inspect 需要 --board X Y W H")
        image = cv2.imdecode(np.fromfile(args.inspect, np.uint8), cv2.IMREAD_COLOR)
        x, y, width, height = args.board
        if image is None or min(x, y) < 0 or min(width, height) < 8 or (
            x + width > image.shape[1] or y + height > image.shape[0]
        ):
            parser.error("截圖或棋盤範圍無效")
        frame = image[y:y + height, x:x + width]
        board = read_board(frame)
        print_board(board)
        if countdown_visible(frame):
            print("開局倒數遮住棋盤，略過走法。")
        elif any(None in row for row in board) or runs(board):
            print("棋盤尚未辨識完整或有寶石正在消除。")
        else:
            move = best_move(board)
            print(f"建議交換 {describe(move)}" if move else "沒有找到合法交換。")
        return 0
    configure_log()
    try:
        play(args.dry_run, args.manual)
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
