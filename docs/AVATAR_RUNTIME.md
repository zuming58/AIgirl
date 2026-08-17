# 心屿动态人物运行方案（R13）

更新时间：2026-08-15

## 当前结论

R13 是唯一的生产母图。待机阶段不再把整张人物持续交给 LivePortrait 重绘，而采用“高清母图常驻 + 局部动作覆盖 + 界面层微动”的混合渲染。

原因是 LivePortrait 的人物区域首先进入 256×256 的模型输入，生成器再输出 512×512 的脸部结果。把最终画布提高到 2K 或 4K 只能提高贴回画布的尺寸，不能恢复母图原有的眼睛、睫毛、发丝和皮肤细节。整帧驱动会显著降低近景人物清晰度。

## 唯一身份资产

- 母图：`character-design/xinyu-main/identity-v1/00-identity-master.png`
- 尺寸：2352×3520
- SHA-256：`8C01CD26E552AEA7D14FDDC336388C76D0DB9F8CC69E71A3BBE301D58232AA88`
- 旧母图、旧表情和候选图只保存在 `identity-v1/backup/`，不得作为驱动输入。

## 待机渲染分层

1. **高清基础层**：始终显示 R13 原始母图或未来经确认的透明人物层。
2. **眨眼局部层**：LivePortrait 只负责生成闭眼过程；合成器只在约 0.6 秒的眨眼窗口内显示羽化后的双眼区域。
3. **呼吸层**：最终应用对人物透明层执行约 4.8 秒一个周期的 0.1%～0.2% 缩放和 1～2 px 垂直位移，不扭曲胸口和衣服纹理。
4. **点头层**：通过人物层整体做极小的旋转和位移；待机循环中不连续点头，倾听状态收到语义事件后才触发一次。
5. **视线规则**：待机时锁定母图视线，不允许自动左右扫视。未来只有明确的交互事件可以触发幅度很小、持续时间很短的视线变化。
6. **嘴部规则**：待机和倾听必须锁嘴，禁止露齿、张嘴、自动微笑。说话阶段以后使用单独的嘴部 ROI 驱动，不替换整张脸。

## 已完成工具

- `scripts/avatar/build-liveportrait-idle-template.py`
  - 从官方动作模板提取双眼闭合差值。
  - 冻结嘴、下颌、面颊和视线。
  - 生成两个自然眨眼和极轻头部姿态的可循环动作模板。
- `scripts/generate-avatar-motion.ps1`
  - 使用本机 LivePortrait 环境生成诊断用动作视频。
  - 默认可将贴回画布提高到 1920 长边，但该参数不等于真实脸部细节分辨率。
- `scripts/avatar/build-hybrid-idle-proof.ps1`
  - 以 R13 原图为高清基础层。
  - 只在两次眨眼期间羽化覆盖眼部区域。
  - 以 CRF 10 输出 2352×3520、30 fps 的高质量验证视频。

示例：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\avatar\build-hybrid-idle-proof.ps1 `
  -SourceMaster "F:\Codex\AI girl\character-design\xinyu-main\identity-v1\00-identity-master.png" `
  -BlinkVideo "F:\Codex\AI girl\character-design\xinyu-main\motion-tests\liveportrait-v1\idle-neutral-hq\00-identity-master--idle-neutral-v1.mp4" `
  -Output "F:\Codex\AI girl\character-design\xinyu-main\motion-tests\hybrid-idle-v1\xinyu-r13-hybrid-idle-proof.mp4"
```

## 当前验证结果

- 已拒绝官方 `d0` 驱动样片：存在视线游走、张嘴和傻笑。
- 已拒绝整帧超分辨率作为默认路线：它可以制造更锐的纹理，但不能恢复真实细节，并可能造成塑料感或时序闪烁。
- 当前混合样片保持 R13 的嘴型和视线，只有两次短眨眼；开放眼状态来自原始母图，而不是低分辨率生成脸。
- 当前样片仍是人物驱动验证，不是最终 16:9 房间场景。最终场景必须先产出透明人物层或无人物房间底图，才能只让人物呼吸而不让背景一起移动。

## 验收门槛

- 开眼静止帧与 R13 母图的人脸特征一致，不得因为超分辨率重塑眼睛、鼻子或嘴。
- 待机期间嘴部像素稳定，不露齿、不说话、不自动微笑。
- 两眼同步自然闭合；每次眨眼约 120～220 ms，间隔带轻微随机性。
- 视线默认锁定镜头，不来回扫视。
- 循环首尾没有跳帧、亮度跳变或人物位置跳动。
- 最终 16:9 应用中，人物主体仍位于屏幕水平中心，呼吸微动只作用于人物层。

## 下一阶段

1. 从最终 16:9 场景中拆出无人物房间底图和 R13 透明人物层。
2. 在 React/Tauri 中实现 `HybridAvatarLayer`，由 `idle / listening / thinking / speaking` 状态事件控制眨眼、点头和嘴部 ROI。
3. 为倾听状态增加一次性轻点头，不使用循环点头视频。
4. 接入语音后，仅将带时间戳的音素或音频包送入嘴部 Worker；基础层始终保持高清。
5. 在 4070 Ti SUPER 上验收 1080p/30 fps 合成、首帧延迟、显存占用和 30 分钟稳定性。
