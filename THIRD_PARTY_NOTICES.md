# Third-party notices

## Hugging Face speech-to-speech

- Upstream: <https://github.com/huggingface/speech-to-speech>
- Local path: `third_party/speech-to-speech`
- Pinned commit: `656099afffda445a3a3cef8ffee55871c9b6123c`
- License: Apache License 2.0

心屿直接复用该子模块的 OpenAI Realtime-compatible WebSocket 客户端、
编解码辅助模块和 AudioWorklet。生产构建从固定提交注入
`mic-capture.js` 与 `audio-playback.js`，未删除或替换上游许可证。

完整许可证文本和上游提交历史保留在
`third_party/speech-to-speech/` 中。升级固定提交前必须重新运行语音代理、
AudioWorklet 构建和浏览器降级回归。

## 主要运行时依赖

| 组件 | 当前版本 | 许可证 |
| --- | ---: | --- |
| React / React DOM | 19.2.0 | MIT |
| Phosphor Icons React | 2.1.10 | MIT |
| Noto Sans SC Variable | 5.3.0 | SIL Open Font License 1.1 |
| Tauri JavaScript API | 2.11.1 | Apache-2.0 OR MIT |
| Tauri autostart plugin | 2.5.1 | MIT OR Apache-2.0 |
| Tauri notification plugin | 2.3.3 | MIT OR Apache-2.0 |
| FastAPI | 0.140.13 | MIT |
| Pydantic | 2.13.4 | MIT |
| Uvicorn | 0.52.0 | BSD-3-Clause |
| websockets | 16.1.1 | BSD-3-Clause |
| PyInstaller | 6.21.0 | GPL-2.0-or-later with bootloader exception |

版本来自当前锁文件和已安装发行包。正式发布前仍须对完整传递依赖、模型权重、
生成素材和 Rust `Cargo.lock` 生成机器可核对的许可证清单；本表不能替代法律审核。
