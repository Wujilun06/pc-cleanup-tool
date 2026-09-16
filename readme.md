# 电脑清理工具 — 项目架构与维护手册

> 本文档面向**日后接手维护的 AI 模型 / 开发者**编写。凡是可能用到的细节都已展开，
> 包括纯文本修改、功能增删、打包分发、测试运行以及一系列"踩过的坑"。
> 维护前请先通读第 0 节（环境）与第 1 节（目录），改完务必跑一遍第 9 节的测试与第 8 节的打包。

---

## 隐私说明

本项目**无需 `private_config.json`**：运行时不读取任何密钥 / 登录态文件（清理逻辑只操作本机缓存与临时目录，无远程凭证）。这是统一的「单一隐私文件」约定的例外——无需创建该文件。构建产物（`build/`、`dist/`、`.spec`）与日志已在 `.gitignore` 忽略。

## 0. 基本信息与环境（必读）

- **用途**：Windows 桌面端单文件 GUI 清理工具，清理微信 / QQ / 钉钉缓存、
  系统临时文件，并引导用户用 Dism++ 做空间回收。
- **交付形态**：单个 `电脑清理工具.exe`（PyInstaller `--onefile`）。**该 exe 可独立复制、
  同目录其他文件全部删除后仍可正常运行**（运行时仅向系统 `%TEMP%` 自解包，不依赖同目录文件，
  也不会在 exe 旁边写任何配置）。
- **唯一源码**：`src/pc_cleaner.py`（约 2300 行，所有界面 / 逻辑 / 文案都在这一份文件里）。
- **Python 运行环境（重要）**：
  - 必须使用隔离 venv：`C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe`
    （Python 3.11.9，已装 `tkinter`、`PIL`、`PyInstaller`）。
  - **系统自带的 3.13 没有 tkinter，不能用于运行 / 测试 / 打包本程序。**
  - 验证命令（在 Git Bash / 终端中）：
    ```bash
    "C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe" -c "import tkinter, PIL, PyInstaller; print('ok')"
    ```
- **safe-delete 拦截（关键陷阱）**：本环境有一层 `CODEBUDDY_SAFE_DELETE_ENABLED` 拦截，
  会把 `os.remove` 重定向到回收站，`build.py` 已内置 `os.environ["CODEBUDDY_SAFE_DELETE_ENABLED"]="0"`。
  **手动运行任何 Python 脚本前，请在命令前加 `export CODEBUDDY_SAFE_DELETE_ENABLED=0 &&`**，
  否则涉及文件删除的逻辑会被静默改写、引发诡异行为。
- **UI 字体 / 主题**：深浅双主题（Win11 Fluent 风格）。主题切换会**销毁并重建所有子控件**，
  但保留任务实例与日志总线（详见第 6 节）。

---

## 1. 目录结构

```
E:\个人项目\电脑清理工具\
├── src\
│   └── pc_cleaner.py        ★ 唯一源码。所有逻辑与文案都在这。
├── build.py                 ★ 打包脚本（PyInstaller --onefile --noconsole --uac-admin）
├── tests\                   ★ 测试与调试脚本（不影响程序本体，建议保留）
│   ├── test_fluent_ui.py        界面控件结构测试（71 项）
│   ├── test_dialogs.py          弹窗冒烟测试（11 项）
│   ├── test_integration.py      构造 App + 切主题集成测试
│   ├── test_dismpp_guide.py     Dism++ 引导窗行为测试
│   ├── verify_fixes.py          钉钉缓存规则 / 控件结构验证
│   ├── shot_*.py                截图脚本（需真实显示器，多屏下不可靠，仅调试用）
│   └── ...
├── dist\
│   └── 电脑清理工具.exe     ★ 打包产物（最终交付物）
├── build\                   PyInstaller 中间产物（可随时删除，会重新生成）
├── .workbuddy\              WorkBuddy 会话记忆 / 配置（与程序无关）
└── readme.md                （本文件）
```

**维护时真正需要的文件只有 `src/pc_cleaner.py` + `build.py` + Python 环境**；
`dist/`、`build/` 都是可由源码重新生成的产物。

