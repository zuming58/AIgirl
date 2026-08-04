# 心屿 XINYU

心屿是一款“本地优先”的陪伴式桌面智能体。项目目标不是只做一个聊天窗口，而是把低延迟语音交互、长期记忆、个人计划和可呼吸的数字角色整合成一个温暖、安静、可长期相处的桌面空间。

> 当前仓库处于可运行的本地应用骨架阶段：16:9 桌面 UI、Core API、SQLite 记忆与计划、提醒收件箱、备份恢复、Tauri 桌面壳和 Realtime 语音网关已经连通；本地语音/语言模型权重、动态人物素材和签名安装包仍需后续验收。

![心屿主界面](docs/assets/xinyu-moment-1920x1080.png)

## 当前可以体验的内容

- 16:9 沉浸式陪伴主界面，支持 1366×768 与 1920×1080 等桌面尺寸
- “此刻 / 对话 / 回忆 / 计划 / 更多”导航与页面切换
- 可多选本机歌单的真实音乐播放器、语音输入胶囊、心情状态、点滴卡片和明日清单
- 水晶心 Logo 与心跳动效
- 对话、可追溯结构化记忆、可编辑计划、到点提醒、心情和设置的本地 SQLite 持久化
- 可替换的对话与 embedding Provider、FTS5 + sqlite-vec 混合召回、可管理的对话摘要
- 运行状态页、JSON v1/v2 导入导出、数据库快照/恢复与二次确认清除
- Tauri 托盘、通知、开机启动、品牌图标和自动封装的 Python Core sidecar
- 显式麦克风权限与设备选择、Realtime 双向语音代理、增量播放/插话状态和最终转写持久化
- FastAPI / Repository 测试、Vite 构建和站点 Worker 测试

更多页面效果：

![心屿功能页面](docs/assets/xinyu-feature-pages.png)

## 技术路线

| 层级 | 当前选择 | 用途 |
| --- | --- | --- |
| UI 原型 | React 19 + Vite 6 | 快速验证桌面界面与交互 |
| 桌面容器 | Tauri 2（已建立工程） | 无边框窗口、托盘、通知、开机启动与 Core sidecar |
| 实时语音 | Hugging Face `speech-to-speech`（子模块） | VAD → STT → LLM → TTS 的低延迟流水线 |
| 智能体服务 | Python 3.11 + FastAPI | 会话编排、Provider 路由、状态与事件管理 |
| 长期记忆 | SQLite + FTS5 + sqlite-vec | 用户事实、来源、混合召回、摘要与用户管理 |
| 本地模型 | 可插拔 STT / LLM / TTS（计划） | 根据显存和隐私需求切换模型 |
| 动态人物 | 写实状态视频库 + LivePortrait + MuseTalk 局部口型 | 以高质量模式实现眨眼、呼吸、视线、表情与音画同步 |

详细选型与取舍见 [技术栈说明](docs/TECH_STACK.md) 和 [技术可行性与开发文档](docs/architecture/心屿-本地陪伴式智能体-技术可行性与开发文档.md)。

## 仓库结构

```text
AIgirl/
├─ apps/
│  └─ desktop-ui/             # React/Vite 桌面界面
├─ services/
│  └─ core/                   # FastAPI、SQLite、Provider 与测试
├─ docs/
│  ├─ architecture/           # 原始蓝图与完整技术可行性文档
│  ├─ design/                 # 页面规划、设计还原与验收记录
│  ├─ DEVELOPMENT.md          # 开发环境、模块边界和调试流程
│  ├─ TECH_STACK.md           # 技术栈与版本策略
│  └─ ROADMAP.md              # 分阶段路线图
├─ scripts/                   # 初始化、完整启动与自动验证脚本
└─ third_party/
   └─ speech-to-speech/       # Hugging Face 上游项目（Git 子模块）
```

## 在新电脑上启动

### 1. 准备环境

- Git 2.40+
- Node.js 20 LTS 或 22 LTS
- npm 10+
- Python 3.11 与 `uv`
- 后续接入语音服务时再安装 FFmpeg 与相应 CUDA 环境

### 2. 克隆完整工程

```powershell
git clone --recurse-submodules https://github.com/zuming58/AIgirl.git
cd AIgirl
git switch --track origin/agent/xinyu-desktop-foundation
.\scripts\setup.ps1
```

`main` 目前仍是早期稳定基线；当前完整开发内容和交接资料位于 `agent/xinyu-desktop-foundation`。另一台电脑继续语音/runtime 时改为切换 `origin/agent/voice-runtime-integration`，并遵循 `docs/OTHER_PC_FUNCTION_PLAN.md`。

如果普通克隆时忘记拉子模块：

```powershell
git submodule update --init --recursive
```

### 3. 启动本地应用

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Open
```

浏览器默认打开 `http://127.0.0.1:4173`，Core API 位于 `http://127.0.0.1:8765`。

### 4. 构建与测试

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

## 文档入口

- [开发手册](docs/DEVELOPMENT.md)：从新电脑初始化到模块接入
- [完整开发交接文档](完整开发交接文档.md)：给跨电脑接手开发者的单一入口、主机配置与下一阶段任务
- [另一台电脑功能开发计划](docs/OTHER_PC_FUNCTION_PLAN.md)：语音/runtime 分支、禁止范围、提交顺序、验收和合并办法
- [交接资料清单](docs/MATERIALS_MANIFEST.md)：本机资料的 GitHub 位置、旧目录处理和隐私/构建排除项
- [实现状态矩阵](docs/IMPLEMENTATION_STATUS.md)：已实现、部分实现、人工门和验证证据
- [技术栈说明](docs/TECH_STACK.md)：当前实现、目标架构与替代方案
- [本地实时语音运行时](docs/VOICE_RUNTIME.md)：speech-to-speech 隔离环境、启动与人工门
- [隐私与数据说明](docs/PRIVACY.md)：本地存储、网络流向、权限和用户控制
- [人物资产规范](docs/AVATAR_ASSETS.md)：高质量状态视频的目录、编码和验收门
- [产品路线图](docs/ROADMAP.md)：从 UI Demo 到本地实时陪伴智能体
- [页面与交互规划](docs/design/页面与交互规划.md)：对话、回忆、计划和动态人物
- [UI 设计验收记录](docs/design/UI-设计还原与验收记录.md)
- [完整技术可行性与开发文档](docs/architecture/心屿-本地陪伴式智能体-技术可行性与开发文档.md)
- [原始架构蓝图](docs/architecture/原始架构蓝图.md)
- [参与开发](CONTRIBUTING.md)

## 项目边界与许可

`third_party/speech-to-speech` 是指向 Hugging Face 官方仓库的 Git 子模块，沿用其独立许可证和提交历史；本仓库不会把上游源码冒充为自有代码。生成式图片和演示文案目前仅用于产品原型，正式商用前需要完成素材来源、肖像权与模型许可证审查。

本仓库暂未授予开源许可证。除各第三方组件按其自身许可证使用外，其他内容默认保留全部权利。
