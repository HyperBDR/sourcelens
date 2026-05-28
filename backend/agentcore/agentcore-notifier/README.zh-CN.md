# Agentcore Notifier

[English](README.md)

面向 Django 的通知管理模块（webhook、邮件等），与 agentcore-metering、agentcore-task 同属 agentcore 系列。

- 配置存储在 **NotifierConfig** 表（scope=global，key+value JSON）。
- 发送仅通过 **Celery 任务**完成，无 HTTP 发送接口。
- 支持静默与合并规则，详见 [docs/MERGE_SILENCE_DESIGN.md](docs/MERGE_SILENCE_DESIGN.md)。
- 飞书自定义机器人： [docs/FEISHU_WEBHOOK.md](docs/FEISHU_WEBHOOK.md)。
- 企业微信 webhook 的 `provider_type` 推荐使用 `wecom`；`wechat` 仅保留为兼容别名，避免历史配置失效。

---

## 安装

- **未上架 PyPI**，仅支持从 GitHub 安装。

**从 GitHub 安装**（克隆后可编辑）：

```bash
pip install -e git+https://github.com/cloud2ai/agentcore-notifier.git
```

若主项目以 submodule 方式引用，在仓库根目录执行：

```bash
pip install -e path/to/agentcore-notifier
```

- 在主项目的 `INSTALLED_APPS` 中加入（如 Agentcore Notifier）：

```python
'agentcore_notifier.adapters.django',
```

- 主项目 Dockerfile 需遍历 `agentcore/` 下各子模块并执行 `pip install -e`。
- 详细说明见主项目 README。

---

## 配置

所有配置存储在 **NotifierConfig** 表（scope=global，key+value JSON）。不依赖主项目 settings 或 app_config 注入；webhook URL、提供商、语言等均通过 notifier 管理界面或 API 设置。

配置方式：

- **Django Admin**：NotifierConfig（key=global、silence_rules）；NotificationChannel 管理 Webhook/邮件渠道。
- **API**：渠道用 `channels/` 增删改查；全局与静默用 `global/`、`silence-rules/`（见下方 API 参考）。

---

## 默认渠道辅助函数

`get_default_webhook_channel()` 与 `get_default_email_channel()`（位于
`adapters.django.services.webhook_service` 与 `email_service`）均返回
`(channel, config_dict)` 或 `(None, None)`。

- **channel**：当前生效的 `NotificationChannel` 实例（或 None）。
- **config_dict**：由 `channel.config` 构建的字典（webhook 为 url/headers 等，
  邮件为 smtp_host/from_email 等），或 None。

解包时请统一命名，避免与使用翻译的模块中的 gettext `_` 冲突：

- 两个都要：`channel, config = get_default_webhook_channel()`
- 只要 channel：`channel, _config = get_default_webhook_channel()`
- 只要 config：`_channel, config = get_default_webhook_channel()`

`get_default_email_channel()` 用法相同。

---

## 发送通知

仅通过 **Celery 任务**发送（无 HTTP 发送接口）。任务会执行静默与合并检查，再调用 WebhookService 并写入 NotificationRecord。

```python
from agentcore_notifier.adapters.django.tasks.send import send_webhook_notification

send_webhook_notification.delay(
    payload={"msg_type": "post", "content": {...}},
    provider_type="feishu",
    source_app="my_app",
    source_type="alert",
    source_id="123",
    user_id=user_id,
)
```

- 合并与静默逻辑见 [docs/MERGE_SILENCE_DESIGN.md](docs/MERGE_SILENCE_DESIGN.md)。
- 飞书自定义机器人消息格式与可选 sign_secret 见 [docs/FEISHU_WEBHOOK.md](docs/FEISHU_WEBHOOK.md)。

---

## API 参考

- 挂载在管理前缀下（如 `api/v1/admin/notifications/`）。
- **鉴权**：`IsAdminUser`（staff 或 superuser），否则 403。

### 统计与配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `.../notification-stats/` | 汇总、按来源、按提供商、时间序列 |
| GET | `.../notification-records/` | 通知记录分页列表 |
| GET / PUT | `.../global/` | 全局配置（保留天数、清理等） |
| GET / PUT | `.../silence-rules/` | 静默规则（NotifierConfig key=silence_rules） |
| GET / POST | `.../channels/` | 通知渠道列表、创建渠道（Webhook/Email） |
| GET / PUT / DELETE | `.../channels/<uuid>/` | 获取/更新/删除单条渠道 |
| POST | `.../channels/validate/` | 校验渠道配置且不保存 |

---

## 清理

旧通知记录的清理由 NotifierConfig key=global 中的 `retention_days`、`cleanup_crontab`、`cleanup_enabled` 控制。启用后由 Celery Beat 定时任务执行。调度在 `AppConfig.ready()` 中合并注册。

---

## 项目结构

- `agentcore_notifier/` – 包根目录。
- `agentcore_notifier/adapters/django/` – Django 应用：models、admin、views、URLs、Celery 任务。
- `agentcore_notifier/adapters/django/services/` – WebhookService、邮件、合并/静默、notification_config、统计、清理。
- `docs/` – 飞书 webhook 等参考文档。
- `tests/` – Pytest 测试（Django 配置见 `tests.settings`）。

---

## 测试

在包根目录（agentcore-notifier）下执行：

```bash
pip install -e ".[dev]"
pytest
```

仅统计 services 层覆盖率：

```bash
pytest --cov=agentcore_notifier.adapters.django.services --cov-report=term-missing
```

需已配置 Django 与 Celery；`tests.settings` 与 `tests.conftest` 提供测试环境。
