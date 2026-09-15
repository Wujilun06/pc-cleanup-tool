"""
说明区尺寸验证：逐条渲染全部功能说明，确认在去掉滚动条后
每一条都能在固定高度的说明区内完整显示（无裁切、无溢出）。

判定方法：用 Text.count("1.0", "end", "displaylines") 得到实际显示行数，
再比对 说明区高度 / 行高 可容纳的最大行数。
"""
import os
import sys
import importlib.util
import tkinter as tk
from tkinter import font as tkfont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "pc_cleaner.py")

spec = importlib.util.spec_from_file_location("pc", SRC)
pc = importlib.util.module_from_spec(spec)
sys.modules["pc"] = pc
spec.loader.exec_module(pc)

HELP_H = 112          # 说明区固定高度（与源码保持一致）
PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    print(("  [OK]   " if cond else "  [FAIL] ") + msg)
    if cond:
        PASS += 1
    else:
        FAIL += 1


def main():
    root = tk.Tk()
    root.geometry("1200x400+0+0")     # 必须真实映射，否则 Text 拿不到实际宽度
    root.update()
    f = tkfont.Font(family=pc.FONT, size=9)
    line_h = f.metrics("linespace")

    # 说明区可用宽度：窗口 1140 - 外层 padx*2 - Text padx*2 - 边框
    avail_w = 1140 - 20 * 2 - 14 * 2 - 2
    # 说明区可用高度：固定高度 - Text pady*2 - 边框
    avail_h = HELP_H - 10 * 2 - 2
    cap_lines = avail_h // line_h

    print(f"字体行高={line_h}px  说明区可用宽={avail_w}px  可用高={avail_h}px"
          f"  → 最多容纳 {cap_lines} 行\n")

    texts = {}
    for cls in sorted(pc.TASK_REGISTRY, key=lambda c: c.order):
        t = cls()
        texts[t.name] = t.desc
    # 默认提示文字
    texts["(默认提示)"] = "将鼠标悬停在上方任意按钮上，这里会显示该功能的详细说明。"
    # 不可用时的追加形态（最长场景）
    longest = max(texts.values(), key=lambda s: len(s.splitlines()))
    texts["(最长+不可用提示)"] = longest + "\n⛔ 当前不可用：未找到 Dism++，请在「路径设置」中指定"

    # 用 place 强制真实几何尺寸，避免 pack 的自适应干扰
    txt = tk.Text(root, wrap="word", font=(pc.FONT, 9), padx=14, pady=10,
                  spacing1=1, relief="flat")
    txt.place(x=0, y=0, width=1140 - 20 * 2, height=600)
    root.update()

    for name, body in texts.items():
        txt.delete("1.0", "end")
        txt.insert("1.0", body)
        txt.update_idletasks()
        # 实际显示行数（含自动折行）
        n = txt.count("1.0", "end", "displaylines")[0]
        # 是否有任何一行超出可视宽度导致横向截断
        wid = txt.count("1.0", "end", "displaychars")[0]
        need = n * line_h
        ok = need <= avail_h
        print(f"  {name}")
        print(f"      硬行数={len(body.splitlines())}  实际显示行数={n}  "
              f"需要高度={need}px / 可用={avail_h}px")
        check(ok, f"{name}: {'完整显示' if ok else f'被裁切（需 {need}px）'}")

    txt.destroy()
    root.destroy()
    print(f"\n结果: {PASS} 项通过, {FAIL} 项失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
