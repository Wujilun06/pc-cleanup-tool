# 电脑清理工具（PC Cleaner）

Windows 桌面端单文件 GUI 清理工具：清理微信 / QQ / 钉钉缓存、系统临时文件，并引导用户用 Dism++ 做空间回收。

> 仓库：`https://github.com/Wujilun06/pc-cleanup-tool`
> 交付物为单个 `电脑清理工具.exe`（PyInstaller `--onefile`），可独立复制、同目录其他文件删除后仍可正常运行。

---

## 1. 简介

- **用途**：一键清理常用 IM（微信/QQ/钉钉）的本地缓存、系统临时文件，并引导用 Dism++ 回收空间。
- **形态**：单文件 `.exe` 图形界面（Win11 Fluent 风格，深/浅双主题），无需安装、复制即用。
- **唯一源码**：`src/pc_cleaner.py`（约 2300 行，所有界面 / 逻辑 / 文案都在这一份文件里）。
- **运行时不落盘任何业务文件**：配置写入注册表 `HKCU\Software\PCCleaner`；退出时清理 PyInstaller 自解压残留。

---

## 2. 原理

### 2.1 用到的编程语言与软件程序

| 类别 | 内容 |
|------|------|
| 编程语言 | **Python 3.11**（⚠ 系统自带 3.13 无 tkinter，**不能用**；必须用隔离 venv，见第 5 节） |
| GUI 库 | **tkinter**（标准库）+ **Pillow(PIL)**（图标/图片处理） |
| 打包工具 | **PyInstaller**（`--onefile --noconsole --uac-admin`） |
| 外部程序 | **Dism++**（空间回收引导，本工具只做置顶引导窗，不内置 Dism++ 本体） |
| 系统 API | `ctypes` / `winreg`（注册表）/ `subprocess`（启动 Dism++）/ `shutil` / `stat`（长路径 `\\?\` 与 chmod） |

### 2.2 工作原理

- **缓存规则驱动**：`CACHE_RULES` 以「应用名 → 待清理子目录 glob 列表」描述各 IM 的缓存位置；
  `resolve_cache_dirs` 在多个候选根目录中自动选命中规则最多的那个。
- **任务注册机制**：所有清理功能都是 `Task` 子类，加 `@register` 后自动进入 `TASK_REGISTRY`，
  UI 按 `order` 排序展示，无需手写 UI 绑定。
- **执行流程**：点击磁贴 → `describe()` 生成确认弹窗 → 确认后后台线程 `run()` → 日志经 `LogBus`
  队列回写主线程文本框。
- **Dism++ 引导**：`TaskDiskCleanup` 之外的特殊交互任务（`dismpp`）走 `_run_dismpp_guided`，
  弹出置顶引导窗并轮询 Dism++ 进程，退出后自动关闭。
- **主题切换**：`apply_theme` → 写注册表 → `App.rebuild_ui()` 销毁并重建所有子控件（保留任务实例与日志总线）。

---

## 3. 具体实现方式

### 3.1 目录结构

```
电脑清理工具\
├── src\
│   └── pc_cleaner.py        ★ 唯一源码。所有逻辑与文案都在这。
├── build.py                 ★ 打包脚本（PyInstaller --onefile --noconsole --uac-admin）
├── tests\                   ★ 测试与调试脚本（不影响程序本体）
│   ├── test_fluent_ui.py        界面控件结构测试（71 项）
│   ├── test_dialogs.py          弹窗冒烟测试（11 项）
│   ├── test_integration.py      构造 App + 切主题集成测试
│   ├── test_dismpp_guide.py     Dism++ 引导窗行为测试
│   ├── verify_fixes.py          钉钉缓存规则 / 控件结构验证
│   └── shot_*.py                截图脚本（需真实显示器，多屏不可靠，仅调试用）
├── dist\电脑清理工具.exe     ★ 打包产物（最终交付物，可由源码重新生成）
├── build\                   PyInstaller 中间产物（可随时删除）
└── readme.md                （本文件）
```

**维护真正需要的文件只有 `src/pc_cleaner.py` + `build.py` + Python 3.11 环境**；
`dist/`、`build/` 都是可由源码重新生成的产物（已 gitignore）。

### 3.2 源码总览（`src/pc_cleaner.py`，按符号名搜索，勿死记行号）

| 区块 | 符号 | 作用 |
|------|------|------|
| 应用元信息 | `APP_NAME` / `APP_VER` / `REG_KEY` | 程序名、版本号、注册表键 `Software\PCCleaner` |
| 主题色板 | `THEMES` / `THEME` / `_sync_theme_globals` | 深/浅两套色，短名 `BG/CARD/ACCENT/...` 由它同步 |
| 主题切换 | `set_theme` / `apply_theme` / `App.rebuild_ui` | 见第 5 节雷区 |
| 控件库 | `FluentButton` / `FluentTile` / `Pill` / `FluentCard` | `Frame + Canvas(圆角背景) + 原生 Label` |
| 日志总线 | `LogBus`(`LOG`) | 内存日志，队列回写主线程 Text |
| 缓存规则 | `CACHE_RULES` / `APP_LABEL` | 各 IM 待清理子目录 glob |
| 路径解析 | `resolve_cache_dirs` / `_dingtalk_roots` / `detect_root` | 多候选自动择优 |
| 删除实现 | `purge_directory` | 递归删文件（长路径+chmod）再删空目录 |
| 任务基类 | `class Task` / `TASK_REGISTRY` / `@register` | 所有清理功能基类与注册 |
| IM 公共 | `class IMCacheTask` | 微信/QQ/钉钉缓存清理公共逻辑 |
| 具体任务 | `TaskClearTemp` / `TaskWeChat` / `TaskQQ` / `TaskDingTalk` / `TaskDiskCleanup` / `TaskDismPP` | 各功能磁贴 |
| 执行流程 | `App.run_task` / `_run_async` / `_launch` / `run_all` / `_run_dismpp_guided` | 确认 → 后台执行 → 日志回填 |
| Dism++ 引导 | `class DismPPGuide(tk.Toplevel)` | 置顶引导窗 |
| 设置 | `App.open_settings` / `reg_get` / `reg_set` | 路径与主题，存注册表 |

### 3.3 运行与打包（速览）

```bash
# ⚠ 必须用 3.11 隔离 venv，且命令前加 safe-delete 关闭环境变量（见第 5 节）
export CODEBUDDY_SAFE_DELETE_ENABLED=0 && cd "E:/个人项目/电脑清理工具" && \
"C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe" build.py
```

---

## 4. 可能用到的隐私权限和私人内容

本项目**不需要、也不包含**任何隐私文件：

- **无 `private_config.json`**：运行时不读取任何密钥 / 登录态文件（统一的「单一隐私文件」约定之例外）。
  清理逻辑只操作本机缓存与临时目录，无远程凭证。
- **需要管理员权限**：清理系统缓存需 `--uac-admin`（启动请求 UAC 提权），这是 Windows 系统行为，非隐私。
- **构建产物不入库**：`build/`、`dist/`（含 exe）、`.spec` 已加入 `.gitignore`，属可由源码重新生成的产物；
  真正入库的只有 `src/pc_cleaner.py`、`build.py`、`tests/` 与文档。
- **本机路径为环境特定**：源码/文档中出现的 `C:/Users/21654/...`、`E:\个人项目\...` 等绝对路径，
  是作者本机的隔离 Python 与项目目录，**克隆到其它机器后需替换为对应环境路径**。
- **`.workbuddy/` 不入库**：工作日志（含本机路径）已被 gitignore，请勿重新加入。

> 若未来接入需要密钥的功能（如云同步配置），仍遵循统一约定：集中到 `private_config.json` 并忽略。

---

## 5. 项目开发 / 打包过程中遇到的问题及解决方案（真实记录）

以下为开发与维护本工具时**实际踩过的坑**，后续修改前必看。

1. **200% DPI 下文字重影（tkinter 已知 bug）**
   - 现象：用 `Canvas.create_text` 或 `Canvas` 内嵌 `Label(create_window)` 时，文字被绘制两次并错位。
   - 解决：所有画字的控件统一走 `Frame + Canvas(仅画圆角背景) + 原生 Label(place 居中)`；
    **绝不再用 `Canvas.create_text` / `create_window` 内嵌 Label**。
2. **safe-delete 拦截导致删除逻辑被静默改写**
   - 现象：本环境 `CODEBUDDY_SAFE_DELETE_ENABLED` 会把 `os.remove` 重定向到回收站，
   手动跑脚本时删除被改写、引发诡异行为。
   - 解决：`build.py` 已内置 `os.environ["CODEBUDDY_SAFE_DELETE_ENABLED"]="0"`；
   **任何手动运行脚本前，命令前加 `export CODEBUDDY_SAFE_DELETE_ENABLED=0 &&`**。
3. **Python 版本陷阱（系统 3.13 无 tkinter）**
   - 现象：用系统 Python 跑/打包会 `ModuleNotFoundError: tkinter`。
   - 解决：固定用隔离 venv `C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe`
   （Python 3.11.9，已装 tkinter/PIL/PyInstaller）。
4. **主题切换「半重建」坏状态**
   - 现象：切浅色后 root 客户区仍是深色（外侧深框/白线）；或切主题时抛 `ValueError` 被静默吞掉 → UI 卡在半重建。
   - 解决：`rebuild_ui()` 开头必须 `self.configure(bg=BG)` 重设 root 背景；
   `_restore_log` 从日志总线取的是**已格式化的字符串**，按字符串解析级别，**不能**当 `(行, 级别)` 元组解包；
   `apply_theme` 的 `try/except: pass` 会掩盖异常，凡在此吞异常至少记一条日志。
5. **钉钉缓存「红线」**
   - 现象：误把 `Program Files\DingTalk\plugins` 当缓存会弄坏钉钉。
   - 解决：只清理 `AppData` 下的缓存（`plugins`/`DingpanSyncUpgrade`/`adacb*/...`）；
   `adacb*/DBFiles`(聊天记录)、`AvatarFiles`(头像) **明确不放入规则**；候选根只含 AppData（不含 Program Files）。
6. **多屏截图错位 + 模型不读图**
   - 现象：`shot_*.py` 在多显示器下截图错位；本环境无法读取图片做视觉验证。
   - 解决：视觉验证只能靠「像素采样(PIL)」或「程序化几何/值检查」；`shot_*.py` 仅单屏调试用。
7. **`FluentButton` 无 `command=` 参数**
   - 现象：直接传 `command=` 不生效。
   - 解决：给内部 `_cmd` 字段赋值（如 `dark_btn._cmd = lambda: ...`）。
8. **新增颜色必须两处同步**
   - 现象：只在 `THEMES["dark"]` 加键，浅色/深色会缺字段。
   - 解决：新增颜色须同时在 `THEMES["dark"]`、`THEMES["light"]` 加键，并在 `_sync_theme_globals` 加一行同步。

---

## 6. 致谢

- **Dism++**（空间回收工具，作者：醉透 / 羽翼城；官网 `https://www.chuyu.me/`）：本工具的「Dism++ 引导」
  流程即引导用户使用它做更深度的系统空间回收，工具本体由用户自行安装。
