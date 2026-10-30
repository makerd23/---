"""No desktop capture or simulated keys."""
import unittest
from types import SimpleNamespace

from dino_bot import choose_action, sample_hits, scan_edges, scan_region, estimate_speed, advance_pixels


class CoordinateTests(unittest.TestCase):
    def test_region_detects_obstacles_between_old_lanes(self):
        for background, ink in ((0xffffff, 0), (0, 0xffffff)):
            for obstacle_top in (52, 67, 91):
                def get_pixel(dc, x, y):
                    return ink if 120 <= x <= 132 and obstacle_top <= y <= obstacle_top+6 else background
                frame = SimpleNamespace(gdi=SimpleNamespace(GetPixel=get_pixel))
                self.assertEqual(scan_region(frame, None, (100, 50, 140, 100), 65), [120])

    def test_region_ignores_ground_below_bounds(self):
        frame = SimpleNamespace(gdi=SimpleNamespace(
            GetPixel=lambda dc, x, y: 0 if y >= 110 else 0xffffff))
        self.assertEqual(scan_region(frame, None, (100, 50, 140, 100), 65), [])

    def test_acceleration_moves_trigger_forward(self):
        speed = 360
        for _ in range(12):
            speed = estimate_speed(([240], []), ([210], []), 0.05, speed, (82, 82))
        self.assertGreater(speed, 550)
        self.assertGreater(advance_pixels(speed, 0.22), 40)
        self.assertEqual(advance_pixels(360, 0.22), 0)
        self.assertLessEqual(advance_pixels(1800, 0.5), 160)

    def test_unmatched_or_clipped_obstacles_do_not_change_speed(self):
        self.assertEqual(estimate_speed(([240], []), ([], []), .05, 360, (82, 82)), 360)
        self.assertEqual(estimate_speed(([110], []), ([82], []), .05, 360, (82, 82)), 360)

    def test_scan_tracks_moving_edge_and_detects_it_after_crossing_trigger(self):
        for background, obstacle in ((0xffffff, 0), (0, 0xffffff)):
            for left in (180, 160, 96):
                def get_pixel(dc, x, y):
                    return obstacle if left <= x < left+20 and 80 <= y <= 90 else background
                frame = SimpleNamespace(gdi=SimpleNamespace(GetPixel=get_pixel))
                edges = scan_edges(frame, None, (100, 85), 65)
                self.assertEqual(len(edges), 1)
                self.assertLess(abs(edges[0]-left), 4)
                self.assertEqual(edges[0] <= 100, left == 96)

    def test_both_points_trigger_jump(self):
        self.assertEqual(choose_action(4, 4, True), 'jump')
        self.assertEqual(choose_action(4, 0, True), 'jump')

    def test_upper_bird_jumps(self):
        self.assertEqual(choose_action(0, 4, True), 'jump')

    def test_wait_during_jump_cooldown(self):
        self.assertEqual(choose_action(4, 4, False), 'wait')
        self.assertEqual(choose_action(0, 4, False), 'wait')

    def test_blank_or_single_pixel_noise_waits(self):
        self.assertEqual(choose_action(0, 0, True), 'wait')
        self.assertEqual(choose_action(1, 1, True), 'wait')

    def test_two_points_are_sampled_independently_day_and_night(self):
        for background, obstacle in ((0xffffff, 0), (0, 0xffffff)):
            # Only the upper point intersects an obstacle.
            def get_pixel(dc, x, y):
                return obstacle if 82 <= x <= 100 and 50 <= y <= 60 else background
            win = SimpleNamespace(gdi=SimpleNamespace(GetPixel=get_pixel))
            self.assertEqual(sample_hits(win, None, (100, 85), 65), 0)
            self.assertEqual(sample_hits(win, None, (100, 55), 65), 12)


if __name__ == '__main__':
    unittest.main()
