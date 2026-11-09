"""Windows screen/image pixels using only Python's standard library."""

import ctypes as ct
from ctypes import wintypes as wt


class BitmapInfo(ct.Structure):
    _fields_ = [
        ("size", wt.DWORD), ("width", wt.LONG), ("height", wt.LONG),
        ("planes", wt.WORD), ("bits", wt.WORD), ("compression", wt.DWORD),
        ("image_size", wt.DWORD), ("xppm", wt.LONG), ("yppm", wt.LONG),
        ("used", wt.DWORD), ("important", wt.DWORD),
    ]


class Frame:
    def __init__(self, data, width, height, stride=None, offset=0):
        self.data = data
        self.width, self.height = width, height
        self.stride = stride or width * 4
        self.offset = offset

    def pixel(self, x, y):
        index = self.offset + y * self.stride + x * 4
        blue, green, red = self.data[index:index + 3]
        return red, green, blue

    def crop(self, x, y, width, height):
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > self.width or y + height > self.height:
            raise ValueError("擷取範圍超出圖片。")
        return Frame(self.data, width, height, self.stride, self.offset + y * self.stride + x * 4)


class Capture:
    def __init__(self):
        self.user = ct.WinDLL("user32", use_last_error=True)
        self.gdi = ct.WinDLL("gdi32", use_last_error=True)
        self.user.GetDC.argtypes = [wt.HWND]
        self.user.GetDC.restype = wt.HDC
        self.user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
        self.gdi.CreateCompatibleDC.argtypes = [wt.HDC]
        self.gdi.CreateCompatibleDC.restype = wt.HDC
        self.gdi.CreateDIBSection.argtypes = [
            wt.HDC, ct.POINTER(BitmapInfo), wt.UINT, ct.POINTER(ct.c_void_p), wt.HANDLE, wt.DWORD,
        ]
        self.gdi.CreateDIBSection.restype = wt.HBITMAP
        self.gdi.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
        self.gdi.SelectObject.restype = wt.HANDLE
        self.gdi.BitBlt.argtypes = [
            wt.HDC, ct.c_int, ct.c_int, ct.c_int, ct.c_int,
            wt.HDC, ct.c_int, ct.c_int, wt.DWORD,
        ]
        self.gdi.DeleteObject.argtypes = [wt.HANDLE]
        self.gdi.DeleteDC.argtypes = [wt.HDC]
        self.screen = self.memory = None
        self.monitors = [dict(zip(
            ("left", "top", "width", "height"),
            (self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79)),
        ))]

    def __enter__(self):
        self.screen = self.user.GetDC(None)
        self.memory = self.gdi.CreateCompatibleDC(self.screen) if self.screen else None
        if not self.memory:
            self.__exit__(None, None, None)
            raise OSError("無法建立 Windows 螢幕擷取，請在已登入的 Windows 桌面執行。")
        return self

    def __exit__(self, *args):
        if self.memory:
            self.gdi.DeleteDC(self.memory)
        if self.screen:
            self.user.ReleaseDC(None, self.screen)
        self.screen = self.memory = None

    def grab(self, region):
        width, height = region["width"], region["height"]
        if width <= 0 or height <= 0:
            raise ValueError("擷取大小無效。")
        info = BitmapInfo()
        info.size, info.width, info.height = ct.sizeof(info), width, -height
        info.planes, info.bits = 1, 32
        pointer = ct.c_void_p()
        bitmap = self.gdi.CreateDIBSection(self.screen, ct.byref(info), 0, ct.byref(pointer), None, 0)
        if not bitmap:
            raise ct.WinError(ct.get_last_error())
        old = self.gdi.SelectObject(self.memory, bitmap)
        try:
            if not old:
                raise OSError("無法選取擷取點陣圖。")
            if not self.gdi.BitBlt(
                self.memory, 0, 0, width, height, self.screen,
                region["left"], region["top"], 0x40CC0020,
            ):
                raise ct.WinError(ct.get_last_error())
            self.gdi.GdiFlush()
            return Frame(ct.string_at(pointer, width * height * 4), width, height)
        finally:
            if old:
                self.gdi.SelectObject(self.memory, old)
            self.gdi.DeleteObject(bitmap)


def read_image(path):
    """Decode PNG/JPEG with the GDI+ library included in Windows."""
    class Startup(ct.Structure):
        _fields_ = [("version", wt.UINT), ("callback", ct.c_void_p),
                    ("thread", wt.BOOL), ("codecs", wt.BOOL)]

    class Data(ct.Structure):
        _fields_ = [("width", wt.UINT), ("height", wt.UINT), ("stride", ct.c_int),
                    ("format", ct.c_int), ("scan", ct.c_void_p), ("reserved", ct.c_size_t)]

    class Rect(ct.Structure):
        _fields_ = [(name, ct.c_int) for name in ("x", "y", "width", "height")]

    dll = ct.WinDLL("gdiplus")
    dll.GdiplusStartup.argtypes = [ct.POINTER(ct.c_size_t), ct.POINTER(Startup), ct.c_void_p]
    dll.GdiplusShutdown.argtypes = [ct.c_size_t]
    dll.GdipCreateBitmapFromFile.argtypes = [wt.LPCWSTR, ct.POINTER(ct.c_void_p)]
    dll.GdipGetImageWidth.argtypes = [ct.c_void_p, ct.POINTER(wt.UINT)]
    dll.GdipGetImageHeight.argtypes = [ct.c_void_p, ct.POINTER(wt.UINT)]
    dll.GdipBitmapLockBits.argtypes = [ct.c_void_p, ct.POINTER(Rect), wt.UINT, ct.c_int, ct.POINTER(Data)]
    dll.GdipBitmapUnlockBits.argtypes = [ct.c_void_p, ct.POINTER(Data)]
    dll.GdipDisposeImage.argtypes = [ct.c_void_p]
    token = ct.c_size_t()
    if dll.GdiplusStartup(ct.byref(token), ct.byref(Startup(1, None, False, False)), None):
        raise OSError("無法啟動 Windows 圖片解碼。")
    bitmap = ct.c_void_p()
    try:
        if dll.GdipCreateBitmapFromFile(str(path), ct.byref(bitmap)):
            raise ValueError("無法讀取圖片，請確認路徑和檔案格式。")
        width, height = wt.UINT(), wt.UINT()
        if dll.GdipGetImageWidth(bitmap, ct.byref(width)) or dll.GdipGetImageHeight(bitmap, ct.byref(height)):
            raise ValueError("無法取得圖片大小。")
        data = Data()
        rect = Rect(0, 0, width.value, height.value)
        if dll.GdipBitmapLockBits(bitmap, ct.byref(rect), 1, 0x26200A, ct.byref(data)):
            raise ValueError("無法讀取圖片像素。")
        try:
            pixels = b"".join(ct.string_at(data.scan + y * data.stride, width.value * 4) for y in range(height.value))
            return Frame(pixels, width.value, height.value)
        finally:
            dll.GdipBitmapUnlockBits(bitmap, ct.byref(data))
    finally:
        if bitmap:
            dll.GdipDisposeImage(bitmap)
        dll.GdiplusShutdown(token)
