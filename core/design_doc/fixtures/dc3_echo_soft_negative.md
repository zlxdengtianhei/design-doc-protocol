# Design Doc：echo-only soft negative

## 头部元数据

| 字段 | 值 |
|---|---|
| T-id | soft-negative |
| req_id | design-doc-completeness |
| semantic_slug | echo-only-soft-negative |
| phase | tool support |
| version | v1 |
| 日期 | 2026-06-04 |
| type | implementation |
| label | design-doc |
| PromptRef | local fixture for DC3 regulator |

## (0) 原始需求逐字原文

````text
为 design_doc 工具新增 check_completeness，检测三层设计文档是否填完。确定性壳检查残留占位和必填结构，第二 agent regulator 检查是否空泛回显需求以及关键决策是否有理由和不选项。
````

## Layer 1 功能设计

### 1.1 核心问题(core_need)

- 核心问题是解决这个需求，让设计文档完成度检测正常工作。

### 1.2 成功效果(success_effect)

- 成功效果是完成用户要求，最终让这个需求被完成。

### 1.3 硬性约束(hard_requirements)

- 硬性约束是满足所有要求，保证实现符合任务描述。

### 1.4 明确不做(negative_requirements)

- 不做和这个需求无关的事情。

### 1.5 交付物(deliverable)

- 交付物是完成后的检测器和相关文件。

## Layer 2 实现设计

### 2.1 架构概述/组件图

```text
需求 -> 实现检测器 -> 完成任务
```

### 2.2 各组件职责与边界(scope_in/scope_out)

| 组件 | scope_in | scope_out | 证据或接口 |
|---|---|---|---|
| 检测器 | 负责检测是否完成 | 不负责无关内容 | 相关工具路径 |

### 2.3 关键设计决策(含为什么)

| 决策 | 选择 | 为什么 | 放弃的替代方案 |
|---|---|---|---|
| 完成度检测 | 按照用户要求实现完成度检测 | 因为任务要求实现这个检测器 | 不选择其他方式，因为其他方式不符合需求 |

### 2.4 反过度工程化三问

- 这个机制是否同时服务多个核心失败模式，而不是只为一个边角问题加协议：是，因为它解决这个问题。
- 有没有更小、更确定的实现能满足同一证明义务：有，按需求实现即可。
- 新增复杂度是否有真实消费链和验证证据支撑：有，因为用户要求要验证。

## Layer 3 代码改动清单

### 3.1 新增(ADDED)

- tools/design_doc/check_completeness.py：新增需求中的检测器。

### 3.2 修改(MODIFIED)

- tools/INDEX.md：登记需求中的工具。

### 3.3 删除(REMOVED)

- 无。

### 3.4 变更前后对比表

| 对象 | 变更前 | 变更后 | 证据 |
|---|---|---|---|
| 需求 | 没有完成 | 完成需求 | 相关验证 |

## Final Boundary

| 字段 | 填写 |
|---|---|
| 状态 | DONE |
| 已覆盖 | 已覆盖用户要求 |
| 未覆盖 | 无 |
| 延后 | 无 |
| 证据边界 | 证据是已经完成 |
