#!/usr/bin/env python3
"""Create landing-pipeline design document skeletons from the TODO dispatch source."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
import os
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core.dispatch_parse import (  # noqa: E402
    DispatchParseError,
    normalize_task_id,
    parse_dispatch,
    parse_show,
)

TODO_CLI = WORKSPACE_ROOT / "tools" / "todo" / "todo.py"
DESIGN_DOC_DIR = Path(
    os.environ.get(
        "DDP_DESIGN_DOC_DIR",  # 目录约定外提为配置（D6 重组裁定）；未设置时落到 <仓根>/design_docs
        str(WORKSPACE_ROOT / "design_docs"),
    )
)
EXPECTED_LABEL = "landing-pipeline"


class ScaffoldError(Exception):
    """User-facing scaffold failure."""


CHINESE_TERM_SLUGS = (
    ("Design Doc", "design-doc"),
    ("Design Docs", "design-docs"),
    ("design doc", "design-doc"),
    ("landing pipeline", "landing-pipeline"),
    ("Git 环境", "git-env"),
    ("Git工具", "git-tool"),
    ("原始prompt", "original-prompt"),
    ("原始 Prompt", "original-prompt"),
    ("原始需求", "original-requirement"),
    ("报告存放位置", "report-location"),
    ("报告书写标准", "report-writing-standard"),
    ("前后对比", "before-after"),
    ("专业术语", "terminology"),
    ("实现逻辑", "implementation-logic"),
    ("确定层", "deterministic-layer"),
    ("语义层", "semantic-layer"),
    ("调用记录", "call-receipt"),
    ("反馈机制", "feedback-mechanism"),
    ("工具端", "tool-side"),
    ("脚手架", "scaffold"),
    ("报告", "report"),
    ("设计文档", "design-doc"),
    ("设计", "design"),
    ("工具", "tool"),
    ("机制", "mechanism"),
    ("清理", "cleanup"),
    ("环境", "env"),
    ("路由", "routing"),
    ("落地", "landing"),
    ("实现", "implementation"),
    ("命名", "naming"),
    ("语义", "semantic"),
    ("位置", "location"),
    ("标准", "standard"),
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "why",
}
MAX_SLUG_PARTS = 7


def run_todo(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(TODO_CLI), *args],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ScaffoldError(f"todo {' '.join(args)} failed: {detail}")
    return result.stdout


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if slug and not re.fullmatch(r"[a-z]?-?\d+|[a-z]+-\d+", slug):
        return slug
    return ""


def _append_slug_part(parts: list[str], part: str) -> None:
    for item in normalize_slug(part).split("-"):
        if item and item not in STOPWORDS and item not in parts:
            parts.append(item)


def derive_slug(show_fields: dict[str, str], task_id: str) -> str:
    title = show_fields.get("Title") or show_fields.get("Description", "")
    parts: list[str] = []
    for phrase, replacement in CHINESE_TERM_SLUGS:
        if phrase in title:
            _append_slug_part(parts, replacement)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", title):
        _append_slug_part(parts, token)
    slug = "-".join(parts[:MAX_SLUG_PARTS])
    return slug or f"{task_id.lower()}-semantic-task"


def render_design_doc(
    task_id: str,
    original_prompt: str,
    metadata: dict[str, str],
    show_fields: dict[str, str],
    slug: str,
    req_doc: str = "",
    todo_register: str | None = None,
) -> str:
    req_id = metadata.get("req_id") or show_fields.get("Req", "")
    label = metadata.get("label") or show_fields.get("Label", "")
    task_type = metadata.get("type") or show_fields.get("Type", "")
    phase = show_fields.get("phase", "<phase>")
    prompt_ref = show_fields.get("PromptRef", "<PromptRef>")
    today = date.today().isoformat()

    req_anchor = (
        f"req-doc: `{req_doc}`\n\n"
        "需求原文唯一真源见上方 requirement_doc；本文只保存指针锚，不复制原文。"
        if req_doc
        else "req-doc: MISSING\n\n本设计文档尚未绑定 requirement_doc，check_completeness 会将新流缺锚判为 FLAG。"
    )
    requirement_face_status = "filled" if req_doc else "unwritten"
    requirement_doc_cell = f"`{req_doc}`" if req_doc else "MISSING"
    todo_register_block = (
        f"""
