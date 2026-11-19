---
name: desktop-visual-pilot
description: 真机 Windows 桌面的可视化驾驶与交付验收。当用户说"你自己交付并且验收""用起来（指 windows-mcp 类桌面自动化）""我要看着你的操作过程""过程中我能提示""打开某个桌面程序验证 UI 生效""截图验收"时使用。不依赖 MCP 工具注册，直接用 win32gui/PIL 驱动真机；内置 checkpoint 交互（每步截图停下等确认）与 autopilot 全程授权双模式。
agent_created: true
---

# 真机可视化驾驶（Desktop Visual Pilot）

## 用途

在**真实 Windows 桌面**上执行 GUI 操作并**让用户看得见过程、随时能插话**，最后给出客观验收判定。
它绕开一个现实困境：windows-mcp 的 MCP 工具经常注不进会话（工具表在会话启动时固定），
但技能本质只是 Python + UIA/截图——直接用 venv 里的 win32gui/win32api/PIL 驱动真机即可，
无需 MCP 工具注册。

**两条铁律**：
1. 过程可见——关键动作后必须截图并展示，不允许全程黑盒跑完才给结果。
2. 用户可介入——默认每步停下等确认；用户授权后可切全程模式。

## 何时使用

- 用户要"自己交付并验收"某个桌面程序 / EXE / GUI 界面
- 用户说"我在看着你操作""过程中我能提示""别全在后台"
- 需要操作无 API 的老旧 Win32 客户端、钉钉客户端、本地 EXE
- 需要验证"新 UI 是否真的生效"（而非只查源码）

## 环境自举（换电脑后第一步）

运行 `scripts/bootstrap.py --install`（它做的事）：
- 剥代理拉包：本机 curl 坏 + 沙箱代理污染 pypi，`uvx windows-mcp` 会超时 49s。
  必须 `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy UV_NO_PROXY='*'`。
- 找到含 `win32gui/win32api/PIL/comtypes/numpy` 的 venv python（缓存里）。
- 探测 console 会话有真实桌面（截图非黑屏、能枚举到可见窗口）。

把输出的 `python` 路径记为本会话的 `PY`。后续所有脚本都用这个解释器：
```
<PY> <skill>/scripts/drive.py ...
```

**若无 uv/无网**：让用户在其本机会话装 uv（`irm https://astral.sh/uv/install.ps1 | iex`），
沙箱内装不动系统级东西（已知铁律）。

## 核心工作流（checkpoint 交互，默认）

这是本 skill 的灵魂。严格按以下节奏，绝不一口气跑完：

1. **建会话**：`session.py init --workdir <任务目录>`（默认 checkpoint 模式）。
2. **每个关键动作**循环执行：
   a. 用 `drive.py <action> --out <shot.png>` 执行一步（launch/focus/click/type/key…），动作自带截图。
   b. 用 Read 工具打开这个 PNG → **用户能真看见当前画面**。
   c. 用一句话说明"刚做了什么 + 看到什么"，然后停下，等用户回复。
   d. 用户可能：确认继续（"对""继续""下一步"）、改指令（"点错了，点下面那个""改成 XX"）、
       或授权全程（"全程授权""别停了""一口气做完"）。
   e. 用 `session.py step` 记录本步；若用户改了指令，先按新指令调整再执行。
3. **识别全程授权信号**：`全程授权 / 别停了 / 不用停 / 一口气做完 / 自动跑完 / 我自己看着 / you decide`。
   命中 → `session.py mode --mode autopilot`，之后连续执行不再每步停，
   但**关键里程碑（启动完成/切到目标页/出错）仍留截图**，结束时统一汇总。
4. **验收**：用 `verify.py` 做客观判定（非黑屏/尺寸/与基线差异），给出 ✅/❌，别用"我觉得"。

## checkpoint 交互示例（正确姿势）

```
助手：已启动 EXE 并最大化，当前画面 [展示 _01_launch.png]。
      我看到标题"项目工作台"、数据卡片都在。下一步我准备点左侧"合同台账"——
      可以继续吗？或者你要我先点别的？
用户：对，点合同台账
助手：[drive.py click --out _02_ledger.png] → [展示截图] → 已切到合同台账页，
      表头第一列是"承接公司"（新 UI 标志）。要继续导出验收图吗？
用户：全程授权，做完告诉我
助手：[session.py mode --mode autopilot] 收到，接下来我连续执行，关键节点留图，结束汇总。
```

**错误姿势**（禁止）：一条龙跑完所有动作，最后甩一张图和结论——用户看不到过程，
无法中途纠正，这正是要根治的问题。

## 坐标怎么定准（今天踩过的坑）

真机全屏 1920×1080，目测坐标经常偏（曾把 y=432 的"合同台账"点成 y=197 的"任务分派看板"）。
正确做法：
1. 先 `drive.py shot --out cur.png` 截当前画面。
2. `drive.py region --x .. --y .. --w .. --h .. --zoom 4 --out zoom.png` 放大目标区域。
3. Read 看放大图，读清文字的精确位置，再换算回原图坐标（放大 4 倍则 原图y = crop_y + 放大图y/4）。
4. 点击后用 `session.py step` 记录，并截图确认高亮/跳转是否符合预期。

**进程存活坑**：沙箱会随脚本退出清理 Popen 起的 EXE 子进程。两种解法：
- 目标程序已开机自启常驻 → 直接 focus 即可，最稳。
- 否则在**同一个 drive.py batch**（`batch --file actions.json`）里完成 launch+操作+截图；
  或单命令 launch 后立刻连续 focus/click，别让中间空档太久。

## 动作速查（drive.py）

| action | 关键参数 | 说明 |
|---|---|---|
| windows | --filter | 枚举可见窗口（标题/类名/hwnd） |
| shot | --out [--x --y --w --h --zoom] | 全屏或区域截图 |
| launch | --exe --title_kw --wait --maximize | 启动并等窗口出现 |
| focus | --title --maximize | 激活/最大化窗口 |
| click / dblclick | --x --y [--out --wait] | 左/右双击，可选点击后等待+截图 |
| move / drag / scroll | --x.. / --clicks | 鼠标移动/拖拽/滚轮 |
| type | --text | 剪贴板粘贴（支持中文），非逐字符 |
| key | --keys "ctrl,shift,esc" | 组合键 |
| region | --x --y --w --h --zoom --out | 放大截图用于读字定位 |
| batch | --file --outdir | 多动作一次跑（autopilot 用） |

## 验收判定（verify.py）

- `--not-black`：证明截到真实桌面，不是 session0 黑屏。
- `--expect-size W H`：分辨率符合预期。
- `--baseline before.png --template-diff 0.5`：界面变化超过阈值（验证新 UI 生效）。
- GUI 语义验收（如表头文字）仍需**人眼 look 截图**或 OCR；本 skill 不内置 OCR，避免重依赖。

## 已知边界

- 无显示器 / session0：截图全黑 → bootstrap 会报 black=true，此时桌面自动化不可用。
- 纯 headless 服务/API 任务别用本 skill，直接 HTTP/脚本更快。
- 坐标点击在 DPI 缩放/多屏下会漂移 → 永远先截图放大定位，别硬编码。
- `windows-mcp-control` 技能是 MCP 工具版；本 skill 是其"工具注不进时的平替实现"，两者互补。

## 换电脑迁移

整个目录自包含。拷到 `~/.workbuddy/skills/desktop-visual-pilot/` 即可。
首次运行 `bootstrap.py --install` 重建 venv（需联网拉包）。
若已上传 GitHub：`git clone <repo> ~/.workbuddy/skills/desktop-visual-pilot`。
