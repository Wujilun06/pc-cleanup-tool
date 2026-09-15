# -*- coding: utf-8 -*-
"""
弹窗组件冒烟测试：
  - ConfirmDialog / ErrorDialog / DismPPGuide / open_settings 全部能正常构建
  - ErrorDialog 底栏无重复
  - DismPPGuide 无底部按钮，且手动关闭会置位 _dismpp_guide_dismissed
"""
import os, sys
import subprocess
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pc_cleaner as pc

# 关键：ConfirmDialog/ErrorDialog 在 __init__ 末尾会 wait_window() 阻塞主循环。
# 测试中改为不阻塞（不真正等待）。
_orig_wait_window = tk.Misc.wait_window
tk.Misc.wait_window = lambda self, w=None: None

FAILS, N = [], 0


def check(cond, name, detail=""):
    global N
    N += 1
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAILS.append(f"{name}  {detail}")


pc.set_dpi_aware()
app = pc.App()
for _ in range(20):
    app.update()

def collect_fluent_buttons(parent):
    out = []
    for ch in parent.winfo_children():
        if isinstance(ch, pc.FluentButton):
            out.append(ch)
        out.extend(collect_fluent_buttons(ch))
    return out


print("--- ConfirmDialog ---")
dlg = pc.ConfirmDialog(app, "确认测试", "这是测试详情内容。\n第二行\n第三行")
for _ in range(8):
    app.update()
check(dlg.winfo_width() >= 580 and dlg.winfo_height() >= 460, "ConfirmDialog 尺寸合规",
      f"({dlg.winfo_width()}x{dlg.winfo_height()})")
btns = collect_fluent_buttons(dlg)
check(len(btns) == 2, f"ConfirmDialog 有 2 个 FluentButton（取消/确认）", f"({len(btns)})")
dlg.destroy()

print("\n--- ErrorDialog ---")
dlg = pc.ErrorDialog(app, "失败测试", "ValueError: 测试", "日志行1\n日志行2")
for _ in range(8):
    app.update()
cards = [w for w in dlg.winfo_children() if isinstance(w, pc.FluentCard)]
check(len(cards) == 1, "ErrorDialog 仅 1 个 FluentCard 容器（无重复底栏）", f"({len(cards)})")
check(dlg.winfo_width() >= 640 and dlg.winfo_height() >= 460, "ErrorDialog 尺寸合规")
btns = collect_fluent_buttons(dlg)
check(len(btns) == 2, "ErrorDialog 有 2 个 FluentButton（关闭/导出日志）", f"({len(btns)})")
dlg.destroy()

print("\n--- DismPPGuide ---")
try:
    proc = subprocess.Popen(["cmd.exe", "/k"], creationflags=0x08000000)
    guide = pc.DismPPGuide(app, proc)
    for _ in range(8):
        app.update()
    check(guide.winfo_width() >= 360, f"DismPPGuide 宽度合规", f"({guide.winfo_width()})")
    btns = collect_fluent_buttons(guide)
    check(len(btns) == 0, f"DismPPGuide 底部按钮已移除（无 FluentButton）", f"({len(btns)})")
    # v0.3.0：手动关闭应置位会话标记并不再弹出
    app._dismpp_guide_dismissed = False
    guide._on_manual_close()
    check(app._dismpp_guide_dismissed is True, "手动关闭置位 _dismpp_guide_dismissed")
    check(guide.winfo_exists() == 0, "手动关闭后窗口销毁")
    proc.terminate()
except Exception as e:
    check(False, "DismPPGuide 构造", f"{type(e).__name__}: {e}")

print("\n--- open_settings ---")
try:
    app.open_settings()
    for _ in range(8):
        app.update()
    toplevels = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]
    check(len(toplevels) >= 1, "open_settings 打开了新窗口")
    if toplevels:
        w = toplevels[0]
        btns = collect_fluent_buttons(w)
        check(len(btns) >= 6, f"open_settings 有 ≥6 个 FluentButton", f"({len(btns)})")
        w.destroy()
except Exception as e:
    check(False, "open_settings 构造", f"{type(e).__name__}: {e}")

# 恢复 wait_window（卫生）
tk.Misc.wait_window = _orig_wait_window
app.destroy()

print("\n" + "=" * 60)
if FAILS:
    print(f"失败 {len(FAILS)} / {N}")
    for f in FAILS:
        print(f"  ✗ {f}")
    sys.exit(1)
print(f"全部 {N} 项通过")
