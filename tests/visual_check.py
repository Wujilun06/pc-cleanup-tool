"""
可视化自测脚本：启动程序 → 等待 → 截屏 → 打开一个确认弹窗 → 截屏。
用法: python tests/visual_check.py
"""
import os
import sys
import time
import subprocess
import importlib.util

# 1) 启动源码版（用 pythonw 无控制台）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "pc_cleaner.py")
PYTHON = sys.executable
SCREENSHOT_DIR = os.path.join(ROOT, "build")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Monkey-patch wait_window 让对话框立即销毁，不阻塞主循环
spec = importlib.util.spec_from_file_location("pc", SRC)
pc = importlib.util.module_from_spec(spec)
sys.modules["pc"] = pc
spec.loader.exec_module(pc)
# 让对话框的 __init__ 不阻塞，测试代码自己管理生命周期
pc.ConfirmDialog.wait_window = lambda self: None
pc.ErrorDialog.wait_window = lambda self: None

from PIL import ImageGrab


def take_screenshot(name: str):
    path = os.path.join(SCREENSHOT_DIR, name)
    img = ImageGrab.grab()
    img.save(path)
    print(f"  -> 截图保存: {path}  ({img.size[0]}x{img.size[1]})")
    return path


def main():
    root = pc.App()
    root.geometry("1140x900")
    # 强制置顶 + 抢焦点
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    def step1():
        print("[1/3] 主窗口（悬停 Dism++ → 显示最长说明）")
        # 直接写入最长的一条说明，验证说明区无需滚动条即可完整显示
        longest = max((c().desc for c in pc.TASK_REGISTRY),
                      key=lambda s: len(s.splitlines()))
        root._set_help(longest)
        root.update_idletasks()
        time.sleep(0.8)
        root.update()
        root.lift(); root.focus_force()
        take_screenshot("v-main.png")
        root.after(300, step2)

    def step2():
        print("[2/3] 打开确认弹窗")
        dlg = pc.ConfirmDialog(root, "确认执行「测试」？",
                               "目标目录：\n  C:\\Test\n\n将删除该目录下所有文件。\n\n"
                               "这是很长很长很长很长很长很长很长的测试内容，"
                               "用于验证弹窗高度是否足够、按钮是否被裁切、"
                               "文字是否完整可读。\n\n"
                               "支持多行说明。\n"
                               "请检查按钮可见。")
        dlg.attributes("-topmost", True)
        dlg.lift()
        root.update_idletasks()
        time.sleep(0.5)
        root.update()
        dlg.lift(); dlg.focus_force()
        take_screenshot("v-confirm.png")
        # 输出按钮位置用于程序化验证
        def walk(w, out):
            out.append(w)
            for c in w.winfo_children(): walk(c, out)
            return out
        btns = [w for w in walk(dlg, []) if isinstance(w, type(dlg.__class__.__mro__[1])) and hasattr(w, "cget") and "text" in w.keys()]
        # 简单：找 button-like widgets
        from tkinter import Button
        btns = [w for w in walk(dlg, []) if isinstance(w, Button)]
        dh = dlg.winfo_height()
        print(f"  弹窗尺寸: {dlg.winfo_width()}x{dh}")
        for b in btns:
            by, bh = b.winfo_y(), b.winfo_height()
            ok = 0 <= by and by + bh <= dh + 1
            print(f"  按钮 {b.cget('text')!r:20s} y={by:>4} h={bh:>3} -> {'OK' if ok else 'CUT!'}")
        dlg.destroy()
        root.after(200, step3)

    def step3():
        print("[3/3] 关闭程序")
        root.destroy()

    root.after(800, step1)
    root.mainloop()
    print("完成")


if __name__ == "__main__":
    main()