---

## 2. 源码总览（`src/pc_cleaner.py`）

> 行号随版本会漂移，**强烈建议按"符号名"搜索而非死记行号**。下面给出"当前大致位置 + 符号名"。

| 区块 | 符号 / 常量 | 作用 |
|------|------------|------|
| 应用元信息 | `APP_NAME`(L41) / `APP_VER`(L42) / `REG_KEY`(L43) | 程序名、版本号、注册表键 `Software\PCCleaner` |
| 主题色板 | `THEMES`(L49) / `THEME`(L83) / `_sync_theme_globals`(L89) | 深/浅两套色，短名 `BG/CARD/ACCENT/...` 由它同步 |
| 主题切换 | `set_theme`(L113) / `apply_theme`(L124) / `App.rebuild_ui`(L1745) | 详见第 6 节 |
| 控件库 | `FluentButton` / `FluentTile` / `Pill` / `FluentCard` | 全部是 `Frame + Canvas(仅画圆角背景) + 原生 Label` |
| 日志总线 | `LogBus`(`LOG`) / `LOG.add_sink` / `App._drain` | 内存日志，通过队列回写主线程 Text |
| 缓存规则 | `CACHE_RULES`(L500) / `APP_LABEL`(L524) | 各 IM 要清理的子目录 glob 规则 |
| 路径解析 | `resolve_cache_dirs`(L549) / `_dingtalk_roots`(L527) / `detect_root` | 定位各 App 数据目录（多候选自动择优） |
| 删除实现 | `purge_directory` | 遍历删除文件（含长路径 `\\?\` 前缀与 chmod），再删空目录 |
| 任务基类 | `class Task`(L590) / `TASK_REGISTRY` / `@register`(L613) | 所有清理功能的基类与注册机制 |
| IM 公共实现 | `class IMCacheTask(Task)`(L666) | 微信/QQ/钉钉缓存清理公共逻辑 |
| 具体任务 | `TaskClearTemp`(L623) / `TaskWeChat`(L710) / `TaskQQ`(L722) / `TaskDingTalk`(L734) / `TaskDiskCleanup`(L848) / `TaskDismPP`(L941) | 各功能磁贴 |
| 执行流程 | `App.run_task`(L2012) / `_run_async`(L2108) / `_launch`(L2138) / `run_all`(L2121) / `_run_dismpp_guided`(L2031) | 确认弹窗 → 后台线程执行 → 日志回填 |
| Dism++ 引导 | `class DismPPGuide(tk.Toplevel)`(L1430) | 置顶引导窗，自动/手动关闭机制 |
| 设置 | `App.open_settings`(L2201) / `reg_get` / `reg_set` | 路径与主题设置，存注册表 |

---

## 3. 主题与配色系统

- 两套色板定义在 `THEMES = {"dark": {...}, "light": {...}}`（L49）。
- 模块级短名（`BG, CARD, TEXT, ACCENT, BORDER, OKC, WARNC, ERRC, ...`）由
  `_sync_theme_globals()`(L89) 从当前 `THEME` 同步。**新增颜色时，必须同时在
  `THEMES["dark"]`、`THEMES["light"]` 两处加键，并在 `_sync_theme_globals` 里加一行同步，
  否则浅色/深色会缺字段。**
- 当前主题由 `REG_KEY` 下 `theme` 值决定，缺省深色。
- **改配色**：只改 `THEMES` 字典即可，全程序都引用短名，自动生效。

---

## 4. 控件库（⚠ 含一个重大历史坑）

四个控件 `FluentButton`、`FluentTile`、`Pill`、`FluentCard`：

- **统一结构**：`tk.Frame` 容器 + 一个 `tk.Canvas`（**仅用 `create_polygon` 画圆角背景**）
  + 一个或多个**原生 `tk.Label`**（用 `place` 居中，**绝不用 `Canvas.create_text`**）。
- **为什么这么绕（重要）**：在 Windows **200% DPI** 下，`Canvas.create_text` / 
  `Canvas` 内嵌 `Label`（`create_window`）会把文字**绘制两次并错位**（每个字符"双重"效果）。
  这是 tkinter 已知 bug。用"原生 Label 独立渲染"是唯一正确解法。
  → **以后新增任何画字的控件，绝对不要用 `Canvas.create_text` 或 `create_window` 内嵌 Label。
     一律走 `Frame + Canvas背景 + 原生Label`。** 全文已无 `create_text`，新增代码请保持。
- `FluentButton` 触发回调：没有 `command=` 参数，直接给内部 `_cmd` 字段赋值
  （如 `dark_btn._cmd = lambda: ...`，见 `open_settings` 中的用法）。
- 按钮宽度：内部用 `font.measure(text) * 1.45 + padx*2` 估算（measure 对中英混排低估，故乘 1.45）。

---

## 5. 缓存清理逻辑

- `CACHE_RULES`(L500) 是核心：键为 `"wechat"/"qq"/"dingtalk"`，值为要清理的子目录 **glob 列表**。
  - `**/...` 表示递归；`adacb*` 是钉钉版本化资源池前缀通配。
  - **钉钉安全红线**：只清理 `AppData` 下的缓存（`plugins`、`DingpanSyncUpgrade`、`adacb*/...`），
    **绝不**把 `Program Files\DingTalk\plugins` 当缓存（那是程序本体，删了会弄坏钉钉）。
    `adacb*/DBFiles`(聊天记录)、`AvatarFiles`(头像) **明确不放入规则**。
- `resolve_cache_dirs(app)`(L549)：钉钉在多个 AppData 候选根里**自动选命中规则最多的那个**
  （`_dingtalk_roots` L527 列出候选，仅 AppData，不含 Program Files）；微信/QQ 走 `detect_root`。
- `purge_directory(d)`：删除目录内文件与空目录，**保留目录自身**；被占用文件跳过并计失败数。
- `IMCacheTask`(L666) 封装了 `available / describe / run`，三个 IM 任务继承它，只需填
  `key/app/name/icon/desc/order` 与 `@register`。

---

## 6. 主题切换机制（改 UI 必看，曾出过 bug）

- 流程：`apply_theme(name)` → 写注册表 → `App.rebuild_ui()`。
- `rebuild_ui()`(L1745) **销毁所有子控件并重建**，但 **root 本身不销毁**，且**保留
  `self._tasks`（任务实例）与日志总线**（重建后由 `_restore_log` 回填历史日志）。
- **两个历史雷区（已修，改时勿再引入）**：
  1. `rebuild_ui` 开头必须 `self.configure(bg=BG)` 重新设置 root 背景，否则切浅色后
     root 客户区仍是深色（表现为"切换后外侧深框/白线"）。
  2. `_restore_log` 从日志总线取的是**已格式化的字符串**，解包时只能按字符串解析级别，
     **不能**当 `(行, 级别)` 元组解包，否则每次切主题（只要有过日志）就抛 `ValueError` 被
     `apply_theme` 的 `try/except: pass` 静默吞掉 → UI 停在半重建的坏状态。
     ⚠ `apply_theme` 的 `try/except: pass` 会掩盖内部异常，凡在此吞异常至少要记一条日志。
- 新增控件后，若需在主题切换后刷新外观，要么在 `rebuild_ui` 的重建流程里包含它，
  要么绑定 `<Configure>` 重绘（参考 `FluentCard` 的做法）。

---

## 7. 任务系统

- 基类 `Task`(L590) 字段：`key / name / icon / desc / order`，方法 `available() / describe() / run()`。
- 注册：类上加 `@register`（L613），`@register` 会把类追加进 `TASK_REGISTRY`。
- 磁贴按 `order` 排序展示（`App._build_ui` 中用 `sorted(..., key=lambda x: x.order)`）。
- 执行入口 `App.run_task(key)`(L2012)：
  - `key == "dismpp"` → 走 `_run_dismpp_guided`（特殊交互流程，见第 8 节）。
  - 其余 → 先 `describe()` 生成确认弹窗，确认后 `_launch(t.run)` 在后台线程执行。
- `run_all()`(L2121)：一键清理，**自动排除 `interactive=True` 的任务**（如 Dism++）。

---

## 8. Dism++ 引导窗（`DismPPGuide`，v0.3.0 行为）

- 位置：`class DismPPGuide(tk.Toplevel)`(L1430)。置顶、贴在 Dism++ 窗口右侧。
- **无底部按钮**（v0.3.0 移除"取消 / 已完成"两个按钮）。
- 4 个步骤文案在 `DismPPGuide.STEPS`(L1441) 列表里；引导正文/警示在 `self.body` 的
  `tk.Label(text=...)`（约 L1482 / L1497），均为字面量。
- **自动关闭**：`_poll_dismpp` 每 800ms 轮询，当 `proc.poll() is not None` 且
  `_dismpp_window_exists()` 为 False（进程退出 + 窗口消失）时调用 `_on_auto_close()` 销毁。
- **手动关闭不再弹出**：绑定 `WM_DELETE_WINDOW` → `_on_manual_close()`，置位
  `App._dismpp_guide_dismissed = True`（**会话级**，仅当前运行有效，不写盘）。
  之后 `_run_dismpp_guided` 检测到该标记会**跳过引导窗**、也**不兜底 terminate** Dism++。
  ⚠ 自动关闭路径**不**置该标记（下次仍可正常弹）。
- 窗口尺寸 `WIN_W/WIN_H/WRAP_W`（L1446-1449）。200% DPI 下内容较多，曾因 380×440 裁切，
  现 620×640；调尺寸后请同步确认 `STEPS` 与警示的 `wraplength`。

---

## 9. 测试与运行

用隔离 venv 运行，**命令前加 `export CODEBUDDY_SAFE_DELETE_ENABLED=0 &&`**：

```bash
export CODEBUDDY_SAFE_DELETE_ENABLED=0 && cd "E:/个人项目/电脑清理工具" && \
"C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe" \
  tests/test_fluent_ui.py        # 71 项：控件结构 / 圆角 / 换行
  tests/test_dialogs.py          # 11 项：各弹窗冒烟
  tests/test_integration.py      # 构造 App + 切主题
  tests/test_dismpp_guide.py     # 引导窗行为
