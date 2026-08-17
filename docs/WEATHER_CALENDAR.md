# 天气与日历 Provider

天气和日历采用可替换 Provider 契约。当前版本默认均为 `disabled`，不会请求定位、访问网络、
读取系统日历或连接真实账号，也不会用静态内容伪装为实时结果。

```text
GET /v1/integrations/status
GET /v1/weather/current
GET /v1/calendar/events?start=<ISO-8601>&end=<ISO-8601>
```

日历查询必须携带带时区的 ISO-8601 起止时间，范围必须递增且不超过 366 天。Provider
只返回规范化日程字段；状态接口不返回端点、密钥、账号、坐标或日程正文。天气只返回用户
授权后由 Provider 提供的位置标签，不暴露经纬度。

后续接真实服务时，必须先实现独立的用户授权/撤销流程，并把密钥存入操作系统安全凭据存储，
不得写入 SQLite、日志、诊断、JSON 导出或 Git。Provider 失败时 API 返回稳定的脱敏错误码，
不影响文字聊天、记忆、计划、音乐和语音。