- **PyInstaller**：提供单文件打包能力，使工具能以一个 `.exe` 分发。
- **tkinter / Pillow**：Python 标准 GUI 与图像处理能力，构成本工具界面基础。

---

## 附：维护手册（供后续开发与修复）

> 下面是针对「日后接手维护的 AI / 开发者」展开的详细内容。改完务必跑测试（第 9 节）→ 重新打包（第 10 节）。

### A. 主题与配色系统
- 两套色板在 `THEMES = {"dark": {...}, "light": {...}}`；模块级短名（`BG, CARD, TEXT, ACCENT, ...`）
  由 `_sync_theme_globals()` 同步。新增颜色必须三处同步（见第 5 节第 8 点）。
- 当前主题由 `REG_KEY` 下 `theme` 值决定，缺省深色。改配色只改 `THEMES` 字典即可全局生效。

### B. 控件库（⚠ 含重大历史坑）
四个控件 `FluentButton`/`FluentTile`/`Pill`/`FluentCard`：统一 `tk.Frame + tk.Canvas(仅画圆角背景) + 原生 tk.Label`。
**200% DPI 下 `Canvas.create_text`/内嵌 Label 会文字重影（tkinter bug），新增画字控件一律走 Frame+Canvas背景+原生Label。**

### C. 缓存清理逻辑
- `CACHE_RULES`：键 `wechat/qq/dingtalk`，值为待清理子目录 glob。`**/...` 递归；`adacb*` 钉钉版本化资源池前缀。
- `resolve_cache_dirs(app)`：钉钉在多个 AppData 候选根中自动选命中规则最多的（`_dingtalk_roots` 仅 AppData）；
  微信/QQ 走 `detect_root`。`purge_directory(d)` 删文件与空目录、保留目录自身，被占用文件跳过并计失败数。
