# 本地实时语音运行时

> 2026-08-04 状态：运行时生命周期增强位于 `agent/voice-runtime-integration`，草稿 PR #2。该分支已增加模型进程 supervisor、协议握手检查和逐轮延迟事件，仍需完成受控进程 API 与 Realtime 可靠性测试，暂不合并。

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

## 运行档位与模型配置

Core 的 `ModelManager` 只校验已配置的模型服务和目标机资源，不会下载权重、启动
模型进程或把不可达服务标记为可用。通过以下环境变量让 Core 与语音启动参数保持一致：

```powershell
$env:XINYU_RUNTIME_PROFILE = "quality_local"
$env:XINYU_STT_MODEL = "large-v3-turbo"
$env:XINYU_TTS_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
```

- `safe_fallback`：默认开发档，不要求语音或模型，运行状态会明确显示降级。
- `quality_local`：面向 16GB 目标机的本地档；需要 LLM 和语音 Realtime 地址，TTS 固定 0.6B 预算。
- `quality_cloud_llm`：仍要求外部 OpenAI-compatible LLM 地址，但可在人工基准后尝试 1.7B TTS；不得在实时口型同时常驻时宣称满足 16GB 预算。

`GET /v1/runtime/status` 返回不含地址、路径和密钥的 `model_plan`，包括档位、显存预算、组件状态、最近健康检查时间和稳定错误码。LLM 会请求 OpenAI-compatible `/models`，语音会执行 WebSocket `101` 握手；仅端口打开不会显示为 ready。模型服务断开后，文本功能和记忆功能继续可用。

Core 还提供不依赖具体模型实现的进程生命周期接口。每个模型进程可以处于
`starting / running / stopping / stopped / failed`，异常退出只标记自己的组件，调用方
可以单独 `restart`；停止有超时和 kill 回退。开发机测试使用假进程，Core 不会因配置了模型
ID 就自动拉取或启动权重。

可管理进程必须由本机环境提前注册，值是不会经过 shell 的 JSON 参数数组：

```powershell
$env:XINYU_LLM_PROCESS_COMMAND_JSON = '["C:\\xinyu\\llama-server.exe", "--model", "C:\\models\\companion.gguf"]'
$env:XINYU_SPEECH_PROCESS_COMMAND_JSON = '["C:\\xinyu\\.venv-voice\\Scripts\\speech-to-speech.exe", "--port", "8766"]'
```

未配置时进程列表为空，Core 不会猜测可执行文件位置。HTTP 端只接受已注册的组件 ID，
不接受任意命令字符串，也不会在状态、事件或错误中返回命令、文件路径和密钥：

```text
GET  /v1/models/processes
POST /v1/models/processes/{component_id}/start
POST /v1/models/processes/{component_id}/stop
POST /v1/models/processes/{component_id}/restart
```

同一组件的操作按异步锁串行执行；重复 start/stop 幂等，并发 start 只会创建一个子进程。
启动超时、异常退出和停止 kill 失败使用稳定错误码，其他组件与文字服务不受影响。

Realtime 代理保留上游文本和二进制帧，并在应用事件流发布 `voice.latency`：
`vad_ms`、`final_transcript_ms`、`first_token_ms`、`first_audio_ms`、`complete_ms` 和
`interrupted_ms`。指标带有稳定的会话 ID 和逐轮 turn ID；`turn_interruptions` 是当前轮
打断次数，`interruptions` 是会话累计打断次数。每轮新输入、插话或新响应都会清空上一轮
里程碑，但不会保存音频或对话正文。上游断线会发送可恢复错误，文字聊天、记忆和计划服务
不受影响。

Core 中继的每个方向使用 64 帧有界队列（可由测试传入更小的上限）；慢客户端或上游会
自然形成背压，队列不会无限增长。客户端断开、上游半关闭或协议异常时会取消剩余任务并
释放上游连接。用户新输入、`response.cancelled` 或 `response.interrupted` 到达时，会丢弃
尚未发送的二进制音频帧以及 Realtime 协议的 JSON 音频增量，再保留并转发转写与取消事件；正在播放的帧由上游/客户端协议自行结束。

## 启动

先启动一个 OpenAI-compatible 本地 LLM 服务，例如监听 `http://127.0.0.1:8080/v1`，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-voice.ps1 `
  -LlmBaseUrl "http://127.0.0.1:8080/v1" `
  -LlmModel "<本地服务中的模型 ID>" `
  -TtsModel "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" `
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

另一台电脑不需要下载大型模型即可继续完成 tracker、进程控制、假 WebSocket、断线、背压、插话和资源清理测试。完整任务见 [另一台电脑功能开发计划](OTHER_PC_FUNCTION_PLAN.md)。人物与场景不属于该分支。
