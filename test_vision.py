"""Synthetic vision checks; does not send keys or capture the desktop."""
import unittest

import cv2
import numpy as np

from dino_vision import foreground_mask, obstacles


class VisionTests(unittest.TestCase):
    def scene(self, night=False, scale=1):
        background, ink = (0, 255) if night else (255, 0)
        frame = np.full((180*scale, 600*scale, 3), background, np.uint8)
        def rect(x1, y1, x2, y2):
            cv2.rectangle(frame, (x1*scale, y1*scale),
                          (x2*scale, y2*scale), (ink,)*3, -1)
        rect(50, 93, 93, 139)  # dinosaur
        rect(0, 140, 599, 141)  # ground must not become an obstacle
        rect(200, 100, 219, 139)  # cactus
        rect(320, 80, 349, 95)  # bird
        rect(500, 10, 510, 20)  # score region must be ignored
        return frame

    def test_day_night_and_scaled_obstacles(self):
        for night in (False, True):
            for scale in (1, 2):
                with self.subTest(night=night, scale=scale):
                    dino = [v*scale for v in (50, 93, 44, 47)]
                    boxes = obstacles(foreground_mask(self.scene(night, scale)), dino)
                    self.assertEqual(len(boxes), 2)
                    self.assertEqual([box[0] for box in boxes], [200*scale, 320*scale])

    def test_blank_frame_has_no_obstacles(self):
        frame = np.full((180, 600, 3), 255, np.uint8)
        self.assertEqual(obstacles(foreground_mask(frame), [50, 93, 44, 47]), [])


if __name__ == '__main__':
    unittest.main()
