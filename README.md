# 小恐龍全自動版

雙擊 start.cmd，或在 IDLE 開啟 auto_dino.py 後按 F5。程式自動尋找 Chrome、以全螢幕開啟獨立遊戲視窗、開始遊戲與跳躍；碰撞後自動重開。F8 或 Ctrl+C 停止，並關閉本程式的 Chrome 視窗。

## 帶到老師電腦

只需 auto_dino.py、start.cmd 與這份 README.md。電腦需有 Windows、Python 3 與 Google Chrome；不需要 pip 套件、ChromeDriver 或座標校準。從 GitHub 下載 ZIP 後先解壓縮再啟動。不要複製 .venv。本機使用 Python 3.12 驗證，尚未在老師電腦測試。

若找不到 Chrome：python auto_dino.py --chrome "C:\Program Files\Google\Chrome\Application\chrome.exe"

## 實作方式與限制

Python 透過僅在本機監聽的 Chrome DevTools Protocol，讀取遊戲障礙物與速度，判斷時機後呼叫遊戲跳躍動作。這是讀取遊戲內部資料的版本，不是畫面像素辨識。沒有修改碰撞判定、速度或分數；仍可能撞到障礙物。若老師要求只能辨識畫面，請使用保留的 dino_bot.py 舊版。

啟動時建立獨立暫存 Chrome 設定資料夾，不使用個人登入資料；結束時清理自己的暫存資料。學校政策若停用偵錯或小恐龍，程式會停止報錯。Chrome 未來改變內部介面時可能需修正。

跳太晚可試 python auto_dino.py --lead 0.14；預設 0.12。測試指定時間：python auto_dino.py --seconds 20。請保持遊戲視窗可見，避免背景節流。

## 驗證

本機已成功自動啟動遊戲並讀到距離增加。未驗證老師電腦相容性或高分表現，不保證排名。

## 舊版

dino_bot.py 保留純 Python 畫面區塊偵測，需 F9 記錄左上、右下，再按 F9 開始。其他 vision、requirements、test_coordinate 檔案屬於舊版，自動版不需要。

## 來源

Chromium 遊戲原始碼：https://raw.githubusercontent.com/chromium/chromium/main/components/neterror/resources/dino_game/offline.ts

全螢幕使用 Chrome 的 --start-fullscreen 啟動參數。可按 F11 切換全螢幕，F8 停止程式。

2026-11-09 修正：實測發現原 0.22 秒提前量讓恐龍下降時仍碰到寬仙人掌，預設改為 0.12 秒。--debug 可輸出跳躍和碰撞當下的障礙物、速度與恐龍高度。
修正後本機全螢幕實測 60 秒：未出現碰撞，經過寬仙人掌與三種高度飛鳥，遊戲內部速度達約 13。這是單次測試結果，不保證其他電腦或長時間不失敗。

飛鳥分級：高飛鳥不跳、中飛鳥蹲下，直到整隻鳥通過才站起來；低飛鳥與仙人掌跳躍。分類使用遊戲提供的鳥高度陣列，不受螢幕解析度影響。python -S -m unittest -v test_auto 可測試五項判斷情境。

教室啟動修正：連接後再次設定並確認全螢幕；失敗則嘗試最大化。啟用頁面焦點、自動點擊畫布與送出空白鍵，確認距離開始增加才進入控制迴圈。已在本機實測自動全螢幕啟動並運行 15 秒，教室電腦仍待驗證。更新時需將新版 auto_dino.py 複製到教室電腦，舊副本不會自行更新。

也可單獨下載 [小恐龍自動遊玩.ipynb](小恐龍自動遊玩.ipynb)，在 Windows 本機 VS Code／Jupyter 選擇本機 Python 核心後按全部執行。筆記本已內嵌程式；執行環境本身需要 Jupyter／ipykernel。F8 或中斷核心停止。維護時執行 build_dino_notebook.py 可從 auto_dino.py 重新產生筆記本。