```

- 这些测试用 `app.update()` 循环而非阻塞 `mainloop`，可无头运行。
- `shot_*.py` 是真实截图脚本，**多显示器下截图会错位**，仅供单屏调试，不可用其做视觉验证。
- 本环境**模型无法读取图片**，所有视觉验证只能靠"像素采样(PIL)"或"程序化几何/值检查"。

---

## 10. 打包与分发

```bash
export CODEBUDDY_SAFE_DELETE_ENABLED=0 && cd "E:/个人项目/电脑清理工具" && \
"C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe" build.py
```

- `build.py` 关键 PyInstaller 参数：`--onefile`（单文件）、`--noconsole`（无黑窗）、
  `--uac-admin`（启动请求管理员，清理系统缓存必需）、`--clean --noconfirm`，
  输出到 `dist/电脑清理工具.exe`。
- 产物是**单文件**：复制即用，同目录可不含任何其他文件。
- 版本号只在 `APP_VER`(L42) 一处，发版时在此改动（标题栏与启动日志都会引用）。

---

## 11. 日常维护操作速查

### 11.1 纯文本 / 文案修改（最常见）

直接用编辑器打开 `src/pc_cleaner.py`，按"要改的那句话"搜索中文串即可，它们都是字面量：

| 想改什么 | 搜什么 / 位置 |
|----------|--------------|
| 版本号 | `APP_VER = "0.3.0"`（L42） |
| 程序标题（顶栏） | `APP_NAME = "电脑清理工具"`（L41）；界面用 `self.title(APP_NAME)` |
| 功能磁贴名称/图标/悬停说明 | 对应任务类的 `name / icon / desc`，如 `TaskDismPP`(L941)、`TaskWeChat`(L710)… |
| 确认弹窗详请文案 | 对应任务的 `describe()` 方法（如 `TaskDismPP.describe` L956） |
| Dism++ 引导窗 4 步骤 | `DismPPGuide.STEPS`(L1441) |
| Dism++ 引导窗正文/警示 | 约 L1482 / L1497 的 `tk.Label(text=...)` |
| 主界面区块标题/按钮 | `_build_ui` 里的 `tk.Label(..., text="功能说明"/"运行日志"/"清空日志")` 等 |
| 设置窗口说明 | `open_settings`(L2201) 内文案 |

### 11.2 增加一个 IM 类清理（微信/QQ/钉钉式）

1. 在 `CACHE_RULES`(L500) 加键，值为该 App 缓存子目录的 glob 列表；
2. `APP_LABEL`(L524) 加中文名映射；
3. 仿 `TaskDingTalk`(L734) 写一个子类继承 `IMCacheTask`，填
   `key/app/name/icon/desc/order` 并加 `@register`；
4. 若该 App 根目录不在默认探测里，在 `detect_root` / `_dingtalk_roots` 补充候选。

### 11.3 增加一个非 IM 的全新任务

1. 仿 `TaskClearTemp`(L623) / `TaskDiskCleanup`(L848) 写 `class XxxTask(Task)`；
2. 实现 `available() / describe() / run()`，加 `@register`；
3. 需要用户手动交互（如 Dism++ 引导窗）则设 `interactive = True` 并在 `run_task`(L2012)
   里加 `if key == "xxx": self._run_xxx_guided(t); return` 分支（参考 dismpp）。

### 11.4 删除一个功能

1. 删掉对应任务类与 `@register`；
2. 在 `CACHE_RULES` / `APP_LABEL` 删除对应键（IM 类）；
3. 若有 `run_task` 里的特判分支（如 `if key == "dismpp"`）一并删除；
4. 跑第 9 节测试确认无遗漏引用。

---

## 12. 已知雷区汇总（改代码前必看）

1. **DPI 文字重影**：绝不用 `Canvas.create_text` / `create_window` 内嵌 Label 画字（第 4 节）。
2. **safe-delete 拦截**：跑脚本前务必 `export CODEBUDDY_SAFE_DELETE_ENABLED=0`（第 0 节）。
3. **Python 版本**：必须用 3.11 隔离 venv，系统 3.13 无 tkinter（第 0 节）。
4. **主题切换半重建**：`rebuild_ui` 必须重设 root `bg`；`_restore_log` 按字符串解析（第 6 节）。
5. **钉钉缓存红线**：只清 AppData 缓存，绝不碰 Program Files 与聊天记录/头像目录（第 5 节）。
6. **多屏截图错位 + 模型不读图**：视觉验证只能靠像素采样或几何值检查（第 9 节）。
7. **`apply_theme` 的 `try/except: pass`** 会吞掉主题切换异常 → 至少记日志。
8. **FluentButton 无 `command=`**：用 `._cmd = lambda: ...` 赋值回调。

---

## 13. 维护者须知（用户偏好）

- 用户要求**诚实**：解决不了就直说，不要无限循环返工；结论要以"程序实际运行结果"为准，
  不要仅凭记忆/推断下结论。
- 涉及破坏性操作（真实删除用户数据、移动个人文件）必须先确认、先备份，绝不在未授权时执行。
- 改完一律：跑测试（第 9 节）→ 重新打包（第 10 节）→ 交付 `dist/电脑清理工具.exe`。

---

## 14. 隐私与仓库说明

- **本仓库不含任何密钥 / 密码 / 凭证**：程序逻辑仅做本地缓存清理，不涉及账号体系。
- **构建产物不入库**：`build/`、`dist/` 已加入 `.gitignore`，属于可由源码重新生成的产物；
  真正入库的只有 `src/pc_cleaner.py`、`build.py`、`tests/` 与文档。
- **本机路径为环境特定**：文档与源码中出现 `C:/Users/21654/...`、`E:\个人项目\...` 等绝对路径，
  是本机环境的隔离 Python / 项目目录，**克隆到其它机器后需替换为对应环境路径**。
- **`.workbuddy/` 已移除**：曾误提交的工作日志（含本机路径）已从历史清除，请勿重新加入。
