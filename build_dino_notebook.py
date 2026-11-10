"""Build a standalone notebook from the current standard-library Dino bot."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / 'auto_dino.py').read_text(encoding='utf-8-sig')
definitions, marker, _ = source.rpartition("\nif __name__ == '__main__':")
if not marker:
    raise ValueError('找不到主程式入口，停止產生筆記本。')


def cell(kind, identity, text):
    item = dict(cell_type=kind, id=identity, metadata={},
                source=text.splitlines(keepends=True))
    if kind == 'code':
        item.update(execution_count=None, outputs=[])
    return item


notebook = dict(
    nbformat=4, nbformat_minor=5,
    metadata={
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'file_extension': '.py',
                          'mimetype': 'text/x-python', 'pygments_lexer': 'ipython3'},
    },
    cells=[
        cell('markdown', 'instructions', '''# 小恐龍全自動遊玩

這份筆記本已內嵌完整程式，可單獨下載，不需要旁邊有 auto_dino.py。

1. 在 **Windows 電腦本機**的 VS Code／Jupyter 開啟，選擇本機 Python 3 核心。
2. 按「全部執行」：自動開啟 Chrome、最大化一般視窗、啟用頁面並開始遊戲。此版不使用 F11 全螢幕。
3. 高鳥直接通過、中鳥蹲下、低鳥與仙人掌跳躍，碰撞後重開。
4. 按 **F8** 或中斷核心停止；程式會關閉自己開啟的 Chrome。

程式本身只用 Python 標準函式庫，不需 pip 套件或 ChromeDriver。**開啟 ipynb 仍需要現成的 Jupyter／ipykernel 執行環境**，老師電腦若只有一般 Python，請改用 start.cmd／auto_dino.py。Google Colab 或遠端 Linux 核心不能控制這台 Windows 電腦。

這個版本使用 Chrome 偵錯介面讀取遊戲資料，不是畫面像素辨識。學校若封鎖偵錯功能或小恐龍，可能無法執行；不保證分數。更新檔案後，先停止舊執行，再重新「全部執行」。
'''),
        cell('code', 'program', definitions+'\n'),
        cell('markdown', 'run-notes', '''## 啟動

下方參數預設為持續遊玩。測試 30 秒可改成 `["--seconds", "30"]`；調整起跳可用 `["--lead", "0.12"]`。

如果最大化仍有問題，把下方參數改成 `["--windowed"]`，就會以一般大小視窗啟動。

執行中的儲存格會一直忙碌，這是正常現象。使用 F8 或中斷核心結束，請勿同時啟動多份。
'''),
        cell('code', 'run', '''執行參數 = []
try:
    main(執行參數)
except KeyboardInterrupt:
    print('已停止。')
except (OSError, RuntimeError, ValueError) as error:
    print('無法執行：', error)
'''),
    ],
)
path = ROOT / '小恐龍自動遊玩.ipynb'
path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
print(path)
