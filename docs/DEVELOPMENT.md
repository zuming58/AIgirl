# 开发手册

本文描述当前仓库已经可以运行的开发链路。尚未安装的模型、桌面容器和人物运行时会在界面中明确显示为“降级”或“未安装”，不会伪装成可用。

## 1. 环境要求

- Windows 11
- Git 2.40+
- Node.js 20 LTS 或 22 LTS
- npm 10+
- Python 3.11
- `uv`（在缺少 `.venv` 时创建 Python 3.11 环境）

FFmpeg、CUDA、Rust、STT / TTS / LLM 和人物模型不属于当前基础启动的硬依赖。进入语音、Tauri 和人物阶段时再按性能基准安装。

## 2. 初始化

```powershell
git clone --recurse-submodules https://github.com/zuming58/AIgirl.git
cd AIgirl
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

初始化脚本会：

1. 固定并拉取 Git 子模块；
2. 创建仓库级 `.venv`；
3. 以可编辑模式安装 `services/core` 和测试依赖；
4. 使用锁文件安装 React UI 依赖。

## 3. 启动完整本地开发栈

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Open
```

默认地址：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| Desktop UI | `http://127.0.0.1:4173` | React 开发界面 |
| Core API | `http://127.0.0.1:8765` | 对话、记忆、计划、人格、设置和数据管理 |
| OpenAPI | `http://127.0.0.1:8765/docs` | 本地接口调试 |
| App events | `ws://127.0.0.1:8765/v1/app/events` | 运行状态和业务事件 |

`dev.ps1` 会同时管理 UI 与 Core 生命周期，按 `Ctrl+C` 后停止本次启动的 Core 进程。运行数据默认位于 `temp/runtime/`，不进入 Git。

## 4. 自动验证

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

该脚本依次执行：

- FastAPI / SQLite 仓储与接口测试；
- Python 覆盖率报告；
- Vite 生产构建；
- Sites Worker 测试；
- `git diff --check`。

也可以单独运行：

```powershell
.\.venv\Scripts\python.exe -m pytest services\core --cov=xinyu_core --cov-report=term
npm --prefix apps\desktop-ui run build
npm --prefix apps\desktop-ui run test:sites
```

### Tauri 桌面壳

桌面工程位于 `apps/desktop-ui/src-tauri`。当前已包含无边框窗口控制、系统托盘、通知、开机启动插件与最小 capability。查看环境：

```powershell
cd apps\desktop-ui
npm run tauri:info
```

Core 会在 Tauri 构建前由 PyInstaller 自动封装为 sidecar，安装版不要求最终用户安装 Python。也可以单独验证封装：

```powershell
npm --prefix apps\desktop-ui run sidecar:build
```

产物写入被 Git 忽略的 `apps/desktop-ui/src-tauri/binaries/`，Tauri 按目标三元组打包。桌面壳启动时若 `127.0.0.1:8765` 已有 Core 会复用，否则启动 sidecar；退出应用时停止由本次启动的 Core。封装后的可执行文件已在独立端口通过 `/health` 健康检查。

安装 Rust stable MSVC 后可运行：

```powershell
npm run tauri:dev
npm run tauri:build
```

本机当前缺少 Rust/Cargo，因此 Web 模式和 Core 可完整开发、构建与测试，Tauri 原生编译属于环境门，不在脚本中自动修改系统。

## 5. 当前代码结构

```text
apps/desktop-ui/
├─ src/App.jsx                 # 当前五个功能页和业务交互
├─ src/services/coreApi.js     # Core API / WebSocket 适配器
├─ src/services/desktopBridge.js # Tauri 与网页安全回退
├─ src/services/speechClient.js  # 上游 Realtime 客户端与麦克风释放适配
├─ src/styles.css              # 16:9 桌面布局和组件视觉
├─ public/assets/              # 原型场景、Logo 和卡片素材
└─ src-tauri/                  # 桌面壳、托盘、品牌图标和 sidecar 生命周期

services/core/
├─ src/xinyu_core/app.py       # FastAPI 路由和事件入口
├─ src/xinyu_core/contracts.py # Pydantic 请求、响应和事件契约
├─ src/xinyu_core/database.py  # SQLite 连接、WAL 和迁移
├─ src/xinyu_core/repository.py# 数据访问
├─ src/xinyu_core/services.py  # 对话与记忆编排
├─ src/xinyu_core/providers.py # 开发回退和 OpenAI-compatible LLM
├─ src/xinyu_core/avatar.py    # 人物状态机与高质量视频资产探测
├─ src/xinyu_core/reminders.py # 安静时段、到点提醒和持久化收件箱
└─ tests/                      # API 与仓储回归测试
```

`App.jsx` 仍偏大。后续在功能稳定后按 `conversation / memory / planning / companion / music / settings` 拆分，避免在接口仍快速变化时做无收益的机械重构。

## 6. Core 配置

