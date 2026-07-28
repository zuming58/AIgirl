# 心屿 XINYU

心屿是一款“本地优先”的陪伴式桌面智能体。项目目标不是只做一个聊天窗口，而是把低延迟语音交互、长期记忆、个人计划和可呼吸的数字角色整合成一个温暖、安静、可长期相处的桌面空间。

> 当前仓库处于产品原型阶段：16:9 桌面 UI Demo 已可运行，“此刻 / 对话 / 回忆 / 计划 / 更多”页面可交互；实时语音、LLM、记忆服务和动态人物尚未接入生产链路。

![心屿主界面](docs/assets/xinyu-moment-1920x1080.png)

## 当前可以体验的内容

- 16:9 沉浸式陪伴主界面，支持 1366×768 与 1920×1080 等桌面尺寸
- “此刻 / 对话 / 回忆 / 计划 / 更多”导航与页面切换
- 音乐播放器、语音输入胶囊、心情状态、点滴卡片和明日清单
- 水晶心 Logo 与心跳动效
- 对话列表、记忆时间线、计划看板的前端交互原型
- Vite 构建、静态预览和站点 Worker 测试

更多页面效果：

![心屿功能页面](docs/assets/xinyu-feature-pages.png)

## 技术路线

| 层级 | 当前选择 | 用途 |
| --- | --- | --- |
| UI 原型 | React 19 + Vite 6 | 快速验证桌面界面与交互 |
| 桌面容器 | Tauri 2（计划） | Windows 桌面打包、托盘、原生能力与较低资源占用 |
| 实时语音 | Hugging Face `speech-to-speech`（子模块） | VAD → STT → LLM → TTS 的低延迟流水线 |
| 智能体服务 | Python + FastAPI（计划） | 会话编排、工具调用、状态管理 |
| 长期记忆 | SQLite + FTS5 + 向量检索（计划） | 用户事实、事件、关系和语义回忆 |
| 本地模型 | 可插拔 STT / LLM / TTS（计划） | 根据显存和隐私需求切换模型 |
| 动态人物 | 2.5D 分层呼吸动效 → Live2D → 音频驱动肖像（分阶段） | 眨眼、呼吸、视线、表情与口型 |

详细选型与取舍见 [技术栈说明](docs/TECH_STACK.md) 和 [技术可行性与开发文档](docs/architecture/心屿-本地陪伴式智能体-技术可行性与开发文档.md)。

## 仓库结构

```text
AIgirl/
├─ apps/
│  └─ desktop-ui/             # 当前可运行的 React/Vite UI Demo
├─ docs/
│  ├─ architecture/           # 原始蓝图与完整技术可行性文档
│  ├─ design/                 # 页面规划、设计还原与验收记录
│  ├─ DEVELOPMENT.md          # 开发环境、模块边界和调试流程
│  ├─ TECH_STACK.md           # 技术栈与版本策略
│  └─ ROADMAP.md              # 分阶段路线图
├─ scripts/                   # 新电脑初始化脚本
└─ third_party/
   └─ speech-to-speech/       # Hugging Face 上游项目（Git 子模块）
```

## 在新电脑上启动

### 1. 准备环境

- Git 2.40+
- Node.js 20 LTS 或 22 LTS
- npm 10+
- 后续接入语音服务时再安装 Python 3.10/3.11、FFmpeg 与相应 CUDA 环境

### 2. 克隆完整工程

```powershell
git clone --recurse-submodules https://github.com/zuming58/AIgirl.git
cd AIgirl
.\scripts\setup.ps1
```

如果普通克隆时忘记拉子模块：

```powershell
git submodule update --init --recursive
```

### 3. 启动 UI Demo

```powershell
cd apps\desktop-ui
npm run dev
```

浏览器打开终端提示的地址，通常是 `http://localhost:5173`。

### 4. 构建与测试

```powershell
cd apps\desktop-ui
npm run build
npm run test:sites
```

## 文档入口

- [开发手册](docs/DEVELOPMENT.md)：从新电脑初始化到模块接入
- [技术栈说明](docs/TECH_STACK.md)：当前实现、目标架构与替代方案
- [产品路线图](docs/ROADMAP.md)：从 UI Demo 到本地实时陪伴智能体
- [页面与交互规划](docs/design/页面与交互规划.md)：对话、回忆、计划和动态人物
- [UI 设计验收记录](docs/design/UI-设计还原与验收记录.md)
- [完整技术可行性与开发文档](docs/architecture/心屿-本地陪伴式智能体-技术可行性与开发文档.md)
- [原始架构蓝图](docs/architecture/原始架构蓝图.md)
- [参与开发](CONTRIBUTING.md)

## 项目边界与许可

`third_party/speech-to-speech` 是指向 Hugging Face 官方仓库的 Git 子模块，沿用其独立许可证和提交历史；本仓库不会把上游源码冒充为自有代码。生成式图片和演示文案目前仅用于产品原型，正式商用前需要完成素材来源、肖像权与模型许可证审查。

本仓库暂未授予开源许可证。除各第三方组件按其自身许可证使用外，其他内容默认保留全部权利。
