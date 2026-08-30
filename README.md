# Design Doc Protocol (DDP)

三层设计文档的脚手架，加一套确定层与语义层分离的完成度检测器，附带一套诚实的证据纪律。

> **诚实定位**：这不是「被验证有效的设计方法论」。「跨 session 持久化的多层设计文档」对实现质量的影响，在本仓写作时（2026-08）尚无任何已发表研究测量过，本仓自己的验证实验也只产生条件性证据（见「测试结果」节）。我们把脚手架、检测器和验证方案一起开源，邀请复现与批评。
>
> **协议结构可能随三层拆分终裁调整**：三层（功能设计/实现设计/代码改动清单）的存废是开放问题，本仓的逐层剥离实验结果只对该问题提供条件性证据。

## 它解决什么

设计文档的失败模式不是没人会写，而是两类：

1. **骨架生成了、没人填**：核心字段留着占位符就宣称完成。确定层检测器（DC1/DC2 等）对这类失效给字段:行号级的可操作误差信号。
2. **填了但空泛**：把需求换说法抄一遍当设计。这类失效机械判不出，交给独立语义判定者（regulator，DC3-DC6），判定者只看编号后的文档本身。

## 组成

- `core/design_doc/design_doc_scaffold.py`：三层骨架生成（双锚点：功能设计=需求锚，实现设计=单元锚）。
- `core/design_doc/check_completeness.py`：完成度检测器。确定性壳（占位状态门/必填空格/结构谓词）+ 可选的语义调节器调用。
- `core/ddp/`：领域产物投影（DDP_ARTIFACT）组装与检查门。
- `docs/protocol.md`：三层怎么填、填到什么算完的协议（语义层）。
- `core/design_doc/CHECK_COMPLETENESS_SPEC.md`：检测器的输入/输出/判别契约。

## 测试结果

功能描述逐条附证据：

**确定层壳的判别力**（`core/design_doc/run_oracle.py --reps 0`，rc=0）：

| 样本 | 期望 | 实际 |
|---|---|---|
| 真实空骨架文档（106 行 20 个核心占位 + 空决策表 + 空状态行） | FLAG | FLAG（34 占位逐条定位 + 空表 + 空状态） |
| 填实文档（本工具的自设计文档） | PASS | PASS |
| DC3 软负样本（占位清零但内容是需求回显） | 壳 PASS、调节器 FLAG | 壳 PASS、调节器 FLAG |

**语义判定的判别力**（原 DC7 义务降级进调节器后的正负样本对照）：正样本（设计面自称实现行为的权威定义）壳 PASS 而调节器精确 FLAG；负样本（reference-only 表述）双 PASS。判别责任移交而非丢失。

**逐层剥离实验**（三层结构的条件性证据，诚实呈现「有效性尚未被证明」）：实验设计为三臂（A 三层全有 / B 去实现设计层 / C 直接实现）× 两任务 × 重复 2 次。**结果：未产出可解释证据。** 任务 T2（commit-0/tinydb，greenfield 多模块）六格全 PASS（200/0），但双盲 judge（gpt-5.6-sol）独立观察 + md5 双证显示六格最终产物逐字复现 PyPI 官方 tinydb 4.8.0——worker 形态无工具无网络，唯一解释是模型训练数据记忆——三臂无可见差异，属记忆 ceiling 压平协议作用，非「Layer 2 无用」的证据。任务 T1（SWE-bench Lite pytest-7490，brownfield）六格结构性缺失：415KB prompt 超过传输层 argv 天花板（OS E2BIG ~131KB）且全部大 context 通道配额死亡，无有效运行。故跨任务外推不可用，单任务内亦因 ceiling 无方向信号。完整读数、归因与复现命令见 `docs/d3/ABLATION_RESULT.md` 与 `docs/d3/SOL_D3_JUDGE_VERDICT.md`（随仓发布）。实验为小样本条件性证据，不构成「协议有效/无效」的普遍结论。

**检测器自身测试**：在本仓根目录跑 `python -m pytest core/design_doc/tests core/ddp/tests -q` = **91 passed, 7 skipped**（2026-08-30，Python 3.13）。7 个 skipped 全是「未随本仓发布的母仓集成面」测试（requirement_doc 集成 ×3 文件、phase_runtime 门禁登记 ×2、回执台账链 ×1、intake CLI 集成 ×1），在母仓布局下它们照常运行（该面全量基线 100 passed, 1 skipped）。判别力 oracle：`python core/design_doc/run_oracle.py --reps 0` rc=0（真实空骨架 FLAG、填实文档 PASS、DC3 软负样本壳 PASS 而调节器 FLAG）。

## 已知集成面（当前版本的边界）

- **语义调节器后端**假定一个「给编号文档回 JSON 判词」的可替换契约；仓内实现绑定一个内部 CLI router，外部使用需自带等价后端（契约见 `core/design_doc/CHECK_COMPLETENESS_SPEC.md` §4）。调节器后端缺席时工具照常工作，语义项报告为 UNKNOWN 而不是假装判过。
- **未随仓发布的母仓集成面**（调用时显式报错或明示跳过，不静默）：`requirement_doc`（需求文档子系统；`intake.record_requirement` 与 `check_artifact` 的 DA2.RD 子检查依赖它——后者在缺席时报告「未运行」而非判红）、`tool_receipts`（调用台账；缺席时降级为不记录并在回执 dict 里如实标注）、`phase_runtime` 门禁登记面。
- **目录约定**：scaffold 的默认设计文档目录经 `DDP_DESIGN_DOC_DIR` 环境变量配置，缺省 `<仓根>/design_docs/`；dispatch 文本注入的解析器已随仓（`core/dispatch_parse.py`），todo CLI 落盘路径属母仓布局，独立使用时以注入文本方式提供需求。
- `core/gatekit/` 为确定层门禁框架的 vendored 副本（来源与日期见文件头注释），与母仓同演进。

## License

MIT（见 `LICENSE`）。
