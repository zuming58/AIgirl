# 开发手册

## 1. 新电脑初始化

### 必需环境

- Windows 11（当前主要目标）
- Git 2.40+
- Node.js 20 LTS 或 22 LTS
- npm 10+

克隆时同时取回语音参考项目：

```powershell
git clone --recurse-submodules https://github.com/zuming58/AIgirl.git
cd AIgirl
.\scripts\setup.ps1
```

手动方式：

```powershell
git submodule update --init --recursive
cd apps\desktop-ui
npm ci
npm run dev
```

## 2. UI 开发

```powershell
cd apps\desktop-ui
npm run dev
```

常用命令：

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | 启动热更新开发服务 |
| `npm run build` | 生成生产构建并准备站点输出 |
| `npm run preview` | 本地预览生产构建 |
| `npm run test:sites` | 验证静态站点 Worker |

当前入口：

- `src/App.jsx`：页面结构、演示数据和基础交互
- `src/styles.css`：16:9 自适应布局、玻璃拟态和动效
- `public/assets/`：运行时引用的原型素材

## 3. 页面职责

| 页面 | 产品职责 | 后端能力 |
| --- | --- | --- |
| 此刻 | 陪伴主场景、快速输入、心情与今日摘要 | 当前状态聚合、主动问候 |
| 对话 | 连续对话和会话历史 | 实时语音、LLM、消息存储 |
| 回忆 | 可解释、可管理的长期记忆 | 提取、检索、合并、纠错、删除 |
| 计划 | 用户计划、提醒和共同约定 | 日程工具、任务状态、提醒调度 |
| 更多 | 设置、模型、声音、隐私和数据管理 | Provider 配置、数据导入导出 |

更完整的交互设计见 [页面与交互规划](design/页面与交互规划.md)。

## 4. 推荐模块边界

后续接入真实数据时，按以下边界拆分，避免继续扩大 `App.jsx`：

```text
apps/desktop-ui/src/
├─ app/                 # 路由、全局状态、事件总线
├─ features/
│  ├─ conversation/
│  ├─ memory/
│  ├─ planning/
│  ├─ companion/
│  └─ music/
├─ components/          # 无业务含义的共享组件
├─ services/            # WebSocket、IPC、API 适配
├─ stores/              # 客户端状态
├─ types/               # DTO 与领域类型
└─ styles/
```

服务端建议：

```text
services/agent/
├─ api/                 # FastAPI / WebSocket
├─ orchestration/       # 对话回合、打断和工具调用
├─ providers/           # STT / LLM / TTS 适配器
├─ memory/              # 提取、检索、压缩与遗忘
├─ tools/               # 计划、提醒、音乐等
├─ avatar/              # 表情、口型和动作事件
└─ persistence/         # SQLite 与迁移
```

## 5. 前后端事件协议

实时链路不要只传最终文本。建议统一事件信封：

```json
{
  "id": "evt_01",
  "type": "assistant.audio.delta",
  "session_id": "session_01",
  "timestamp": 1785283200000,
  "payload": {}
}
```

首批事件：

- `user.speech.started`
- `user.speech.stopped`
- `transcript.partial`
- `transcript.final`
- `assistant.thinking`
- `assistant.text.delta`
- `assistant.audio.delta`
- `assistant.audio.stopped`
- `avatar.expression.changed`
- `memory.candidate.created`
- `plan.updated`
- `error`

任何长任务都必须能通过 `session_id` 和 `turn_id` 取消，用户插话时立即停止旧回合的 LLM 输出、TTS 合成和音频播放。

## 6. 本地数据草案

建议首批表：

- `messages`
- `conversations`
- `memories`
- `memory_sources`
- `plans`
- `reminders`
- `relationship_state`
- `settings`

`memories` 至少包含 `kind`、`content`、`confidence`、`importance`、`source_message_id`、`created_at`、`updated_at` 和 `deleted_at`。不能只保存一段无法追溯的摘要。

## 7. 本地模型开发环境

语音阶段再安装：

- Python 3.10/3.11
- FFmpeg
- NVIDIA 驱动与匹配版本的 CUDA（需要 GPU 时）
- 独立虚拟环境

模型权重放入本机 `models/` 或系统缓存目录，不进入 Git。每个 Provider 需要提供健康检查、冷启动耗时、实时系数、首包延迟和显存占用。

## 8. 调试与验收

每次 UI 变更至少检查：

- 1366×768 不遮挡主输入条
- 1920×1080 人物处在视觉中心偏左，右侧卡片不压脸
- 导航可键盘聚焦
- 动效关闭后仍可使用
- 页面切换不丢失演示状态

语音阶段记录：

- VAD 判定耗时
- 最终转写延迟
- LLM 首 token 延迟
- TTS 首音频包延迟
- 端到端首声延迟
- 打断生效时间

## 9. 子模块更新

查看当前固定版本：

```powershell
git submodule status
```

更新上游时不要直接改子模块源码：

```powershell
cd third_party\speech-to-speech
git fetch origin
git checkout <经过验证的提交>
cd ..\..
git add third_party\speech-to-speech
```

提交中必须说明上游提交号、更新原因和回归结果。