Core 只监听回环地址。可通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `XINYU_DATA_DIR` | 用户本地应用数据目录 | SQLite 和运行数据位置 |
| `XINYU_AUTH_TOKEN` | 空 | 可选本机 Bearer Token |
| `XINYU_LLM_BASE_URL` | 空 | OpenAI-compatible 本地或受控服务地址 |
| `XINYU_LLM_MODEL` | 空 | 模型 ID |
| `XINYU_LLM_API_KEY` | 空 | Provider 密钥；不得提交到 Git |
| `XINYU_SPEECH_REALTIME_URL` | 空 | speech-to-speech Realtime 地址，例如 `ws://127.0.0.1:8766/v1/realtime` |

未配置 LLM 时使用可识别的 `development-fallback` 回复，仅用于验证全链路，不冒充真实模型能力。

## 7. 已实现接口

- `GET /health`
- `GET /v1/runtime/status`
- `GET /v1/system/capabilities`
- `GET /v1/diagnostics`
- `GET /v1/models`
- `GET /v1/avatar/status`
- `GET /v1/avatar/assets/{state}`
- `POST /v1/avatar/state`
- `POST /v1/chat`
- `GET /v1/conversations`
- `GET /v1/conversations/{session_id}/messages`
- `POST /v1/memories`
- `POST /v1/memories/query`
- `GET /v1/memories/{id}/context`
- `PATCH / DELETE /v1/memories/{id}`
- `GET / POST /v1/plans`
- `PATCH / DELETE /v1/plans/{id}`
- `GET /v1/notifications`
- `POST /v1/notifications/{id}/acknowledge`
- `GET / PUT /v1/persona`
- `GET /v1/mood/current`
- `POST /v1/mood`
- `GET /v1/settings`
- `PUT /v1/settings/{key}`
- `POST /v1/voice/session`
- `POST /v1/voice/transcripts`
- `GET /v1/data/export`
- `POST /v1/data/import`
- `GET / POST /v1/data/backups`
- `POST /v1/data/backups/{name}/restore`
- `DELETE /v1/data`
- `WS /v1/app/events`
- `WS /v1/realtime/voice`

语音会话接口会先报告独立运行时是否可达。可达时，
`WS /v1/realtime/voice` 双向代理上游 Realtime 帧；不可达时返回可恢复的
诚实降级事件，前端不会申请麦克风权限。最终转写通过
`POST /v1/voice/transcripts` 幂等写入对应语音会话。生产构建会从固定的
`speech-to-speech` 子模块注入两个 AudioWorklet 到 `dist/client/worklets/`。

## 8. 数据与迁移

SQLite 采用 WAL，迁移位于 `services/core/src/xinyu_core/migrations/`。当前包含：

- 人格与版本；
- 会话、消息和回合；
- 结构化记忆、来源、关系边与 FTS5；
- 心情状态；
- 计划、承诺和工具运行；
- 主动事件、媒体资产、设置和模型注册表。

自动记忆仅处理用户明确要求记住的高置信表达。用户可以主动添加、查看来源消息、理解“为什么记得”、编辑、置顶和删除；同槽新事实会保留替代关系，未确认且未收藏的系统推断 180 天后过期。完整数据可以导入/导出。数据库快照经过 SQLite 完整性和版本校验，恢复、导入和清除都带确认步骤，导入或清除前会先创建安全快照。

温柔问候默认只在用户已有互动且约 4 小时未交流时评估；遵守
`privacy.quiet_hours`，同类问候冷却 4 小时且每日最多 2 次。全局主动陪伴和
`proactive.checkin_enabled` 任一关闭都会禁止该问候。计划提醒不占问候额度。

高质量人物状态视频放在运行数据目录
`avatar/xinyu-main/{idle,listening,thinking,speaking,smiling,goodnight}.mp4`。
`idle / listening / thinking / speaking` 四个必需状态齐全后 Core 才会把渲染器
标记为 `video_state_library`；UI 随状态切换视频并在首帧可播放前保留静态背景。
详细验收规格见 [人物资产规范](AVATAR_ASSETS.md)。

诊断报告只返回版本、健康状态、记录数量、运行组件、硬件概况和非敏感开关，
不返回消息/记忆正文、数据目录、麦克风设备 ID 或密钥。隐私边界见
[隐私与数据说明](PRIVACY.md)。

## 9. 人工确认边界

以下工作不能自动替用户做最终决定：

- 下载体积较大的模型与选择显存档位；
- 授权真人肖像、角色资产和声音克隆；
- 麦克风、系统通知和开机启动权限；
- 第三方模型、图片、音乐与字体的商用许可审核；
- Windows 代码签名、发布账号和线上密钥；
- 最终人物审美、声音和主动陪伴频率验收。

这些项目会保留成明确的验收门，不阻塞接口、回退路径、测试和无授权部分的继续开发。

## 10. 子模块更新

```powershell
git submodule status
```

更新上游时固定到经过验证的提交，并记录许可证、更新原因和回归结果：

```powershell
cd third_party\speech-to-speech
git fetch origin
git checkout <经过验证的提交>
cd ..\..
git add third_party\speech-to-speech
```

完整覆盖情况见 [实现状态矩阵](IMPLEMENTATION_STATUS.md)。
