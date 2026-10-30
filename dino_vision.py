"""Legacy optional OpenCV bot; default bot uses only the standard library."""
import argparse
import ctypes
import json
import time
from pathlib import Path

import cv2
import mss
import numpy as np

CONFIG = Path(__file__).with_name('calibration.json')
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = ctypes.c_void_p
SPACE, DOWN, F8 = 0x20, 0x28, 0x77


def key(code, pressed):
    user32.keybd_event(code, 0, 0 if pressed else 2, 0)


def tap(code):
    key(code, True)
    time.sleep(0.035)
    key(code, False)


def stopped():
    return bool(user32.GetAsyncKeyState(F8) & 0x8000)


def countdown(seconds):
    for left in range(seconds, 0, -1):
        print(f'{left} 秒：請切回 Chrome（F8 停止）', flush=True)
        for _ in range(10):
            if stopped():
                raise KeyboardInterrupt
            time.sleep(0.1)


def select(title, frame):
    box = cv2.selectROI(title, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    if box[2] < 10 or box[3] < 10:
        raise ValueError('未選取有效區域，已取消。')
    return [int(v) for v in box]


def calibrate(sct):
    print('先開啟 chrome://dino，保持恐龍站立；五秒後擷取畫面。')
    countdown(5)
    monitor = sct.monitors[1]
    frame = np.array(sct.grab(monitor))[:, :, :3].copy()
    x, y, w, h = select('1. Select game canvas including ground; ENTER confirms', frame)
    dx, dy, dw, dh = select('2. Select standing dinosaur tightly; ENTER confirms', frame[y:y+h, x:x+w])
    if dx + dw >= w or dy + dh >= h:
        raise ValueError('恐龍必須位於遊戲區域內，並保留地面下方空間。')
    config = dict(left=monitor['left']+x, top=monitor['top']+y,
                  width=w, height=h, dino=[dx, dy, dw, dh])
    CONFIG.write_text(json.dumps(config, indent=2), encoding='utf-8')
    return config


def foreground_mask(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Background occupies most of the canvas; works with day/night inversion.
    background = float(np.median(gray))
    return (np.abs(gray.astype(np.float32)-background) > 65).astype(np.uint8)


def obstacles(mask, dino):
    dx, dy, dw, dh = dino
    ground = dy + dh
    scale = dh / 47.0
    start = min(mask.shape[1]-1, dx + dw + int(4*scale))
    top = max(0, ground-int(85*scale))
    bottom = max(top+1, ground-int(5*scale))
    crop = mask[top:bottom, start:]
    # Group wings/body and neighbouring cactus pixels without merging ground.
    joined = cv2.morphologyEx(crop, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    result = []
    for x, y, w, h, area in stats[1:count]:
        if area < 12*scale*scale or h < 6*scale or w < 3*scale:
            continue
        result.append((start+int(x), top+int(y), int(w), int(h)))
    return sorted(result)


def run(sct, config, debug, lead):
    region = {k: config[k] for k in ('left', 'top', 'width', 'height')}
    dx, dy, dw, dh = config['dino']
    scale = dh/47.0
    print('倒數後開始。請點擊 Chrome 遊戲區域；F8 或 Ctrl+C 停止。')
    countdown(5)
    target = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(ctypes.c_void_p(target), title, 512)
    if 'chrome' not in title.value.lower():
        raise ValueError('前景視窗標題未包含 Chrome，已取消。請切回 Chrome 再執行。')
    speed = 360*scale
    previous = []
    last_time = time.perf_counter()
    last_jump = 0.0
    jump_release = 0.0
    ducking = False
    duck_until = 0.0
    frozen_since = None
    last_scene = None
    restart_after = last_time + 2
    tap(SPACE)
    try:
        while not stopped():
            now = time.perf_counter()
            if user32.GetForegroundWindow() != target:
                print('前景視窗已改變，停止操作。')
                break
            frame = np.array(sct.grab(region))[:, :, :3].copy()
            mask = foreground_mask(frame)
            boxes = obstacles(mask, config['dino'])
            dt = now-last_time
            estimates = []
            if 0.003 < dt < 0.15:
                for x, y, w, h in boxes:
                    matches = [(px-x)/dt for px, py, pw, ph in previous
                               if abs(py-y) < 12*scale and abs(pw-w) < 12*scale
                               and 1*scale < px-x < 35*scale]
                    if matches:
                        estimates.append(min(matches, key=lambda v: abs(v-speed)))
            if estimates:
                measured = float(np.median(estimates))
                if 100*scale < measured < 1800*scale:
                    speed = 0.8*speed + 0.2*measured
            previous, last_time = boxes, now
            # Detect frozen obstacle/ground pixels, excluding score and game-over text.
            scene = mask[max(0, dy+dh-int(12*scale)):dy+dh+int(8*scale), dx+dw:]
            if last_scene is not None and scene.shape == last_scene.shape:
                change = np.mean(scene != last_scene) if scene.size else 1
                if change < 0.001:
                    frozen_since = now if frozen_since is None else frozen_since
                else:
                    frozen_since = None
            last_scene = scene.copy()
            if frozen_since is not None and now-frozen_since > 1.4 and now > restart_after:
                key(DOWN, False)
                key(SPACE, False)
                ducking = False
                duck_until = 0.0
                jump_release = 0.0
                tap(SPACE)
                print('畫面停止移動，嘗試重新開始。', flush=True)
                restart_after = now+3
                frozen_since = None
                previous = []
                speed = 360*scale
            if jump_release and now >= jump_release:
                key(SPACE, False)
                jump_release = 0
            should_duck = now < duck_until
            if boxes:
                x, y, w, h = boxes[0]
                distance = x-(dx+dw)
                bottom = y+h
                # High birds clear the standing dinosaur; middle birds need ducking.
                if bottom > dy+5*scale:
                    middle_bird = bottom < dy+dh-18*scale
                    if middle_bird:
                        if distance < max(100*scale, speed*0.32):
                            # Keep ducking until the bird's trailing edge clears
                            # the dinosaur, even after it leaves the search crop.
                            duck_until = now + (x+w-dx+10*scale)/max(speed, 1)
                            should_duck = True
                    elif distance < max(65*scale, speed*lead) and now-last_jump > 0.55:
                        key(DOWN, False)
                        ducking = False
                        duck_until = 0.0
                        should_duck = False
                        key(SPACE, True)
                        jump_release = now + min(0.24, max(0.12, w/max(speed, 1)+0.08))
                        last_jump = now
            if should_duck != ducking:
                key(DOWN, should_duck)
                ducking = should_duck
            if debug:
                for x, y, w, h in boxes:
                    cv2.rectangle(frame, (x,y), (x+w,y+h), (0,0,255), 1)
                cv2.putText(frame, f'{speed:.0f} px/s | F8 STOP', (5,20), 0, .5, (0,0,255), 1)
                cv2.imshow('Dino debug (keep Chrome focused)', frame)
                cv2.waitKey(1)
            time.sleep(0.005)
    finally:
        key(SPACE, False)
        key(DOWN, False)
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='Chrome 小恐龍自動跳躍（Windows）')
    parser.add_argument('--calibrate', action='store_true', help='重新框選遊戲及恐龍')
    parser.add_argument('--debug', action='store_true', help='顯示辨識框（勿點擊預覽視窗）')
    parser.add_argument('--lead', type=float, default=0.24, help='跳躍提前秒數，預設 0.24')
    args = parser.parse_args()
    if not 0.05 <= args.lead <= 0.6:
        parser.error('--lead 必須介於 0.05 與 0.6 秒之間')
    try:
        user32.SetProcessDPIAware()
        with mss.mss() as sct:
            config = calibrate(sct) if args.calibrate or not CONFIG.exists() else json.loads(CONFIG.read_text(encoding='utf-8'))
            run(sct, config, args.debug, args.lead)
    except KeyboardInterrupt:
        print('已停止。')
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'無法執行：{exc}')


if __name__ == '__main__':
    main()