## Todo Register

```todo_register
{todo_register}
```
"""
        if todo_register is not None
        else ""
    )

    return f"""# Design Doc：{task_id} / {req_id}

## 头部元数据

| 字段 | 值 |
|---|---|
| T-id | {task_id} |
| req_id | {req_id} |
| semantic_slug | {slug} |
| phase | {phase} |
| version | v1 |
| 日期 | {today} |
| type | {task_type} |
| label | {label} |
| PromptRef | {prompt_ref} |
| d9_contract | on-demand-v1 |

## (0) 原始需求锚

{req_anchor}

### 0.1 dispatch 原文快照（参考，不是真源）

以下内容由 `design_doc_scaffold` 通过 `todo dispatch {task_id}` 注入，只用于写作时快速定位。需求真源以 req-doc 指针为准。

````text
{original_prompt}
````

## §需求面

> 本面只放 requirement_doc 指针和本次涉及需求索引，不复制逐字需求。

| 字段 | 值 |
|---|---|
| face_status | {requirement_face_status} |
| written_at | {today} |
| written_by | design_doc_scaffold |
| 设计需求 | `{req_id or "MISSING"}` |
| 执行需求 | `{task_id}` |
| requirement_doc 指针 | {requirement_doc_cell} |

## §意义面

> face_status 为 `unwritten` 时，本面占位合法；改成 `filled` 后必须填实并通过 DC1/DC6。Forbidden Read 契约：写意义面的 agent 不读 §设计面草稿，只读需求面指针、CROSS_DOMAIN_MEANING.md 条目和本任务授权输入。意义三层锚（跨域/协作/元层）见 `rules/meaning/INDEX.md`，正文在 `rules/meaning/CROSS_DOMAIN_MEANING.md`。

| 字段 | 值 |
|---|---|
| face_status | unwritten |
| written_at | unwritten |
| written_by | unwritten |
| 设计需求 | `<设计需求 req_id / requirement_doc 条目>` |
| 执行需求 | `<执行需求 todo id / dispatch 条目>` |
| 承接总领意义 | `<CROSS_DOMAIN_MEANING.md 条目编号，例如 1 或 A>` |

### M1 本域核心意义

- `<这个设计文档为什么存在，要补哪个上下文缺口>`

### M2 补哪类根局限

- `<a/b/c/d 或第一层必要条件；说明补什么局限>`

### M3 总领意义锚

- `<CROSS_DOMAIN_MEANING.md 中的 1-13 或 A/B/C>`

### M4 防哪种不良行为

- `<防 reward hacking、回显需求、自证完成、上下文断裂等哪类问题>`

### M5 意义到落地对应

- `<意义如何落到确定层槽位、外部 oracle、状态门或消费链>`

## §设计面

| 字段 | 值 |
|---|---|
| face_status | unwritten |
| written_at | unwritten |
| written_by | unwritten |
| 设计需求 | `{req_id or "MISSING"}` |
| 执行需求 | `{task_id}` |

### D9 层适用性与状态

> 当前契约按触发条件选择 Layer 2/3。D9 layer state 只允许 `required`、`not_applicable`、`unwritten`；`filled` 保留给独立的 face_status，不可混入本表。`required` 只有至少一个命名触发键为 `true` 时成立，全部为 `false` 时必须写 `not_applicable`；`not_applicable` 必须给出理由并逐项评估触发条件，`unwritten` 仍是不完整状态。触发评估只使用 `key=false` 或 `key=true` 的结构化值；checker 只检查结构，不判断理由质量。

| layer | state | reason | trigger_evaluation |
|---|---|---|---|
| Layer 2 | unwritten | `<required 或 not_applicable 的判定理由>` | `<multiple_paths=unwritten; handoff=unwritten; user_confirmation=unwritten; cross_file_impact=unwritten>` |
| Layer 3 | unwritten | `<required 或 not_applicable 的判定理由>` | `<existing_object_disposition=unwritten; implementation_writeback=unwritten; direct_multi_file_execution=unwritten>` |

