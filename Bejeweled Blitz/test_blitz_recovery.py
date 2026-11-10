"""Offline regression checks; no browser, input events, or extra packages."""

import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

import blitz_bot
from gem_vision import read_board
from native_pixels import Frame


BOARD = tuple(tuple(map(int, row.split())) for row in (
    "2 3 4 1 5 5 6 1", "3 1 7 2 1 6 7 6", "4 2 3 5 3 5 1 1",
    "6 1 7 2 6 7 5 3", "6 4 2 7 6 4 2 3", "4 2 5 1 1 5 6 2",
    "1 1 6 2 1 4 5 7", "1 1 2 7 6 2 2 3",
))
PARTIAL = BOARD[:7] + ((None,) * 8,)
COLORS = ((0, 0, 0), (240, 10, 10), (240, 128, 10), (240, 240, 10),
          (10, 230, 20), (10, 128, 240), (240, 10, 240), (230, 230, 230))


def make_frame(board):
    data = bytearray()
    for y in range(341):
        for x in range(320):
            r, g, b = (0, 200, 240) if y >= 320 else COLORS[board[y // 40][x // 40] or 0]
            data.extend((b, g, r, 255))
    return Frame(bytes(data), 320, 341)


class RecoveryTests(unittest.TestCase):
    def test_ambiguous_edges_use_central_color(self):
        class EffectFrame:
            width = height = 320

            def pixel(self, x, y):
                x, y = (x % 40) / 40, (y % 40) / 40
                if .34 <= x <= .66 and .34 <= y <= .66:
                    return COLORS[5]
                return COLORS[1] if y < .45 else (10, 10, 10)

        self.assertEqual(read_board(EffectFrame()), ((5,) * 8,) * 8)

    def test_missing_gems_stay_unknown(self):
        self.assertEqual(read_board(make_frame(PARTIAL).crop(0, 0, 320, 320)), PARTIAL)

    def test_eight_unknown_gems_allow_a_stable_local_move(self):
        move = blitz_bot.best_move(PARTIAL, previous=PARTIAL)
        self.assertIsNotNone(move)
        trial = [list(row) for row in PARTIAL]
        (r, c), (rr, cc) = move
        trial[r][c], trial[rr][cc] = trial[rr][cc], trial[r][c]
        self.assertTrue(any(set(move) & run for run in blitz_bot.runs(trial)))

    def test_changing_cells_are_not_clicked(self):
        previous = tuple(tuple(v % 7 + 1 if v else None for v in row) for row in PARTIAL)
        self.assertIsNone(blitz_bot.best_move(PARTIAL, previous=previous))

    def test_long_interference_recovers_in_script_and_notebook(self):
        nb = json.loads(Path(__file__).with_name("寶石方塊自動遊玩.ipynb").read_text(encoding="utf-8"))
        notebook = {"__name__": "blitz_notebook_test"}
        for cell in nb["cells"]:
            if cell["cell_type"] == "code" and cell.get("id") != "run-game":
                exec(compile("".join(cell["source"]), "<notebook>", "exec"), notebook)
        frames = [make_frame(PARTIAL), make_frame(tuple(
            tuple(v % 7 + 1 if v else None for v in row) for row in PARTIAL
        ))]
        for namespace in (blitz_bot.__dict__, notebook):
            with self.subTest(runtime=namespace["__name__"]):
                events = []

                class Clock:
                    ticks = 0
                    strftime = staticmethod(time.strftime)
                    time_ns = staticmethod(time.time_ns)

                    def monotonic(self):
                        self.ticks += .25
                        return self.ticks

                    def sleep(self, seconds):
                        pass

                clock = Clock()

                class Window:
                    def check(self):
                        if events:
                            raise KeyboardInterrupt

                    def game_window(self):
                        return 123

                    def swap(self, *args):
                        events.append(clock.ticks)
                        return True

                class Capture:
                    count = 0

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        pass

                    def grab(self, region):
                        self.count += 1
                        return frames[self.count % 2] if self.count <= 30 else frames[0]

                diagnostics = Mock()
                with patch.dict(namespace, Windows=Window, Capture=Capture, time=clock,
                                LOG=Mock(), save_diagnostics=diagnostics,
                                calibrate=lambda win: (123, (100, 200, 320, 320))):
                    with self.assertRaises(KeyboardInterrupt):
                        namespace["play"](False, manual=True)
                self.assertEqual(len(events), 1)
                self.assertGreater(events[0], 12)
                diagnostics.assert_called_once()


if __name__ == "__main__":
    unittest.main()
