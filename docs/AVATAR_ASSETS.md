# 高质量人物状态视频资产规范

## 目录与命名

运行数据目录下使用固定角色 ID：

```text
avatar/
└─ xinyu-main/
   ├─ idle.mp4
   ├─ listening.mp4
   ├─ thinking.mp4
   ├─ speaking.mp4
   ├─ smiling.mp4
   └─ goodnight.mp4
```

`idle / listening / thinking / speaking` 是启用视频状态库的最小集合；
`smiling / goodnight` 可后补。文件由 Core 的受限状态路由提供，客户端不能传入
任意路径。

## 画面约束

- 1920×1080、16:9、25 fps；
- H.264 High Profile、`yuv420p`、无音轨；
- 与批准的静态主场景保持相同人物、机位、裁切、桌面和灯光；
- 人物面部与上半身位于全屏水平中心，不能向左漂移；
- 循环片段首尾曝光、姿态和视线连续，不使用明显镜头运动；
- `speaking` 仅作为高质量预制回退，真实口型阶段仍由独立局部脸区 Worker 驱动。

## 状态语义

| 文件 | 建议时长 | 动作 |
| --- | ---: | --- |
| `idle.mp4` | 6–10 秒 | 呼吸、偶尔眨眼、极轻微视线变化 |
| `listening.mp4` | 4–8 秒 | 目光专注、轻微点头，不持续重复大动作 |
| `thinking.mp4` | 4–8 秒 | 短暂移开视线后回看，不表现焦虑 |
| `speaking.mp4` | 4–8 秒 | 克制自然的说话姿态，便于无口型时回退 |
| `smiling.mp4` | 3–6 秒 | 温暖短微笑后回到中性 |
| `goodnight.mp4` | 6–10 秒 | 更低能量、更柔和灯光，保持可循环 |

## 启用与验证

导入文件后重启 Core，检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/v1/avatar/status
```

只有返回 `renderer: video_state_library` 才表示最小集合完整。随后分别触发
`listening / thinking / speaking / idle`，确认切换前静态底图一直存在、视频首帧
淡入、无黑帧、无音轨抢占、人物位置不跳动。

## 权利门

正式发布前必须为角色原图、生成模型、状态视频和任何真人参考保存来源、
许可范围、生成日期与审核记录。没有明确肖像和商用权时只能用于本机原型。
