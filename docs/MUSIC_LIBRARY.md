# 本地音乐库

心屿的音乐库只索引用户显式配置的本机目录，不上传、复制或提交音乐文件。Core 将
文件路径保存在本地 SQLite 中，但列表 API、诊断和 JSON 导出不会返回绝对路径。

## 配置

使用 JSON 字符串数组配置一个或多个目录，然后重启 Core：

```powershell
$env:XINYU_MUSIC_DIRECTORIES_JSON = '["D:\\Music", "E:\\Shared Music"]'
```

未配置目录时音乐库状态为 `disabled`，不会自动扫描系统目录。支持 `mp3`、`flac`、
`m4a`、`ogg`、`opus` 和 `wav`。扫描只读取曲名、歌手、专辑、时长和封面是否存在，
不会把封面或音频内容写入数据库。

## API

```text
GET  /v1/music/library
POST /v1/music/library/scan
GET  /v1/music/tracks/{track_id}/audio
```

客户端使用资产 ID 获取音频，不接触本机路径。文件移动到任一已配置目录后，重新扫描会
通过 SHA-256 指纹恢复原记录；文件断开时记录保留为 `missing` 并给出恢复提示。

扫描在后台线程中运行。当前里程碑没有自动监控目录，也没有提交任何音乐或封面文件。
单个损坏、无法读取或格式与扩展名不匹配的音频不会中断整个扫描；接口会保留其余有效曲目，并以
`degraded`、`music_files_skipped` 和 `skipped_count` 返回可诊断但不含本机路径的状态。