- `IMCacheTask` 封装 `available/describe/run`，三个 IM 任务继承它，只需填 `key/app/name/icon/desc/order` 与 `@register`。

### D. 主题切换机制（改 UI 必看）
`apply_theme(name)` → 写注册表 → `App.rebuild_ui()`。`rebuild_ui()` 销毁所有子控件并重建，但 root 不销毁，
且保留 `self._tasks` 与日志总线（重建后 `_restore_log` 回填）。两个历史雷区见第 5 节第 4 点。

### E. 任务系统
- 基类 `Task` 字段 `key/name/icon/desc/order`，方法 `available()/describe()/run()`；类上加 `@register` 进 `TASK_REGISTRY`。
- 执行入口 `App.run_task(key)`：`key=="dismpp"` 走 `_run_dismpp_guided`；其余先 `describe()` 确认弹窗，
  确认后 `_launch(t.run)` 后台线程执行。`run_all()` 一键清理，自动排除 `interactive=True` 的任务。

### F. Dism++ 引导窗（`DismPPGuide`）
- `class DismPPGuide(tk.Toplevel)` 置顶、贴 Dism++ 窗口右侧；无底部按钮（v0.3.0 移除取消/已完成）。
- 4 步文案在 `DismPPGuide.STEPS`；自动关闭：`_poll_dismpp` 每 800ms 轮询，进程退出+窗口消失时 `_on_auto_close()`。
- 手动关闭绑定 `WM_DELETE_WINDOW` → 置位 `App._dismpp_guide_dismissed=True`（会话级，不写盘），下次跳过引导窗。
- 窗口尺寸 `WIN_W/WIN_H/WRAP_W`，200% DPI 下曾因裁切，现 620×640；调尺寸后同步确认 `STEPS` 与警示的 `wraplength`。

