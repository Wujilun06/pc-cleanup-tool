# -*- coding: utf-8 -*-
"""Dism++ 引导窗尺寸测试：直接弹出一个引导窗截图，确认 4 步骤完整可见。"""
import os, sys, ctypes, ctypes.wintypes as wt
import time
import subprocess
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pc_cleaner as pc
from PIL import ImageGrab

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot_dismpp_guide.png")

pc.set_dpi_aware()
pc.set_theme("light")  # 浅色下截图更易看清尺寸

app = pc.App()
app.attributes("-topmost", True)
app.update(); app.lift(); app.focus_force()
for _ in range(15): app.update()

# 构造一个假的 Popen（DismPPGuide 接受任意 Popen，只看 proc.poll()）
# 用 notepad 占位，确保进程持续运行
proc = subprocess.Popen(["notepad.exe"])

# 显式调用 DismPPGuide（不走完整流程）
guide = pc.DismPPGuide(app, proc)
for _ in range(15): app.update()

hwnd = ctypes.windll.user32.GetParent(guide.winfo_id()) or guide.winfo_id()
r = wt.RECT()
ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
print(f"引导窗矩形: {r.left},{r.top} -> {r.right},{r.bottom}  ({r.right-r.left}x{r.bottom-r.top})")

for _ in range(8): app.update(); time.sleep(0.05)
ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).save(OUT)
print(f"已保存: {OUT}")

guide._on_done()  # 关闭引导窗
proc.terminate()
app.destroy()