"""Automatic Chrome Dino launcher. Python standard library only."""
import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit


class CDP:
    def __init__(self, url):
        u = urlsplit(url)
        if u.hostname not in ('127.0.0.1', 'localhost'):
            raise ValueError('只允許本機 Chrome 連線')
        self.sock = socket.create_connection((u.hostname, u.port), timeout=5)
        self.reader = self.sock.makefile('rb')
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(('GET '+u.path+' HTTP/1.1\r\nHost: '+u.netloc+
                          '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+key+
                          '\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        status = self.reader.readline()
        headers = {}
        while True:
            line = self.reader.readline()
            if line in (b'\r\n', b''):
                break
            k, v = line.decode().split(':', 1)
            headers[k.lower()] = v.strip()
        expected = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if b' 101 ' not in status or headers.get('sec-websocket-accept') != expected:
            self.close()
            raise RuntimeError('Chrome 偵錯連線失敗')
        self.serial = 0

    def close(self):
        self.reader.close()
        self.sock.close()

    def send(self, payload, opcode=1):
        mask = os.urandom(4)
        n = len(payload)
        header = bytes([0x80 | opcode])
        header += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126])+struct.pack('!H', n) if n < 65536 else bytes([0x80 | 127])+struct.pack('!Q', n))
        self.sock.sendall(header+mask+bytes(v ^ mask[i % 4] for i, v in enumerate(payload)))

    def read(self, n):
        data = self.reader.read(n)
        if len(data) != n:
            raise ConnectionError('Chrome 視窗已關閉')
        return data

    def receive(self):
        message = bytearray()
        while True:
            a, b = self.read(2)
            length = b & 127
            if length == 126:
                length = struct.unpack('!H', self.read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.read(8))[0]
            if length > 16*1024*1024:
                raise RuntimeError('回應過大')
            mask = self.read(4) if b & 128 else None
            payload = self.read(length)
            if mask:
                payload = bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
            opcode = a & 15
            if opcode == 8:
                raise ConnectionError('Chrome 視窗已關閉')
            if opcode == 9:
                self.send(payload, 10)
                continue
            if opcode == 10:
                continue
            message.extend(payload)
            if a & 128:
                return json.loads(message)

    def call(self, method, **params):
        self.serial += 1
        self.send(json.dumps(dict(id=self.serial, method=method, params=params)).encode())
        while True:
            result = self.receive()
            if result.get('id') == self.serial:
                if 'error' in result:
                    raise RuntimeError(str(result['error']))
                return result.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in result:
            raise RuntimeError(str(result['exceptionDetails']))
        return result.get('result', {}).get('value')


def find_chrome(explicit=None):
    candidates = [explicit, shutil.which('chrome')]
    for base in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
        candidates.append(str(Path(os.environ.get(base, ''))/'Google/Chrome/Application/chrome.exe'))
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise FileNotFoundError('找不到 Chrome。可用 --chrome 指定 chrome.exe 路徑。')


INIT = r'''(async () => {
 let R = typeof Runner !== 'undefined' ? Runner : globalThis.Runner;
 if (!R) R = (await import('/dino_game/offline.js')).Runner;
 const r = R.getInstance ? R.getInstance() : R.instance_;
 if (!r || !r.tRex || !r.horizon || typeof r.tRex.startJump !== 'function')
   throw new Error('此 Chrome 的遊戲介面不相容，或學校已停用小恐龍');
 globalThis.__pythonDino = r;
 return true;
})()'''
STATE = '''(() => { const r=globalThis.__pythonDino, t=r.tRex;
 return {crashed:r.crashed, playing:r.playing, jumping:t.jumping, ducking:t.ducking,
 speed:r.currentSpeed, x:t.xPos, width:t.config.width || t.config.WIDTH || 44,
 y:t.yPos, ground:t.groundYPos, velocity:t.jumpVelocity,
 distance:r.distanceRan, obstacles:r.horizon.obstacles.map(o=>({x:o.xPos,width:o.width,y:o.yPos,type:o.typeConfig.type,
 levels:Array.isArray(o.typeConfig.yPos)?o.typeConfig.yPos:null}))}; })()'''


def obstacle_action(obstacle):
    if obstacle['type'].lower() != 'pterodactyl':
        return 'jump'
    levels = sorted(set(obstacle.get('levels') or [50, 75, 100]))
    index = min(range(len(levels)), key=lambda i: abs(levels[i]-obstacle['y']))
    if index == 0:
        return 'ignore'
    if len(levels) >= 3 and index == 1:
        return 'duck'
    return 'jump'