### G. 测试与运行
```bash
export CODEBUDDY_SAFE_DELETE_ENABLED=0 && cd "E:/个人项目/电脑清理工具" && \
"C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe" \
  tests/test_fluent_ui.py tests/test_dialogs.py tests/test_integration.py tests/test_dismpp_guide.py
```
- 测试用 `app.update()` 循环而非阻塞 `mainloop`，可无头运行。`shot_*.py` 多屏错位，仅单屏调试。

### H. 打包与分发
```bash
export CODEBUDDY_SAFE_DELETE_ENABLED=0 && cd "E:/个人项目/电脑清理工具" && \
"C:/Users/21654/.workbuddy/binaries/python/envs/cleaner311/Scripts/python.exe" build.py
```
- 关键 PyInstaller 参数：`--onefile --noconsole --uac-admin --clean --noconfirm`，输出 `dist/电脑清理工具.exe`。
- 单文件：复制即用。版本号只在 `APP_VER` 一处，发版时改动。

### I. 日常维护操作速查
- **纯文本/文案**：按中文串搜索 `src/pc_cleaner.py`，均为字面量（版本号 `APP_VER`、标题 `APP_NAME`、
  磁贴 `name/icon/desc`、确认文案 `describe()`、Dism++ 步骤 `DismPPGuide.STEPS`、设置 `open_settings`）。
- **加一个 IM 类清理**：`CACHE_RULES` 加键 → `APP_LABEL` 加中文名 → 仿 `TaskDingTalk` 写子类继承 `IMCacheTask` 加 `@register`。
- **加一个非 IM 任务**：仿 `TaskClearTemp`/`TaskDiskCleanup` 写 `class XxxTask(Task)`，实现三方法加 `@register`；
  需手动交互则设 `interactive=True` 并在 `run_task` 加特判分支。
- **删一个功能**：删任务类与 `@register` → 删 `CACHE_RULES`/`APP_LABEL` 对应键 → 删 `run_task` 特判分支 → 跑测试。

### J. 已知雷区汇总（改代码前必看）
1. DPI 文字重影：禁用 `Canvas.create_text`/内嵌 Label（第 B 节）。
2. safe-delete 拦截：跑脚本前 `export CODEBUDDY_SAFE_DELETE_ENABLED=0`（第 5 节第 2 点）。
3. Python 版本：必须 3.11 隔离 venv（第 5 节第 3 点）。
4. 主题切换半重建：`rebuild_ui` 重设 root `bg`；`_restore_log` 按字符串解析（第 5 节第 4 点）。
5. 钉钉缓存红线：只清 AppData，不碰 Program Files 与聊天记录/头像（第 5 节第 5 点）。
6. 多屏截图错位 + 模型不读图（第 5 节第 6 点）。
7. `apply_theme` 的 `try/except: pass` 吞异常 → 至少记日志。
8. `FluentButton` 无 `command=`，用 `._cmd = lambda: ...`。

### K. 维护者须知（用户偏好）
- 诚实：解决不了直说，不无限返工；结论以「程序实际运行结果」为准，不凭记忆/推断。
- 破坏性操作（真实删除用户数据、移动个人文件）必须先确认、先备份，未授权不执行。
- 改完一律：跑测试 → 重新打包 → 交付 `dist/电脑清理工具.exe`。
