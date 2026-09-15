# -*- coding: utf-8 -*-
"""主窗口截图：用于人工确认 Fluent 视觉效果。输出 tests/shot_main.png"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import ctypes
import ctypes.wintypes as wt

import pc_cleaner as pc
from PIL import ImageGrab

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot_main.png")

pc.set_dpi_aware()
app = pc.App()
app.attributes("-topmost", True)
app.update()
app.lift()
app.focus_force()
for _ in range(25):
    app.update()

# 悬停到「清理微信缓存」磁贴，让说明区显示真实内容
if "wechat" in app._tasks:
    app._tasks["wechat"]._btn.event_generate("<Enter>", x=5, y=5)
    for _ in range(10):
        app.update()

hwnd = ctypes.windll.user32.GetParent(app.winfo_id()) or app.winfo_id()
r = wt.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
left, top, right, bottom = r.left, r.top, r.right, r.bottom
print(f"窗口矩形: {left},{top} -> {right},{bottom}  ({right-left}x{bottom-top})")

for _ in range(6):
    app.update()
    time.sleep(0.05)

img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
img.save(OUT)
print(f"已保存: {OUT}  尺寸={img.size}")

app.destroy()
