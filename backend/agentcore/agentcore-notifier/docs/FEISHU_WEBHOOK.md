# 飞书自定义机器人 Webhook 参数说明

本文说明通过 agentcore-notifier 向飞书群机器人发送消息时使用的参数与安全设置。官方文档：[飞书 - 自定义机器人使用指南](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot?lang=zh-CN)。

## 一、消息体格式（请求 body）

飞书自定义机器人要求 POST 请求体为 JSON，且包含：

| 字段 | 必填 | 说明 |
|------|------|------|
| **msg_type** | 是 | 消息类型，如 `text`、`post`、`image`、`interactive`（卡片）等 |
| **content** | 是 | 消息内容，结构与 msg_type 对应，见官方文档 |

常见类型示例：

- **text**：`{"text": {"text": "内容"}}`
- **post**（富文本）：`{"post": {"zh_cn": {"title": "标题", "content": [[{"tag": "text", "text": "..."}]]}}}`
- **image**：需传图片 key（先通过上传接口获取）
- **interactive**：卡片消息，结构见文档

本模块在发送前会按渠道配置自动添加 **message_prefix**（消息前缀），并可选添加 **签名校验** 字段。

## 二、安全设置：签名校验（加签）

若在飞书群机器人中开启了「签名校验」，则请求体中还需包含：

| 字段 | 说明 |
|------|------|
| **timestamp** | 当前时间戳，单位**秒**（如 `1599360473`），需在有效期内（建议 ±5 分钟内） |
| **sign** | 签名字符串：签名字符串 = `timestamp + "\n" + 密钥`，使用 **HMAC-SHA256** 计算后 **Base64** 编码 |

在通知渠道的 Webhook 配置中填写 **sign_secret**（与飞书机器人安全设置中的「密钥」一致）后，本模块会在每次发送时自动在 body 中加入 `timestamp` 与 `sign`，无需业务方处理。

## 三、渠道 config 中与飞书相关的字段

| 字段 | 说明 |
|------|------|
| provider_type | 固定为 `feishu`（或 wecom，与飞书兼容） |
| url | 机器人的 Webhook 地址 |
| message_prefix | 可选，拼在消息正文前的文案 |
| sign_secret | 可选，开启签名校验时填写飞书提供的密钥 |
| timeout | 可选，请求超时秒数 |
| headers | 可选，额外请求头 |

## 四、飞书支持的 msg_type 简要对照

| msg_type | 说明 |
|----------|------|
| text | 纯文本 |
| post | 富文本（标题 + 段落，支持 text/at/img 等 tag） |
| image | 图片（需先上传拿 image_key） |
| file | 文件 |
| interactive | 卡片消息（含按钮、表单等） |
| share_chat / share_user | 分享群/用户 |

具体 content 结构以 [飞书开放平台文档](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot?lang=zh-CN) 为准。
