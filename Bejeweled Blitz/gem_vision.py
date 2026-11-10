"""Gem IDs and flame detection from sampled RGB pixels, without pip packages."""

from colorsys import rgb_to_hsv


def hsv(pixel):
    hue, sat, value = rgb_to_hsv(*pixel)
    return hue * 180, sat * 255, value


def color_id(pixel):
    hue, sat, value = hsv(pixel)
    if sat <= 80 and value >= 145:
        return 7
    if sat < 100 or value < 95:
        return None
    if hue <= 8 or hue >= 172:
        return 1
    for limit, code in ((21, 2), (38, 3), (82, 4), (125, 5), (171, 6)):
        if hue <= limit:
            return code
    return None


def read_board(frame):
    rows = []
    for row in range(8):
        cells = []
        for col in range(8):
            counts = [0] * 8
            for y in range(8):
                for x in range(8):
                    px = int((col + 0.24 + x * 0.52 / 7) * frame.width / 8)
                    py = int((row + 0.24 + y * 0.52 / 7) * frame.height / 8)
                    code = color_id(frame.pixel(px, py))
                    if code is not None:
                        counts[code] += 1
            ranked = sorted(range(1, 8), key=lambda code: counts[code], reverse=True)
            best, second = ranked[:2]
            gem = best if counts[best] >= 20 and counts[best] - counts[second] >= 11 else None
            if gem is None:
                # When edge effects split the vote, retry inside the gem body.
                # Require both a strong central vote and support in the wider sample.
                core = [0] * 8
                for y in range(5):
                    for x in range(5):
                        px = int((col + 0.36 + x * 0.28 / 4) * frame.width / 8)
                        py = int((row + 0.36 + y * 0.28 / 4) * frame.height / 8)
                        code = color_id(frame.pixel(px, py))
                        if code is not None:
                            core[code] += 1
                ranked = sorted(range(1, 8), key=lambda code: core[code], reverse=True)
                best, second = ranked[:2]
                if core[best] >= 15 and core[best] - core[second] >= 9 and counts[best] >= 12:
                    gem = best
            cells.append(gem)
        rows.append(tuple(cells))
    return tuple(rows)


def flame_strength(frame):
    # A flame adds yellow light above and outside the ordinary gem silhouette.
    lit = 0
    total = 0
    for y in (0.04, 0.08, 0.12, 0.16, 0.20):
        for x in (0.16, 0.23, 0.30, 0.37, 0.63, 0.70, 0.77, 0.84):
            hue, sat, value = hsv(frame.pixel(int(x * frame.width), int(y * frame.height)))
            lit += 14 <= hue <= 38 and sat >= 70 and value >= 190
            total += 1
    return lit / total


def read_flames(frame, board):
    flames = set()
    for row in range(8):
        for col in range(8):
            if board[row][col] is None:
                continue
            x, y = col * frame.width // 8, row * frame.height // 8
            right, bottom = (col + 1) * frame.width // 8, (row + 1) * frame.height // 8
            if flame_strength(frame.crop(x, y, right - x, bottom - y)) >= 0.12:
                flames.add((row, col))
    return flames


def countdown_visible(frame):
    count = 0
    for y in range(20):
        for x in range(20):
            red, green, blue = frame.pixel(
                int((1 / 3 + x / 60) * frame.width),
                int((3 / 8 + y / 80) * frame.height),
            )
            count += green >= 250 and red <= 4 and blue <= 4
    return count > 14


def cyan(pixel):
    red, green, blue = pixel
    if blue < 100 or green < 70 or red > max(green, blue) * 0.62:
        return False
    hue, sat, value = hsv(pixel)
    return 83 <= hue <= 107 and sat >= 100 and value >= 100


def timer_active(frame):
    hits = sum(cyan(frame.pixel(x * frame.width // 8, y * frame.height // 4))
               for x in range(8) for y in range(4))
    return hits > 8


def find_board(frame):
    # Search for the full cyan bar during the opening countdown.
    tested = set()
    for y in range(2, frame.height, 4):
        start = None
        for x in range(0, frame.width + 4, 4):
            lit = x < frame.width and cyan(frame.pixel(x, y))
            if lit and start is None:
                start = x
            if lit or start is None:
                continue
            left, right = start, min(x, frame.width)
            start = None
            if right - left < 150:
                continue
            while left > 0 and cyan(frame.pixel(left - 1, y)):
                left -= 1
            while right > left and not cyan(frame.pixel(right - 1, y)):
                right -= 1
            pending = [((left + right) // 2, y)]
            visited = set()
            top, bottom = y, y
            while pending:
                px, py = pending.pop()
                if (px, py) in visited or not (0 <= px < frame.width and 0 <= py < frame.height):
                    continue
                visited.add((px, py))
                if not cyan(frame.pixel(px, py)):
                    continue
                left, right = min(left, px), max(right, px + 1)
                top, bottom = min(top, py), max(bottom, py)
                pending.extend(((px-1, py), (px+1, py), (px, py-1), (px, py+1)))
            if not 14 <= (right - left) / (bottom - top + 1) <= 29:
                continue
            key = (left, top, right)
            if key in tested:
                continue
            tested.add(key)
            side = round((right - left) * 1.013)
            board_x = left - round(side * 0.008)
            board_y = top - round(side * 0.018) - side
            if min(board_x, board_y) < 0 or board_x + side > frame.width or board_y + side > frame.height:
                continue
            board = read_board(frame.crop(board_x, board_y, side, side))
            gems = [gem for row in board for gem in row if gem is not None]
            if len(gems) >= 60 and len(set(gems)) >= 5:
                return board_x, board_y, side, side
    return None
