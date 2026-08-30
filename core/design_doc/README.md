# design_doc

`design_doc` 从 `todo dispatch <T-id>` 读取原始 prompt 和任务元数据，生成三层 Design Doc 骨架。

## Usage

```bash
python3 core/design_doc/design_doc_scaffold.py T631 --slug git-env-cleanup-design
python3 core/design_doc/design_doc_scaffold.py T631
python3 core/design_doc/check_completeness.py core/design_doc/fixtures/T631_git-env-cleanup-design.md
python3 core/design_doc/check_completeness.py core/design_doc/fixtures/dc3_echo_soft_negative.md --regulator --regulator-tier claude-zai:high --timeout 600
```

参数：
- `task_id`：landing-pipeline 的 T-id。
- `--slug`：可选语义 kebab slug；传入后文件名为 `<T-id>_<slug>.md`。

未传 `--slug` 时，工具从 `todo show <T-id>` 的任务标题派生语义 slug，绝不使用纯 req_id 作为文件名。

## Input / Output

输入来自 `tools/todo/todo.py dispatch/show`。输出目录经 `DDP_DESIGN_DOC_DIR` 环境变量配置（缺省 `<仓根>/design_docs/`），并在头部元数据写入 `semantic_slug`。

同名文件已存在时退出 1，不覆盖既有设计文档；每次调用会 best-effort 写入 `tool_receipts`。

## When To Use

当 landing-pipeline 任务需要先固定需求锚、实现边界和代码 delta 计划时，用这个工具起 Design Doc 骨架。

## Completion Gate

`check_completeness.py` 是 design_doc 的完成度检测器。

- DC1/DC2：确定性壳，零 LLM。脚手架在元数据写入 `d9_contract | on-demand-v1`。当前契约始终检查 `success_effect`、`negative_requirements`、`requirement_doc` 锚和 Final Boundary；D9 表逐行检查 Layer 2/3 的 `required`、`not_applicable` 或 `unwritten` 状态、理由和触发评估。`required` 只有至少一个命名 trigger 为 `true` 才有效，并要求对应决策表或代码改动清单；全部 trigger 为 `false` 却写 `required` 会 FLAG，`unwritten` 始终 FLAG。没有 D9 标记的历史文档继续按旧的 Layer 1 五格和 Layer 2 决策表读取，不因兼容读取而获得当前契约认证。
- DC3/DC4：可选 regulator。通过 `cli_agent` 只喂设计文档全文，判断是否空泛回显需求、关键决策是否有理由和不选项。
- Oracle：`python3 core/design_doc/run_oracle.py --reps 0` 验证确定性判别；`--reps 1 --regulator-tier claude-zai:high --timeout 600` 记录 regulator raw。

D9 的触发键是 Layer 2 的 `multiple_paths`、`handoff`、`user_confirmation`、`cross_file_impact`，以及 Layer 3 的 `existing_object_disposition`、`implementation_writeback`、`direct_multi_file_execution`。触发值只允许 `key=true|false`；`yes/no`、`active/inactive`、`triggered/not_triggered` 等别名会被 FLAG。`filled` 只属于三面 `face_status`，不是当前 D9 layer state。checker 只判结构，不判断理由质量、触发判断是否正确或任务是否成功；当前 P4 结论上限是 `p4_d9_static_structural_reconciliation_only_no_protocol_effect_claim`。
