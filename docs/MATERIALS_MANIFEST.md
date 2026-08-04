# 交接资料清单

更新日期：2026-08-04

## 已进入 GitHub 的资料

| 资料 | GitHub 位置 | 说明 |
| --- | --- | --- |
| 当前完整工程 | 仓库根目录 | React/Vite、Tauri、FastAPI、SQLite、语音代理、模型管理、测试与脚本 |
| 完整交接入口 | `完整开发交接文档.md` | 当前状态、目标硬件、分支、启动、架构、人工门和验收 |
| 另一台电脑计划 | `docs/OTHER_PC_FUNCTION_PLAN.md` | 功能分工、分支、提交顺序、验收和合并办法 |
| 当前技术可行性文档 | `docs/architecture/心屿-本地陪伴式智能体-技术可行性与开发文档.md` | 由早期 TTUan 方案演进而来的当前技术基准 |
| 早期 TTUan 技术草案 | `docs/archive/TTUan-本地虚拟女友-技术可行性与开发文档-2026-07-28.md` | 原始草案归档，正文与本机源文件规范化后相同 |
| 原始架构蓝图 | `docs/architecture/原始架构蓝图.md` | 用户提供的 TTUan 架构蓝图副本 |
| 技术栈、路线与状态 | `docs/TECH_STACK.md`、`docs/ROADMAP.md`、`docs/IMPLEMENTATION_STATUS.md` | 当前实现和下一阶段验收依据 |
| 语音运行时 | `docs/VOICE_RUNTIME.md` | speech-to-speech 接入、运行档位和人工门 |
| 人物资产规范 | `docs/AVATAR_ASSETS.md` | 只作为接口和验收规范；实际人物新设计留在主电脑 |
| UI 设计记录 | `docs/design/`、`apps/desktop-ui/design-qa.md` | 页面规划、布局约束和还原记录 |
| 关键展示图 | `docs/assets/`、`apps/desktop-ui/qa-*.png` | 当前主界面与功能页面验收图 |
| Hugging Face speech-to-speech | `third_party/speech-to-speech` | Git 子模块，固定 `656099afffda445a3a3cef8ffee55871c9b6123c` |

## 本机旧目录的处理结论

### `F:\Codex\AI girl\xinyu-ui-demo`

这是进入正式仓库之前的 UI 原型工作目录。其可维护源码已经演进并进入 `apps/desktop-ui/`；正式仓库版本还增加了 Core API、记忆、计划、设置、语音和 Tauri 集成，因此不再把旧源码复制成第二套应用。

其中两张主要交付图已逐字节核对并存在正式仓库：

- `qa-moment-1920x1080.png` → `docs/assets/xinyu-moment-1920x1080.png`；
- `design-qa-feature-pages-montage.png` → `docs/assets/xinyu-feature-pages.png`。

旧目录中的 `node_modules/`、`dist/`、Vite 日志、重复构建字体、临时对比图和已淘汰 Logo 迭代不属于跨电脑继续开发所需源资料，不上传 GitHub。这样避免仓库出现两套相互漂移的 UI 和大量可重建产物。

### `F:\Codex\AI girl\speech-to-speech`

这是上游仓库的独立学习副本，HEAD 为 `656099afffda445a3a3cef8ffee55871c9b6123c`。正式工程已经用同一提交的 Git 子模块保存，不重复上传整个副本。

### 运行产物

以下内容刻意不上传，并已由 `.gitignore` 保护：

- `temp/` 中的 SQLite、缓存、日志与运行数据；
- `.venv/`、`.venv-voice/` 和 `node_modules/`；
- `dist/`、PyInstaller 和 Tauri binaries；
- 模型权重、Hugging Face 缓存和 CUDA 缓存；
- `.env`、API Key、Token 和本机凭据；
- 个人聊天、记忆正文、麦克风设备 ID；
- 未确认授权的真人肖像、声音与音乐。

这些不是遗漏，而是隐私、许可、仓库体积和可重复构建边界。

## 人物资料边界

当前已用于 UI Demo 的场景图和通用人物画面已在仓库中。后续重新塑造的女主人物、身份参考图、状态视频、LivePortrait/MuseTalk 中间资产和声音样本保留在主电脑，等用户确认形象与授权后再决定是否进入私有制品库；另一台电脑只遵循人物状态接口，不生产或替换人物。

## GitHub 分支资料入口

| 分支 / PR | 用途 |
| --- | --- |
| `main` | 稳定基线，目前仍是初始工程 |
| `agent/xinyu-desktop-foundation` / PR #1 | 当前完整集成分支与交接文档入口 |
| `agent/voice-runtime-integration` / PR #2 | 另一台电脑继续开发语音和模型运行时 |
| `agent/avatar-identity-scene` | 主电脑保留的人物/场景分支；另一台电脑不得修改 |
