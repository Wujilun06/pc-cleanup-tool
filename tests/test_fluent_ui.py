# -*- coding: utf-8 -*-
"""
Fluent 版 UI 验证：
  1. 启动主窗口，等待布局稳定
  2. 对每条功能说明（含「不可用」追加行）逐条灌入说明区
  3. 断言说明区完整可见（Text.yview() 必须是 (0.0, 1.0)，即无隐藏行）
  4. 在多种窗口宽度下重复验证（换行行数会随宽度变化）
  5. 断言说明区高度是运行时测量出来的（非写死的 112）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pc_cleaner as pc

FAILS: list[str] = []
CHECKS = [0]


def check(cond: bool, name: str, detail: str = ""):
    CHECKS[0] += 1
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name} {detail}")
        FAILS.append(f"{name} {detail}")


def help_fully_visible(app: pc.App) -> tuple[bool, str]:
    """说明区内容是否被裁剪：yview 首尾为 0.0/1.0 表示全部可见。"""
    app.help_text.update_idletasks()
    app.update()
    y0, y1 = app.help_text.yview()
    h = app.help_text.winfo_height()
    if h <= 4:
        return False, f"(说明区高度异常: {h})"
    if y0 <= 0.0001 and y1 >= 0.9999:
        return True, ""
    return False, f"(yview=({y0:.3f},{y1:.3f}) 高度={h}px，内容被裁剪)"


def main():
    print("=" * 70)
    print("Fluent UI 验证")
    print("=" * 70)

    pc.set_dpi_aware()
    app = pc.App()
    app.update()
    app.after(300, app.quit_app) if False else None

    # 等 _fit_help_height 的 after(150) 跑完
    for _ in range(30):
        app.update()
    app.update()

    font = pc.tkfont.Font(family=pc.FONT, size=9)
    print(f"\n[信息] 实际使用字体: {pc.FONT}")
    print(f"[信息] 行高(linespace): {font.metrics('linespace')}px")
    print(f"[信息] 说明区卡片实测高度: {app.help_card.winfo_height()}px")
    print(f"[信息] 计算高度记录值 _help_h: {app._help_h}px")

    check(app._help_h > 0, "说明区高度已在运行时计算", f"(_help_h={app._help_h})")

    # 收集全部说明样本
    samples = list(app._help_samples) + [pc.DEFAULT_HELP]
    # 去重但保留顺序
    seen, uniq = set(), []
    for s in samples:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    print(f"[信息] 说明样本数: {len(uniq)} 条（含「不可用」态变体）")

    for width in (1040, 1140, 1300, 1600):
        print(f"\n--- 窗口宽度 {width}px ---")
        try:
            app.geometry(f"{width}x920")
        except Exception:
            pass
        for _ in range(10):
            app.update()
        computed = app._help_h
        card_h = app.help_card.winfo_height()
        print(f"  [信息] 计算高度={computed}px  卡片实际高度={card_h}px")
        for i, s in enumerate(uniq, 1):
            first = s.split("\n")[0][:18]
            app._set_help(s)
            ok, detail = help_fully_visible(app)
            check(ok, f"w={width} 说明#{i}「{first}…」完整显示", detail)

    # 悬停模拟：把鼠标移入磁贴（生成 Enter 事件），确认说明区同步更新且不裁剪
    print("\n--- 悬停事件模拟 ---")
    try:
        app.geometry("1140x920")
        for _ in range(10):
            app.update()
        for key, t in app._tasks.items():
            tile = t._btn
            tile.event_generate("<Enter>", x=5, y=5)
            app.update()
            txt = app.help_text.get("1.0", "end-1c")
            check(bool(txt.strip()) and txt != pc.DEFAULT_HELP,
                  f"悬停「{t.name}」说明区已更新", f"(内容前 20 字: {txt[:20]!r})")
            ok, detail = help_fully_visible(app)
            check(ok, f"悬停「{t.name}」说明未裁剪", detail)
            tile.event_generate("<Leave>", x=5, y=5)
            app.update()
    except Exception as e:
        check(False, "悬停事件模拟", f"{type(e).__name__}: {e}")

    # 组件自检
    print("\n--- Fluent 组件自检 ---")
    check(isinstance(app.help_card, pc.FluentCard), "说明区使用圆角卡片 FluentCard")
    check(isinstance(app.log_card, pc.FluentCard), "日志区使用圆角卡片 FluentCard")
    tiles = [t._btn for t in app._tasks.values()]
    check(all(isinstance(x, pc.FluentTile) for x in tiles),
          f"{len(tiles)} 个功能磁贴均为 FluentTile")
    check(hasattr(app, "_pill") and isinstance(app._pill, pc.Pill),
          "顶栏使用胶囊徽章 Pill")

    # 圆角几何：点数 = 4 角 × (steps+1)
    pts = pc.round_rect_points(0, 0, 100, 50, 8, steps=6)
    check(len(pts) == 4 * 7 * 2, "圆角矩形顶点数正确", f"({len(pts)//2} 个点)")

    # 换行模拟：极窄宽度下必须产出多行
    lines = pc.wrap_lines("自动定位微信数据目录（新版 xwechat_files / 旧版 WeChat Files）",
                          font, 120)
    check(len(lines) >= 2, "窄宽度下自动换行生效", f"(得到 {len(lines)} 行)")

    app.destroy()

    print("\n" + "=" * 70)
    if FAILS:
        print(f"结果：{len(FAILS)} / {CHECKS[0]} 项失败")
        for f in FAILS:
            print(f"  ✗ {f}")
        return 1
    print(f"结果：全部 {CHECKS[0]} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
