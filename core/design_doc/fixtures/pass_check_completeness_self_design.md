# Design Doc：check_completeness / design_doc done-gate

## 头部元数据

| 字段 | 值 |
|---|---|
| T-id | local-fixture |
| req_id | design-doc-completeness |
| semantic_slug | check-completeness-self-design |
| phase | tool support |
| version | v1 |
| 日期 | 2026-06-04 |
| type | implementation |
| label | design-doc |
| PromptRef | local fixture for tools/design_doc/check_completeness.py |

## (0) 原始需求逐字原文

````text
为 design_doc 工具新增 check_completeness，检测三层设计文档是否填完。确定性壳检查残留占位和必填结构，第二 agent regulator 检查是否空泛回显需求以及关键决策是否有理由和不选项。
````

## Layer 1 功能设计

### 1.1 核心问题(core_need)

- design_doc_scaffold 能生成三层骨架，但没有机械 done-gate 阻止空骨架被当作完成稿；本任务要给设计文档增加可复跑的完成度误差信号。

### 1.2 成功效果(success_effect)

- 对残留占位或必填结构缺失的设计文档，工具返回 FLAG 并列出具体字段、章节、行号；对填实 fixture 返回 PASS；对空泛回显 fixture，确定性壳 PASS 但 regulator 输出 FLAG 和可操作字段说明。

### 1.3 硬性约束(hard_requirements)

- DC1/DC2 必须不调用 LLM，exit code 可复现；DC3/DC4 必须通过 cli_agent 调用第二 agent，且只传设计文档全文；检测谓词按标题和占位模式通用匹配，不写入 T631 的具体字段值。

### 1.4 明确不做(negative_requirements)

- 本轮不把检测器放进通用 detectors 集合，不改 design_doc_scaffold 的模板生成逻辑，不声明跨所有设计文档质量泛化。

### 1.5 交付物(deliverable)

- 交付 tools/design_doc/check_completeness.py、tools/design_doc/run_oracle.py、fixtures、logs、VALIDATION.md，并在 tools/INDEX.md 登记工具。

## Layer 2 实现设计

### 2.1 架构概述/组件图

```text
design document markdown -> deterministic shell for DC1/DC2 -> optional cli_agent regulator for DC3/DC4 -> oracle log and exit code
```

### 2.2 各组件职责与边界(scope_in/scope_out)

| 组件 | scope_in | scope_out | 证据或接口 |
|---|---|---|---|
| deterministic shell | 扫描 markdown 标题、表格和占位模式，输出 DC1/DC2 issues | 不判断内容是否真正有设计深度 | tools/design_doc/check_completeness.py scan_file |
| regulator prompt | 让第二 agent 只看设计文档全文，判断 DC3/DC4 | 不读取作者推理、聊天记录、repo sibling 文件 | check_completeness.py run_regulator_for_text |
| oracle harness | 固化 T631 positive、填实 hard negative、DC3 soft negative 的验证结果 | 不把 regulator raw 自动判成 pass/fail | tools/design_doc/run_oracle.py |

### 2.3 关键设计决策(含为什么)

| 决策 | 选择 | 为什么 | 放弃的替代方案 |
|---|---|---|---|
| 工具位置 | check_completeness.py 与 design_doc_scaffold.py co-locate | 它是 design_doc 产物的 done-gate，调用者会在工具旁寻找 | 不放 adhoc detectors 集合，因为该检测器不是通用失败模式库 |
| DC1/DC2 实现 | 使用标准库 markdown line scanner 和表格解析 | 结构信号来自模板标题和占位模式，标准库足够且可复现 | 不引入 markdown 第三方解析器，避免工具安装依赖 |
| regulator 输出 | 要求 strict JSON，同时在 run_oracle 日志保留 raw | 机器可读方便复查，raw 能让人工核验可操作性 | 不让 harness 自己给 DC3/DC4 判 pass/fail，避免 LLM 判断被伪装成确定性 oracle |

### 2.4 反过度工程化三问

- 这个机制是否同时服务多个核心失败模式，而不是只为一个边角问题加协议：服务骨架未填和空泛回显两类真实失败，二者都来自设计文档完成信号缺失。
- 有没有更小、更确定的实现能满足同一证明义务：有；DC1/DC2 只做 line scanner，DC3/DC4 只在需要时调 regulator。
- 新增复杂度是否有真实消费链和验证证据支撑：有；design_doc_protocol 把 check_completeness 作为完成检测器引用，run_oracle 用 T631 和两个 fixtures 验证。

## Layer 3 代码改动清单

### 3.1 新增(ADDED)

- tools/design_doc/check_completeness.py：新增完成度检测器。
- tools/design_doc/run_oracle.py：新增验证 harness。
- tools/design_doc/fixtures/pass_check_completeness_self_design.md：新增 PASS fixture。
- tools/design_doc/fixtures/dc3_echo_soft_negative.md：新增 DC3 soft negative fixture。
- tools/design_doc/VALIDATION.md：记录 bounded 验证结论。

### 3.2 修改(MODIFIED)

- tools/INDEX.md：给 design_doc 工具族登记 check_completeness done-gate。
- tools/design_doc/README.md：补充完成度检测器的使用入口。

### 3.3 删除(REMOVED)

- 无。

### 3.4 变更前后对比表

| 对象 | 变更前 | 变更后 | 证据 |
|---|---|---|---|
| design_doc 完成信号 | 只有 scaffold 生成成功，无法判断骨架是否填实 | DC1/DC2 可复现判别，DC3/DC4 有隔离 regulator raw | python3 tools/design_doc/run_oracle.py --reps 0 |

## Final Boundary

| 字段 | 填写 |
|---|---|
| 状态 | DONE |
| 已覆盖 | 检测器、fixtures、oracle、工具索引登记、验证记录 |
| 未覆盖 | 多任务真实样本泛化、live-loop 自动拦截、跨模型 regulator 稳定性 |
| 延后 | 若未来 design_doc 模板改字段，需要同步更新 required heading matcher |
| 证据边界 | 当前证据只覆盖本检测器在 T631、PASS fixture、DC3 soft negative 上的 bounded 行为 |