## Layer 1 功能设计

> 本层对应 AAU 的 Requirement Anchor schema。当前契约始终要求成功效果和明确不做，并要求上面的 requirement_doc 锚点；核心问题、硬性约束、交付物槽位按任务需要填写，不作为所有任务的统一门槛。

### 1.1 核心问题(core_need)

- `<这个任务真正要解决的问题是什么>`

### 1.2 成功效果(success_effect)

- `<达到什么状态才算满足需求>`

### 1.3 硬性约束(hard_requirements)

- `<必须满足的约束、输入输出、边界、运行证据要求>`

### 1.4 明确不做(negative_requirements)

- `<本轮明确不做什么，避免设计发散>`

### 1.5 交付物(deliverable)

- `<最终必须产出的文件、工具、文档、回执或验证记录>`

## Layer 2 实现设计

> 占位：本层对应 AAU 的 Unit Anchor / Architecture，用来约束组件职责、行为边界和实现取舍。

### 2.1 架构概述/组件图

```text
<组件 A> -> <组件 B> -> <产物/验证>
```

### 2.2 各组件职责与边界(scope_in/scope_out)

| 组件 | 职责 (scope_in) | 禁读 (scope_out / forbidden_read) | skill_injection | 证据或接口 |
|---|---|---|---|---|
| `<组件>` | `<负责什么>` | `<不负责什么>` | `<skill 名，从 _DAO_ROUTING 选>` | `<路径/命令/接口>` |

### 2.3 关键设计决策(含为什么)

| 决策 | 选择 | 为什么 | 放弃的替代方案 |
|---|---|---|---|
| `<决策点>` | `<本轮选择>` | `<选择理由>` | `<不选什么及原因>` |

### 2.3b 设计来源与参考(provenance)

> 占位：决策表管「选了什么、为什么」，本节管「这个选择的依据从哪来」。任何借鉴外部/业界方案的关键设计都要在这里留一条可回溯的锚；纯第一性推导也要写明「第一性推导」，防漏报冒充无来源。重构时靠这里追溯之前成功设计的依据。来源类型四选一：业界实现 / 内部先例 / 第一性推导 / 用户指定。占位阶段（设计面 unwritten）可保留占位；设计面声明 filled 后本表须与决策表的关键决策对齐、不留占位。

| 设计点 | 来源类型 | 参考锚(名称+URL 或仓内路径) | 采纳了什么 | 与参考的差异 |
|---|---|---|---|---|
| `<对应哪个关键决策>` | `<业界实现/内部先例/第一性推导/用户指定>` | `<参考名+URL 或 仓内文件路径；第一性推导写"无外部锚">` | `<从参考里采纳了哪部分>` | `<与参考有意偏离的地方及原因；无差异写"直接采纳">` |

### 2.4 反过度工程化三问

- 这个机制是否同时服务多个核心失败模式，而不是只为一个边角问题加协议：`<回答>`
- 有没有更小、更确定的实现能满足同一证明义务：`<回答>`
- 新增复杂度是否有真实消费链和验证证据支撑：`<回答>`

## Layer 3 代码改动清单

> 占位：设计阶段先列计划，实现后回填实际 delta。它对应 AAU 的执行后产物审查，不用于提前自报完成。

### 3.1 新增(ADDED)

- `<路径>`：`<新增内容和原因>`

### 3.2 修改(MODIFIED)

- `<路径>`：`<修改内容和原因>`

### 3.3 删除(REMOVED)

- `<路径>`：`<删除内容和原因；没有则写“无”>`

### 3.4 变更前后对比表

| 对象 | 变更前 | 变更后 | 证据 |
|---|---|---|---|
| `<对象>` | `<before>` | `<after>` | `<路径 / 命令 / receipt>` |

## Final Boundary

