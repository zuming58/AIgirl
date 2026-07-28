# 参与开发

## 基本流程

1. 从最新主分支创建功能分支：`feature/<模块>-<说明>`。
2. 一次提交只处理一类问题，不提交模型权重、密钥、运行数据、`node_modules` 或构建产物。
3. UI 变更至少验证 1366×768 和 1920×1080 两种尺寸。
4. 提交前运行：

```powershell
cd apps\desktop-ui
npm ci
npm run build
npm run test:sites
```

5. Pull Request 说明应包含：改动目的、影响页面、验证方式、截图以及尚未解决的问题。

## 代码与产品约定

- UI 组件使用 React 函数组件；页面状态暂放在页面层，接入真实服务时再抽离 store。
- 视觉基调保持“温暖、克制、呼吸感”，不要堆叠高饱和色、过强发光或过多浮层。
- 动效必须支持 `prefers-reduced-motion`，不能影响文字可读性和输入操作。
- 对话、记忆和计划之间通过明确的数据结构连接，不直接依赖页面展示文案。
- 用户数据默认本地保存；任何云端调用必须可见、可配置、可关闭。
- 角色需要清楚说明其 AI 身份，避免以情感操控、内疚诱导等方式提高留存。

## 素材与依赖

- 新素材应记录来源、生成工具、使用范围和商用状态。
- 第三方项目优先使用子模块、包管理器或明确的适配层，不复制后抹去其许可证。
- 加入模型前记录模型名称、版本、下载地址、显存要求、许可证和校验值。

## 提交信息建议

```text
feat(memory): add memory timeline filtering
fix(ui): keep voice capsule visible at 1366x768
docs(architecture): document local TTS adapter
```
