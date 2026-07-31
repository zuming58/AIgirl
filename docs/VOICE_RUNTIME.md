# 本地实时语音运行时

心屿复用 Hugging Face `speech-to-speech` 的 OpenAI Realtime-compatible WebSocket，而不是重新实现一套私有音频协议。Core 通过 `XINYU_SPEECH_REALTIME_URL` 检测独立语音进程；语音进程崩溃不会拖垮文字对话、记忆和计划。

## 当前已完成

- `speech-to-speech` 作为固定提交的 Git 子模块；
- Core 的语音会话协商接口；
- `/v1/realtime/voice` 到独立 Realtime 进程的双向文本/二进制代理；
- 未配置或不可达时保持诚实降级，不申请麦克风权限；
- 前端直接复用上游 WebSocket 客户端、PCM16 AudioWorklet、VAD 状态和插话清空逻辑；
- 麦克风枚举、显式权限检测、输入设备持久化、回声消除、降噪与自动增益；
- 用户/助手最终转写幂等写入 SQLite，会话刷新后仍可查看；
- 语音中的用户明确记忆表达进入与文字对话相同的可追溯记忆链路；
- 停止会话或异常时关闭 AudioContext、WebSocket 并释放所有麦克风轨道；
- `listening / thinking / speaking / idle` 状态驱动人物状态机；
- 独立上游 Realtime 地址与端口探测；
- STT / TTS 运行状态进入模型注册表和设置页；
- 独立 `.venv-voice` 安装脚本与启动脚本；
- 未配置、格式错误、服务未监听、真实代理、转写幂等和记忆提取的自动测试。

## 浏览器与 Core 数据流

```text
麦克风
  → AudioWorklet（16 kHz PCM16、噪声门）
  → UI Realtime Client
  → ws://127.0.0.1:8765/v1/realtime/voice
  → Core 双向代理
  → speech-to-speech Realtime
  → 增量音频 / 增量转写
  → AudioWorklet 播放 + 最终转写落库
```

Core 会先通过端口探测确认上游可达；真正的协议握手和错误仍由 Realtime
连接负责。UI 只在用户点击语音按钮后调用 `getUserMedia`，打开设置页不会
静默占用麦克风。

## 为什么使用独立进程

- PyTorch、CUDA、STT 和 TTS 依赖不会污染 Core 的轻量环境；
- 显存不足或模型崩溃时，文字功能仍然可用；
- 语音进程可以按需启动和退出；
- 便于记录 VAD、STT、LLM、TTS 各段延迟；
- 后续可以把语音运行时放到另一台局域网机器。

## 16GB 高质量档建议

当前机器自动检测为 RTX 4070 Ti SUPER 16GB：

| 模块 | 首轮基准候选 | 原因 |
| --- | --- | --- |
| VAD | Silero VAD v5 | 上游内置、轻量 |
| 中文 STT | Faster Whisper `large-v3-turbo` | 中文覆盖与 Windows/CUDA 生态更稳 |
| LLM | 独立 llama.cpp 4B–8B GGUF | 控制 KV cache，并与语音进程解耦 |
| TTS | Qwen3-TTS CustomVoice | 不需要未经授权的声音克隆 |
| 协议 | Realtime WebSocket | 支持转写增量、音频增量和取消 |

模型最终选择必须以本机基准为准。人物口型运行时加入后，需要重新测量并发显存，不能只看单模型速度。

## 安装门

语音依赖包含 PyTorch 等大型包，模型权重还涉及下载量和许可证，因此基础 `setup.ps1` 不会静默安装。确认后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-voice.ps1 -ConfirmLargeInstall
```

该脚本只安装隔离环境和程序依赖，不主动下载 STT / TTS 权重。首次真正启动所选模型时，上游运行时可能下载权重。

## 启动

先启动一个 OpenAI-compatible 本地 LLM 服务，例如监听 `http://127.0.0.1:8080/v1`，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-voice.ps1 `
  -LlmBaseUrl "http://127.0.0.1:8080/v1" `
  -LlmModel "<本地服务中的模型 ID>" `
  -Speaker "<验收后的内置声音>"
```

语音服务默认监听：

```text
ws://127.0.0.1:8766/v1/realtime
```

启动 Core 前设置：

```powershell
$env:XINYU_SPEECH_REALTIME_URL = "ws://127.0.0.1:8766/v1/realtime"
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Open
```

## 仍需人工确认

- 实际下载哪个 STT / TTS / LLM 权重；
- 内置女声的审美验收；
- 若使用声音克隆，必须有声音权利与本人同意；
- 麦克风系统权限；
- 模型许可证和商用范围。

这些人工门不影响协议、状态检测、降级、测试和 UI 继续开发。

## 已知验证边界

当前自动测试覆盖代理协议、降级、转写持久化和构建资产；完整的声学验收仍
需要人工选择并下载模型后，在真实麦克风与扬声器上测量首包延迟、插话停止
时间、回声和连续 30 分钟稳定性。没有这些结果时，文档不会宣称达到目标延迟。
