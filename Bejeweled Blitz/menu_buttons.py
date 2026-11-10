"""Recognize only the supplied PLAY / PLAY AGAIN / NO THANKS button images."""

import json
from pathlib import Path


def button_color(pixel):
    red, green, blue = pixel
    return max(red, blue) >= 100 and min(red, blue) >= 45 and green < 85 and min(red, blue) > green * 1.8


def button_boxes(frame, step=3):
    points = {
        (x, y) for y in range(0, frame.height, step) for x in range(0, frame.width, step)
        if button_color(frame.pixel(x, y))
    }
    boxes = []
    while points:
        seed = points.pop()
        pending = [seed]
        left = right = seed[0]
        top = bottom = seed[1]
        count = 0
        while pending:
            x, y = pending.pop()
            count += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for neighbor in ((x-step, y), (x+step, y), (x, y-step), (x, y+step)):
                if neighbor in points:
                    points.remove(neighbor)
                    pending.append(neighbor)
        width, height = min(frame.width, right + step) - left, min(frame.height, bottom + step) - top
        if 60 <= width <= 460 and 14 <= height <= 120 and 1.9 <= width / height <= 7:
            if count * step * step >= width * height * 0.35:
                boxes.append((left, top, width, height))
    return boxes


def signature(frame):
    values = []
    for row in range(16):
        for col in range(40):
            x = min(frame.width-1, int((col + 0.5) * frame.width / 40))
            y = min(frame.height-1, int((row + 0.5) * frame.height / 16))
            values.append(frame.pixel(x, y))
    return values


def white(pixel):
    return min(pixel) >= 165 and max(pixel) - min(pixel) < 85


class MenuButtons:
    def __init__(self):
        path = Path(__file__).with_name("menu_buttons.json")
        self.references = json.loads(path.read_text(encoding="utf-8"))

    def find(self, frame):
        matches = []
        for x, y, width, height in button_boxes(frame):
            left, top = max(0, x-4), max(0, y-4)
            crop = frame.crop(left, top, min(frame.width, x+width+4)-left, min(frame.height, y+height+4)-top)
            refined = button_boxes(crop, step=1)
            if not refined:
                continue
            dx, dy, width, height = max(refined, key=lambda box: box[2]*box[3])
            x, y = left+dx, top+dy
            pixels = signature(frame.crop(x, y, width, height))
            for reference in self.references:
                if abs(width / height / reference["aspect"] - 1) > 0.18:
                    continue
                samples = reference["pixels"]
                error = sum(abs(a-b) for p, q in zip(pixels, samples) for a,b in zip(p,q)) / (len(pixels)*3)
                text_union = sum(white(p) or white(q) for p,q in zip(pixels,samples))
                text_overlap = sum(white(p) and white(q) for p,q in zip(pixels,samples))
                overlap = text_overlap / max(1, text_union)
                if error < 33 and overlap > 0.48:
                    matches.append((error, reference["name"], (x+width//2, y+height//2)))
        if not matches:
            return None
        _, name, point = min(matches)
        return name, point
