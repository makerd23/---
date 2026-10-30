# 小恐龍自動跳躍：純 Python 區塊偵測版

預設 dino_bot.py 只用 Python 內建模組與 Windows API。不需要 pip、Chrome 外掛、OpenCV、NumPy 或 MSS。使用矩形區塊偵測，區塊內讀到障礙物就跳躍，不會蹲下。

## 開始

1. 在 Chrome 開啟 chrome://dino，先不要開始，使用預設縮放。
2. 雙擊 start.cmd，或在終端機執行 python dino_bot.py。也可用 IDLE 開啟程式後按 F5。
3. 切回 Chrome，將滑鼠放在恐龍前方區塊的左上角，按 F9；再移到右下角，按 F9。建議區塊寬 30–50、高 50–55 像素，右緣距恐龍右側約 100 像素，下緣離地 5–10 像素。不要包含恐龍、地面、文字或雲。
4. 移開滑鼠，再按 F9 開始。現在總共需要按三次 F9。
5. F8 或終端機 Ctrl+C 停止。切換前景視窗也會停止。筆電可能需要 Fn 搭配功能鍵。

不會出現框選視窗。每次啟動重新記錄座標；移動或縮放 Chrome 後也要重新執行。

## 加速追蹤與調整

每輪用 BitBlt 擷取一小塊畫面，再在記憶體讀取像素。從區塊右緣再往右掃描 200 像素以估速，以障礙物左邊緣位移估速。速度增加時自動增加提前距離，最多 160 像素。只讀取螢幕，不讀遊戲內部資料，也不修改碰撞或分數。

- 顯示估速與提前距離：python dino_bot.py --debug。
- 從一開始就跳太晚／太早：重新執行，將座標往右／左調 10–20 像素。
- 加速後跳太晚：可試 python dino_bot.py --lead 0.28；預設 0.22。
- 調整空白鍵按住時間：python dino_bot.py --hold 0.22；預設 0.18 秒。

區塊每隔 4 像素取樣一欄、每隔 3 像素取樣一列，涵蓋中間高度而非只讀兩條線；極細或剛好落在取樣間隙的物體仍可能漏掉。所有障礙物均用跳躍處理，尚未驗證各種飛鳥高度的通過率。像素估速可能受背景、縮放與畫面延遲影響，不會自動重開，不保證分數。以上參數仍待實際遊戲調校。

## 驗證

python -S -m unittest -v test_coordinate

測試包含加速提前、丟失配對、邊界裁切、日夜像素、移動障礙物與跳躍冷卻。已通過離線測試與語法檢查，尚未驗證此版遊戲成績或學校電腦效能。

## GitHub 與學校電腦

目前尚未上傳 GitHub。預設版本只需 dino_bot.py、start.cmd、README.md，可附 test_coordinate.py。從 GitHub 選 Code → Download ZIP，解壓縮後執行；需要 Windows 與可用的 Python 3。本機檢查使用 Python 3.12，其他版本未逐一實測。

不要上傳或複製 .venv、__pycache__、calibration.json。setup.cmd 只顯示操作提示，不會安裝套件。舊影像版保留在 dino_vision.py；requirements.txt、requirements-school.txt、check_environment.py、test_vision.py 都是舊版用的檔案，區塊版不需要。

## API 來源

- 像素讀取：https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getpixel
- 小區域擷取：https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-bitblt
- 滑鼠座標：https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getcursorpos
