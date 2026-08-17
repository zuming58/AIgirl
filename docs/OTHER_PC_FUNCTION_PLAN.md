# 另一台电脑功能开发计划

更新日期：2026-08-04

适用仓库：`https://github.com/zuming58/AIgirl`

唯一工作分支：`agent/voice-runtime-integration`

现有草稿 PR：<https://github.com/zuming58/AIgirl/pull/2>

## 1. 分工结论

另一台电脑只开发“不依赖最终人物审美和 RTX 4070 Ti SUPER 实机验收”的功能链路：实时语音协议、模型进程管理、运行状态、错误恢复、记忆/计划的功能接口和自动测试。

以下内容明确留在主开发电脑，另一台不要修改：

- 女主人物形象、脸型、马尾、服装和性感/青春程度；
- 房间、桌面物件、灯光、构图和人物位置；
- Logo、主场景、顶部胶囊和底部交互坞的视觉调整；
- LivePortrait / MuseTalk 资产生产、状态视频和口型最终验收；
- `apps/desktop-ui/public/assets/` 中人物与场景资源；
- `apps/desktop-ui/src/App.jsx` 和 `src/styles.css` 中与主场景视觉有关的改动；
- `services/core/src/xinyu_core/avatar.py` 与 `docs/AVATAR_ASSETS.md`。

如果功能开发必须触及 UI，只允许修改设置页、运行状态页、错误提示和语音控制状态；不得重排主场景。

## 2. 接手命令

```powershell
git clone --recurse-submodules https://github.com/zuming58/AIgirl.git
cd AIgirl
git fetch origin
git switch --track origin/agent/voice-runtime-integration
git pull --ff-only
git rev-parse HEAD
```

首次接手时应看到或包含提交：

```text
c76b45f7f3c79c5fb74de5981a365cd7bd2e9de1
```

如果本地已经有仓库：

```powershell
git status -sb
git fetch origin
git switch agent/voice-runtime-integration
git pull --ff-only
git submodule update --init --recursive
```

开始前工作区必须干净。不得使用 `git reset --hard` 清除未知改动，也不得强制推送。

## 3. 当前代码已经做到什么

`c76b45f` 已完成：

- speech-to-speech Realtime WebSocket 的 Core 双向代理；
- 文本与二进制帧转发、语音事件和基础延迟指标；
- 模型进程 `start / stop / restart / failure` 生命周期抽象；
- 模型进程失败隔离和 Core 退出时清理；
- speech、LLM 健康检查与短时缓存；
- 模型状态和生命周期事件；
- 语音及模型管理新增测试 12 项通过；
- 没有下载模型、没有改人物、没有改主 UI。

这仍是“运行时基础”，不是已经能像真人一样实时说话。真实 STT、LLM、TTS 权重尚未选择和下载，声音、麦克风、回声、显存和延迟也没有完成实机验收。

## 4. 第一优先级：修复 PR #2 的合并阻塞项

### 问题

`VoiceLatencyTracker` 目前在整个 WebSocket 会话中只创建一次，而且每类 milestone 只写入第一次。多轮对话时，第二轮会继续上报第一轮的 `vad_ms / first_token_ms / first_audio_ms / complete_ms`。

相关位置：

- `services/core/src/xinyu_core/app.py`：创建会话级 tracker；
- `services/core/src/xinyu_core/speech.py`：首次写入后不覆盖；
- `services/core/tests/test_speech.py`：需要新增两轮回归。

### 要求

1. 明确区分 `session` 与 `turn`；每轮语音输入或 `response.created` 开始新的 turn。
2. 每轮分别计算 VAD、最终转写、首 token、首音频、完成和打断延迟。
3. 保留会话 ID、turn ID 和累计打断次数，但不得保存音频或对话正文到指标。
4. 连续模拟两轮事件，断言第二轮所有毫秒值都以第二轮起点计算。
5. 乱序、取消、只文本回复、断线时不抛未处理异常。

### 验收

```powershell
.\.venv\Scripts\python.exe -m pytest services\core\tests\test_speech.py -q
```

新增测试必须能在旧实现上失败、在修复后通过。提交建议：

```text
fix(voice): reset latency metrics per turn
```

## 5. 第二优先级：把模型进程基础变成可操作运行时

当前 `ModelProcessSupervisor` 有生命周期对象，但没有完整的安全控制面。继续完成：

1. 为同一进程的并发 `start / stop / restart` 加 `asyncio.Lock`，避免重复拉起。
2. 增加受控的进程注册配置；命令只能来自本地配置，不接受任意 HTTP 命令字符串。
3. 增加模型进程查询、启动、停止、重启接口；只允许已注册组件 ID。
4. 增加启动超时、优雅停止、超时 kill、退出码、最近错误码和重启次数。
5. stdout/stderr 只写脱敏日志，API 不返回路径、Token、用户文本或完整命令行密钥。
6. Core 退出时全部清理；某一个模型失败不得影响文字、记忆、计划和其他模型。
7. 所有状态变化通过 `/v1/app/events` 发布稳定事件。

建议接口：

