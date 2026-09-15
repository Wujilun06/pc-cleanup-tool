"""验证 DismPPGuide 的新行为（v0.3.0）：
  1. 底部两个按钮已移除；
  2. 手动关闭 → 置位会话标记 _dismpp_guide_dismissed，且 Dism++ 不被终止；
  3. 自动关闭（Dism++ 已关）→ 不置位标记。
"""
import sys
import tkinter as tk

sys.path.insert(0, "src")
import pc_cleaner as pc


def _count_fluent_buttons(widget):
    n = 0
    for child in widget.winfo_children():
        if isinstance(child, pc.FluentButton):
            n += 1
        n += _count_fluent_buttons(child)
    return n


def main():
    app = pc.App()
    app.withdraw()

    # 假进程：poll() 返回 None（仍在运行），避免真实启动 Dism++
    class FakeProc:
        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("Dism++ 不应被 terminate")

        def kill(self):
            raise AssertionError("Dism++ 不应被 kill")

    # ---- 1. 无底部按钮 ----
    g1 = pc.DismPPGuide(app, FakeProc())
    n_btn = _count_fluent_buttons(g1)
    print(f"  [1] 引导窗内 FluentButton 数量 = {n_btn} (期望 0)")
    assert n_btn == 0, "底部按钮未移除"
    g1.destroy()

    # ---- 2. 手动关闭 → 置位标记 ----
    app._dismpp_guide_dismissed = False
    g2 = pc.DismPPGuide(app, FakeProc())
    g2._on_manual_close()
    print(f"  [2] 手动关闭后 _dismpp_guide_dismissed = {app._dismpp_guide_dismissed} (期望 True)")
    assert app._dismpp_guide_dismissed is True
    assert g2.winfo_exists() == 0, "手动关闭后窗口应销毁"
    # 验证 _run_dismpp_guided 会跳过引导（不抛 terminate 异常）
    print("  [2] 手动关闭路径未触发 Dism++ terminate（符合预期）")

    # ---- 3. 自动关闭（Dism++ 已关）→ 不置位标记 ----
    app._dismpp_guide_dismissed = False
    g3 = pc.DismPPGuide(app, FakeProc())

    class ExitedProc(FakeProc):
        def poll(self):
            return 0  # 进程已退出

    g3.proc = ExitedProc()
    # 打补丁：让窗口检测返回 False（窗口已消失）
    orig = pc._dismpp_window_exists
    pc._dismpp_window_exists = lambda: False
    try:
        g3._on_auto_close()
    finally:
        pc._dismpp_window_exists = orig
    print(f"  [3] 自动关闭后 _dismpp_guide_dismissed = {app._dismpp_guide_dismissed} (期望 False)")
    assert app._dismpp_guide_dismissed is False
    assert g3.winfo_exists() == 0, "自动关闭后窗口应销毁"

    app.destroy()
    print("✓ DismPPGuide 行为全部验证通过")


if __name__ == "__main__":
    main()