| 字段 | 填写 |
|---|---|
| 状态 | DONE / PARTIAL / BLOCKED |
| 已覆盖 | `<本设计或实现已经覆盖的范围>` |
| 未覆盖 | `<当前未覆盖但仍在需求内的范围>` |
| 延后 | `<明确延后到后续任务的事项>` |
| 证据边界 | `<哪些结论有运行证据，哪些只是设计占位>` |
{todo_register_block}
"""


def create_scaffold(
    task_id: str,
    slug: str | None = None,
    out_dir: Path | str | None = None,
    req_doc: Path | str | None = None,
    todo_register: str | None = None,
) -> Path:
    task_id = normalize_task_id(task_id)
    if not task_id:
        raise ScaffoldError("missing T-id")

    dispatch_output = run_todo("dispatch", task_id)
    try:
        original_prompt, dispatch_metadata = parse_dispatch(dispatch_output)
        show_fields = parse_show(run_todo("show", task_id))
    except DispatchParseError as exc:
        raise ScaffoldError(str(exc)) from exc

    req_id = dispatch_metadata.get("req_id") or show_fields.get("Req", "")

    semantic_slug = normalize_slug(slug or "") or derive_slug(show_fields, task_id)
    target_dir = Path(out_dir).expanduser().resolve() if out_dir else DESIGN_DOC_DIR
    target = target_dir / f"{task_id}_{semantic_slug}.md"
    if target.exists():
        raise ScaffoldError(f"target already exists, not overwriting: {target}")

    target_dir.mkdir(parents=True, exist_ok=True)
    req_doc_text = str(Path(req_doc).expanduser()) if req_doc else ""
    target.write_text(
        render_design_doc(
            task_id,
            original_prompt,
            dispatch_metadata,
            show_fields,
            semantic_slug,
            req_doc=req_doc_text,
            todo_register=todo_register,
        ),
        encoding="utf-8",
    )
    return target


def record_receipt_best_effort(
    task_id: str,
    exit_code: int,
    target: Path | None = None,
    error: str = "",
    slug: str = "",
    req_doc: str = "",
) -> None:
    try:
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.insert(0, str(WORKSPACE_ROOT))
        from tools.tool_receipts import record

        normalized_task_id = normalize_task_id(task_id)
        meta = {
            "task_id": normalized_task_id,
            "caller": "design_doc_scaffold",
            "artifact_paths": [target] if target else [],
            "semantic_slug": slug,
            "req_doc": req_doc,
        }
        if error:
            meta["error"] = error
        record(
            "design_doc_scaffold",
        {"task_id": normalized_task_id, "slug": slug, "req_doc": req_doc},
            exit_code,
            meta=meta,
        )
    except Exception as exc:  # pragma: no cover - must never affect scaffold behavior
        print(f"warning: failed to record tool receipt: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a prefilled landing-pipeline design document skeleton from todo dispatch."
    )
    parser.add_argument("task_id", help="landing-pipeline T-id, for example T631")
    parser.add_argument("--slug", help="semantic kebab slug for the output filename")
    parser.add_argument("--out-dir", help="output directory; defaults to the landing design_docs directory")
    parser.add_argument("--req-doc", help="requirement_doc path anchor to write into §0")
    parser.add_argument(
        "--todo-register",
        help="literal todo_register fenced-block body to include; no schema parsing or todo hook is run",
    )
    args = parser.parse_args()

    target: Path | None = None
    try:
        target = create_scaffold(
            args.task_id,
            slug=args.slug,
            out_dir=args.out_dir,
            req_doc=args.req_doc,
            todo_register=args.todo_register,
        )
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if "not found" in str(exc):
            print(
                "hint: run `python3 tools/todo/todo.py list` to see valid task ids",
                file=sys.stderr,
            )
        record_receipt_best_effort(args.task_id, 1, error=str(exc), slug=args.slug or "", req_doc=args.req_doc or "")
        return 1

    print(f"created: {target}")
    record_receipt_best_effort(
        args.task_id,
        0,
        target=target,
        slug=args.slug or target.stem.split("_", 1)[-1],
        req_doc=args.req_doc or "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
