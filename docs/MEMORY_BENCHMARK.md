# 记忆检索基准

此基准使用固定种子的合成数据和独立 SQLite 文件，不读取或修改用户数据库，不调用真实
embedding 服务，也不下载模型。默认生成 10 万条记忆，测量建库耗时、数据库大小、FTS5
查询 P50/P95 和 Top-5 命中率。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\benchmark-memory.ps1
```

可用 `-Count`、`-Queries`、`-Seed` 和 `-DatabasePath` 调整参数。目标文件必须不存在，
脚本绝不覆盖已有数据库。生成的数据库保留在 `temp/` 供人工检查和逐文件清理。

该结果只衡量开发机上的 SQLite/FTS5 基线，不代表中文语义召回准确率。真实
`BAAI/bge-small-zh-v1.5`、sqlite-vec、10 万条数据 P95 和 Top-5 中文语义命中率仍须在
RTX 4070 Ti SUPER 目标机完成最终验收。
