# Agentcore 模块结构与命名规范

本文档约定 agentcore 系列模块的目录结构、包命名和对外导出方式，作为新增 agentcore 模块时的统一依据。

---

## 一、仓库与目录命名

| 用途           | 规范               | 示例                    |
|----------------|--------------------|-------------------------|
| 仓库/根目录名  | `agentcore-{模块}`，kebab-case | `agentcore-task`、`agentcore-metering` |
| Python 包名    | `agentcore_{模块}`，全小写 + 下划线 | `agentcore_task`、`agentcore_metering` |
| PyPI / setuptools `name` | 与仓库一致，kebab-case | `agentcore-task` |

规则：**目录与 PyPI 用 kebab-case，Python 包名用单下划线、全小写。**

---

## 二、顶层包结构

```
agentcore-{module}/           # 仓库根，kebab-case
  agentcore_{module}/         # Python 包根，下划线
    __init__.py
    constants.py              # 领域常量（可选，按需）
    adapters/
      __init__.py
      django/                 # 或其他 runtime：fastapi, flask...
        ...
  pyproject.toml
  README.md
  docs/
  tests/
```

- 领域通用常量放在**根包**下 `constants.py`（如 `TaskStatus`），便于多适配层复用。
- 适配层按 runtime 分目录：`adapters/django/`、`adapters/fastapi/` 等，目录名小写。

---

## 三、Django 适配层内部结构（简化：仅 services 层）

```
agentcore_{module}/
  adapters/
    django/
      __init__.py           # 对外入口，从 services 懒加载并导出
      services/             # 实现与对外 API 均在此包
        __init__.py         # 统一导出（锁、TaskTracker、TaskStatus、TaskLogCollector 等）
        *.py                # 具体实现（如 lock, task_lock, task_tracker, log_collector）
      models.py
      views/
      urls.py
      admin.py
      apps.py
      serializers.py
      migrations/
      ...
```

约定：

- **services/**：既是对外 API 的实现，也是对外导出的定义；在 `services/__init__.py` 中集中 re-export 或实现，并维护 `__all__`。
- **adapters/django/__init__.py**：通过 `__getattr__` 从 `services` 按名懒加载并导出，避免顶层 import 时加载 Django 模型等导致 AppRegistryNotReady。

不单独设 interface 层，对外与实现统一放在 services。

---

## 四、命名规则汇总

| 对象           | 规则               | 示例 |
|----------------|--------------------|------|
| 仓库/目录      | kebab-case         | `agentcore-task` |
| Python 包      | 全小写 + 下划线    | `agentcore_task` |
| 适配层目录     | 小写               | `django`、`fastapi` |
| 实现与导出包   | 固定名 `services` | `adapters/django/services/` |
| 常量类/常量模块 | 大驼峰或全大写     | `TaskStatus`、`DEFAULT_TIMEOUT` |
| 函数/方法      | snake_case         | `acquire_task_lock`、`register_task_execution` |

---

## 五、导入约定

- **推荐（对外使用）**  
  `from agentcore_{module}.adapters.django import ...`  
  例如：`from agentcore_task.adapters.django import TaskTracker, acquire_task_lock`

- **可选（直接来自 services）**  
  `from agentcore_{module}.adapters.django.services import ...`  
  与从 `adapters.django` 导入的符号一致，按需使用。

---

## 六、Django 适配层入口实现要点

- `adapters/django/__init__.py` 中定义 `__all__`，并实现 `__getattr__(name)`，从 **`services`** 按名懒加载并返回。
- `adapters/django/services/__init__.py` 中集中实现或从子模块 re-export 对外 API，并维护与顶层一致的 `__all__`。

---

## 七、文档与测试

- 每个 agentcore 模块建议包含：
  - 根目录 **README.md**：安装、用法、对外 API 说明。
  - **docs/**：设计说明（如 DESIGN.md）、实现清单、领域词汇等。
- 本文档（**AGENTCORE_STRUCTURE_AND_NAMING.md**）作为**结构定义与命名**的参考，新建 agentcore 模块时请按此约定实现。

---

## 八、与现有模块的对应关系

- **agentcore-task**：已按上述规范实现（仅 `services/` 层，对外从 `agentcore_task.adapters.django` 或 `agentcore_task.adapters.django.services` 导入）。
- **agentcore-metering**：可按需将对外导出收敛到 `adapters/django/services/` 并保持与本文档一致。