```text
GET  /v1/models/processes
POST /v1/models/processes/{component_id}/start
POST /v1/models/processes/{component_id}/stop
POST /v1/models/processes/{component_id}/restart
```

接口命名可以调整，但必须补 Pydantic 契约、OpenAPI、权限/本机边界和测试。

### 验收

- 并发两次 start 只产生一个子进程；
- 假进程异常退出只把自身标记为 failed；
- restart 后 PID/状态正确变化；
- stop 超时会 kill；
- Core shutdown 不遗留子进程；
- 未注册 ID、重复操作和非法状态返回稳定错误码。

提交建议：

```text
feat(runtime): expose safe model process controls
```

## 6. 第三优先级：实时语音可靠性，不下载大型模型

低配笔记本可以使用假上游 WebSocket 完成以下工程工作：

1. 为 voice session 增加稳定 session/turn 关联和结构化错误码。
2. 覆盖上游未启动、握手不是 101、连接中断、半关闭、超时和非法 JSON。
3. 增加有界发送队列或等价背压策略，防止慢上游导致内存增长。
4. 用户插话时确认取消事件、播放队列清空和 tracker 状态一致。
5. 关闭页面、停止会话或 Core 退出时释放 WebSocket、AudioContext 和麦克风轨道。
6. 健康检查不得把“端口能连接”误报为“Realtime 协议可用”。
7. 日志和诊断只记录事件类型、耗时、状态和稳定错误码。

不要在笔记本自动下载 Faster-Whisper、Qwen、Qwen3-TTS、LivePortrait 或 MuseTalk 权重。模型真实延迟和显存只在 RTX 4070 Ti SUPER 主机验收。

提交建议：

```text
test(voice): cover reconnect backpressure and interruption
```

## 7. 第四优先级：可并行完成的桌面功能

完成前三项后，如果仍有开发时间，可按以下顺序继续：

1. 安装 Rust stable MSVC 后验证 Tauri `dev/build`、托盘、通知、开机启动和 Core sidecar；没有 Rust 时只补契约和测试，不伪造“已验收”。
2. 给计划提醒补系统通知适配器测试、重复提醒去重和时区/夏令时边界。
3. 给本地音乐补媒体库索引、封面元数据和断开文件后的恢复提示；不提交音乐文件。
4. 给记忆补可重复的 10 万条合成数据基准脚本；真实中文 embedding 准确率仍留到目标机。
5. 给天气、日历定义 Provider 接口和关闭状态；没有用户授权与密钥时不接真实账号。

每一类功能使用单独提交；不要把所有改动揉进一个提交。

## 8. 测试与提交规则

每次推送前：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
git diff --check
git status -sb
```

如果低配电脑无法运行某一项，必须记录“未运行原因”，不能写成通过。禁止提交：

- `.env`、API Key、Token、数据库和日志；
- `.venv*`、`node_modules`、`dist`、模型缓存和权重；
- 麦克风 ID、个人对话、记忆正文和本机绝对数据路径；
- 未授权真人图片、声音、音乐和字体；
- 人物/场景视觉改动。

推送仍使用原分支：

```powershell
git push origin agent/voice-runtime-integration
```

不要创建重复 PR，不要合并 PR #2，不要 force-push。把结果更新到 PR #2：列出提交、测试、未测项和下一步。

## 9. 回到主电脑后的合并方式

主电脑执行：

```powershell
git fetch origin
git switch agent/xinyu-desktop-foundation
git pull --ff-only
git log --oneline origin/agent/xinyu-desktop-foundation..origin/agent/voice-runtime-integration
```

审核顺序：

1. 检查 PR #2 是否只包含 voice/runtime/docs/tests；
2. Core 全量、UI 单测和生产构建；
3. 两轮延迟指标、插话、断线和进程清理专项测试；
4. 确认没有人物/场景改动、模型权重、密钥或私人数据；
5. 通过后把 PR 从 Draft 改为 Ready，再合并到 `agent/xinyu-desktop-foundation`；
6. 最后由 PR #1 统一进入 `main`，发布前仍需人物、声音、模型许可证和安装包人工验收。

## 10. 可直接发给另一台电脑的任务提示

```text
请继续开发 GitHub 仓库 zuming58/AIgirl 的 agent/voice-runtime-integration 分支，现有草稿 PR 是 #2。先阅读 docs/OTHER_PC_FUNCTION_PLAN.md、完整开发交接文档.md、docs/VOICE_RUNTIME.md 和 docs/IMPLEMENTATION_STATUS.md。

第一步必须修复 VoiceLatencyTracker 在多轮 WebSocket 会话中沿用首轮延迟数据的问题，补连续两轮回归测试。第二步给 ModelProcessSupervisor 加并发锁、安全进程配置与受控 start/stop/restart API，并补异常退出、停止超时、重复启动和 Core shutdown 测试。第三步用假 WebSocket 完成断线、背压、插话、半关闭和错误码测试。

不要下载大模型，不要修改人物、场景、Logo、主 UI 构图、avatar.py 或人物资产文档；不要提交权重、密钥、数据库、日志和私人数据。每项单独提交，运行 scripts/test.ps1，直接推送原分支并更新 PR #2，不要 force-push，也不要自行合并。
```
