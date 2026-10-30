"""Read-only checks; no simulated keys or desktop capture."""
import importlib
import platform
import struct
import sys


def main():
    print('系統：', platform.platform())
    print('Python：', sys.version.split()[0])
    print('位元：', struct.calcsize('P') * 8)
    print('路徑：', sys.executable)
    if sys.platform != 'win32':
        print('此專案目前只支援 Windows。')
        return 1
    if not (3, 9) <= sys.version_info[:2] <= (3, 12) or struct.calcsize('P') != 8:
        print('學校相容套件組需要 Python 3.9–3.12（64 位元）。')
        return 1
    if '--python-only' in sys.argv:
        return 0
    failed = False
    for name in ('mss', 'numpy', 'cv2'):
        try:
            module = importlib.import_module(name)
            print(name, getattr(module, '__version__', '已載入'))
        except (ImportError, OSError) as exc:
            print(name, '無法載入：', exc)
            failed = True
    print('此檢查不代表遊戲效能或學校電腦相容性已驗證。')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
