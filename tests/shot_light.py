# -*- coding: utf-8 -*-
"""浅色主题 + 设置弹窗截图：用于人工确认主题切换与设置弹窗布局。"""
import os, sys, ctypes, ctypes.wintypes as wt
import time
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pc_cleaner as pc
from PIL import ImageGrab

OUT_MAIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot_light.png")
OUT_DLG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot_settings.png")

pc.set_dpi_aware()

# 浅色
pc.set_theme("light")

app = pc.App()
app.attributes("-topmost", True)
app.update(); app.lift(); app.focus_force()
for _ in range(25): app.update()

# 悬停到「清理微信缓存」
if "wechat" in app._tasks:
    app._tasks["wechat"]._btn.event_generate("<Enter>", x=5, y=5)
    for _ in range(8): app.update()

hwnd = ctypes.windll.user32.GetParent(app.winfo_id()) or app.winfo_id()
r = wt.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
left, top, right, bottom = r.left, r.top, r.right, r.bottom
for _ in range(6): app.update(); time.sleep(0.05)
ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(OUT_MAIN)
print(f"已保存: {OUT_MAIN}")

# 打开设置弹窗截图
app.open_settings()
for _ in range(20): app.update()
top_levels = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]
if top_levels:
    w = top_levels[-1]
    hwnd2 = ctypes.windll.user32.GetParent(w.winfo_id()) or w.winfo_id()
    r2 = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd2, ctypes.byref(r2))
    for _ in range(6): app.update(); time.sleep(0.05)
    ImageGrab.grab(bbox=(r2.left, r2.top, r2.right, r2.bottom), all_screens=True).save(OUT_DLG)
    print(f"已保存: {OUT_DLG}")

# 恢复深色
pc.set_theme("dark")
app.destroy()