def decide_action(state, lead):
    if not state['playing'] or state['jumping']:
        return 'wait'
    obstacles = sorted((o for o in state['obstacles']
                        if o['x']+o['width'] > state['x']-8
                        and obstacle_action(o) != 'ignore'), key=lambda o: o['x'])
    if not obstacles:
        return 'run'
    obstacle = obstacles[0]
    action = obstacle_action(obstacle)
    distance = obstacle['x']-state['x']-state['width']
    seconds = max(lead, .2) if action == 'duck' else lead
    return action if distance <= state['speed']*60*seconds else 'run'


def main():
    parser = argparse.ArgumentParser(description='自動開啟 Chrome 並操作小恐龍，不需要安裝套件')
    parser.add_argument('--chrome', help='Chrome 執行檔路徑')
    parser.add_argument('--lead', type=float, default=.12, help='跳躍提前秒數（預設 0.12）')
    parser.add_argument('--seconds', type=float, default=0, help='測試時間，0 表示持續執行')
    parser.add_argument('--debug', action='store_true', help='記錄跳躍與碰撞狀態')
    args = parser.parse_args()
    if not .05 <= args.lead <= .5 or args.seconds < 0:
        parser.error('lead 需介於 0.05–0.5，seconds 不可為負數')
    chrome = find_chrome(args.chrome)
    profile = Path(tempfile.mkdtemp(prefix='python-dino-'))
    connection = None
    process = None
    try:
        print('開啟獨立 Chrome 小恐龍視窗；F8 或 Ctrl+C 停止。', flush=True)
        process = subprocess.Popen([chrome, '--user-data-dir='+str(profile),
            '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
            '--no-first-run', '--no-default-browser-check', '--new-window',
            '--start-fullscreen', 'chrome://dino/'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        last_error = None
        deadline = time.monotonic()+25
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000:
                raise KeyboardInterrupt
            try:
                port = int((profile/'DevToolsActivePort').read_text().splitlines()[0])
                with opener.open('http://127.0.0.1:%d/json/list' % port, timeout=1) as response:
                    pages = json.load(response)
                page = next(p for p in pages if p.get('type') == 'page')
                connection = CDP(page['webSocketDebuggerUrl'])
                if not page.get('url', '').startswith('chrome://dino'):
                    connection.call('Page.navigate', url='chrome://dino/')
                    time.sleep(.5)
                connection.evaluate(INIT)
                break
            except (OSError, ValueError, StopIteration, RuntimeError) as error:
                last_error = error
                if connection:
                    connection.close()
                    connection = None
                time.sleep(.3)
        if not connection:
            raise RuntimeError('25 秒內無法連接小恐龍；可能是 Chrome 版本或學校政策不允許遠端偵錯。原因：'+repr(last_error))
        connection.call('Page.bringToFront')
        connection.call('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32)
        connection.call('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
        print('已自動開始。不需選座標；由 Python 判斷跳躍。', flush=True)
        started = last_report = time.monotonic()
        dead_since = None
        while not args.seconds or time.monotonic()-started < args.seconds:
            if ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000:
                break
            state = connection.evaluate(STATE)
            now = time.monotonic()
            if state['crashed']:
                if dead_since is None:
                    print('碰撞：'+(json.dumps(state) if args.debug else
                          '距離 {:.0f}，稍後自動重開'.format(state['distance'])), flush=True)
                dead_since = dead_since or now
                if now-dead_since > 1.5:
                    connection.evaluate('globalThis.__pythonDino.restart()')
                    dead_since = None
            else:
                dead_since = None
                action = decide_action(state, args.lead)
                if action == 'duck' and not state['ducking']:
                    connection.evaluate('globalThis.__pythonDino.tRex.setDuck(true)')
                    if args.debug:
                        print('蹲下：'+json.dumps(state), flush=True)
                elif action in ('jump', 'run'):
                    if state['ducking']:
                        connection.evaluate('globalThis.__pythonDino.tRex.setDuck(false)')
                    if action == 'jump':
                        if args.debug:
                            print('跳躍：'+json.dumps(state), flush=True)
                        connection.evaluate('globalThis.__pythonDino.tRex.startJump(globalThis.__pythonDino.currentSpeed)')
            if now-last_report >= 5:
                print('速度 {:.1f}；距離 {:.0f}；{}'.format(state['speed'], state['distance'], '碰撞後重開' if state['crashed'] else '運行中'), flush=True)
                last_report = now
            time.sleep(.015)
    finally:
        if connection:
            try:
                connection.call('Browser.close')
            except (OSError, RuntimeError):
                pass
            connection.close()
        if process:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        # Only remove the uniquely created temporary profile, never user profiles.
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('已停止。')
    except (OSError, RuntimeError, ValueError) as error:
        print('無法執行：', error)
        raise SystemExit(1)
