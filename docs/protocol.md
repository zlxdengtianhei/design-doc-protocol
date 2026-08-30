---
status: draft
---
# 设计文档协议：怎么填、填到什么算完（术·语义层，draft）

> 本协议自私有母仓迁出。文中 `tools/...`、`adhoc_jobs/...`、`rules/skills/...` 形态的路径是母仓内部证据锚，未随本仓发布；随仓代码在 `core/`，实验证据在 `docs/d3/`。

## 元数据

- **类型**：Draft Workflow（术·协议，给 `design_doc` 工具配语义层；不替代工具本身）
- **适用场景**：要为一个 landing-pipeline 任务写三层设计文档时——用 `design_doc` 工具生成骨架之后，怎么把三层填实、填到什么算完；复杂/跨文件设计前怎么准备（Designer Packet）；设计决定牵连别的文件时怎么传播（touched-by/canonical-for）；DDP 域自己做多轮迭代时怎么审查 Bad Behavior 风险 + 判 fresh-agent 可消费性。
- **证据**：bounded。done-criteria 对照 `design_doc` 工具的真实模板 + AAU `DESIGN_FINAL_v3` 双锚点结构定出；配套完成度检测器在 T631（20 个真实占位）+ 一份填实文档上验证过确定性判别。**未跨多个真实任务验证填写质量**。Designer Packet / touched-by / Bad Behavior 三节（v0.2）证据为本轮 dogfood：三节内容本身按其自己的纪律产出（先写 Designer Packet 草稿再写本文件、本次改动自身即 touched-by 传播的真实案例、写完后跑过一轮 Bad Behavior 审查），单实例，未跨多任务验证。意义面 / 三面异步两节（v0.3）锚到 T963 落地实现（commit `e4c7028ae`）和设计真源 `adhoc_jobs/context_infra_base_tooling_buildout_20260615/cross_domain_design_meaning_20260619/per_domain_design/ddp_DESIGN.md`，本节为协议补写，行为证据来自 `tools/design_doc/check_completeness.py` 与 `tools/design_doc/design_doc_scaffold.py` 当前实现。设计来源记录纪律节（v0.4，SGQ-14）为**本轮协议补写 + 骨架落地**：`design_doc_scaffold.py` 已加 §2.3b provenance 小节，行为证据 = 三态 check_completeness shell 验证（设计面 unwritten 占位被抑制 / filled 填实无 FLAG / filled 空表按 DC1 逐格 FLAG，证明 §2.3b 继承设计面状态门语义，判定中性）；证据边界诚实：**单轮落地，未跨多个真实任务验证 provenance 的填写质量**，"填实 vs 空泛"当前靠 regulator/第二方而非机械检测器。
- **配套**：确定层工具 `design_doc`（生成骨架，路径查 `tools/INDEX.md`；骨架 §2.3b「设计来源与参考(provenance)」由本协议「设计来源记录纪律」节指导填写）；完成度检测器 `design_doc` 的 `check_completeness`（残留占位 + 空泛填写的误差信号）；Designer Packet 历史模板 `adhoc_jobs/design_doc_protocol_loop_codex_20260501/prompts/designer_prompt_reconstruction.md`；touched-by/canonical-for 传播机制 `rules/skills/drafts/bestpractice_architecture_doc_design.md` §2.3；Bad Behavior 分类法 `rules/skills/workflow_controller_loop/references/BAD_BEHAVIOR_GUIDE.md`；测试用例 schema `rules/skills/workflow_real_task_test_case_design.md`。
- **日期**：2026-06-04 初版；2026-07-07 v0.2（Y 级兼容扩展）；2026-07-07 v0.3（T963 后续补写，Y 级兼容扩展）；2026-07-10 v0.4（SGQ-14 provenance 补写，Y 级兼容扩展，version-manager 校核确认 Y 级成立）；2026-08-19 v0.5（P4 D9 on-demand-v1 结构契约与确定性 checker 对齐）；2026-08-19 B1 repair（收紧当前 D9 状态和值词汇）。
- **v0.5 边界**：P4 只把 D9 的层状态和触发评估落到脚手架与确定性结构检查；当前 D9 layer state 只有 `required`、`not_applicable`、`unwritten`，trigger evaluation 只接受 `key=true|false`；没有协议效果、语义质量或真实任务成功的结论。
- **演进**：v0.1（2026-06-04 初版，三层填法 + DC1-DC4）→ **v0.2**（2026-07-07，UP-63/DDP-14/UP-67 三条 Y 级新增：Designer Packet 六要素预写纪律 / touched-by-canonical-for 传播纪律 / Bad Behavior 审查+fresh-agent 可消费性；三者均为新增可选节 + 补充 Final Boundary 验收维度，不推翻既有 DC1-DC4 结论，调用方无需改动既有三层填法）→ **v0.3**（2026-07-07，T963/e4c7028ae 后续补写：意义面 M1-M5 填法、三面异步写入纪律、DC1 状态门与 DC6 意义面填实检查；兼容新增，不要求旧单面文档重写）→ **v0.4**（2026-07-10，SGQ-14 一条 Y 级新增：「设计来源记录纪律」节，配套骨架 `design_doc_scaffold.py` 新增 §2.3b「设计来源与参考(provenance)」独立小节；新增可选节 + 骨架新表，不推翻既有 DC1-DC6 与三层填法，§2.3b 自动继承设计面 DC1 状态门语义，调用方无需改动既有填法。version-manager 校核依 workflow_version_evolution.md §2/§4 Skill 行确认 Y 级成立：新增可选节 + 骨架新表，无 X 级下游负担）。

## 目标（一句话）

`design_doc` 工具能生成一个三层骨架，但骨架里每个核心字段都是 `<...>` 占位。光有工具没有协议，结果就是骨架生成了、没人填——T631 那份 106 行设计文档里 20 个核心字段（问题是什么、目标态、约束、架构、决策、交付物）全是空占位，因为没有东西告诉 agent 怎么填、填到什么算完。这个协议补的就是这一层：什么时候用、三层各自填什么才算填实、用什么机械判据确认填完了。

## 边界（不做什么）

- 不替代 `design_doc` 工具（骨架生成、原文注入、receipt 都在工具里）。本协议只管骨架生成之后的语义层。
- 不规定具体任务的设计内容。给的是「填实 vs 空填」的判据和填写引导，不是替某个任务做设计。
- 不做 draft→production 晋级判定（`workflow_landing_to_production`）。设计文档填完 ≠ 产物 landed，后者看消费链。
- 完成度检测器（术）住在工具目录里，本协议按名引用、不内联实现。

## 何时用 design_doc

不是每个任务都要三层设计文档。触发条件（任一成立就值得写）：

- 任务涉及多文件 / 多组件 / 跨边界，实现路径不止一条、要先定架构再动手。
- 有「设计先于代码」价值的任务：先冻结目标语义和行为边界，避免实现时发散（双锚点的用途）。
- 要交接给另一个 agent（含 Codex）实现：设计文档是它的行为锚点。

反过来，单文件小改、机械替换、一条命令能验的任务不需要三层设计文档，写了反而是过度工程。

## 三层怎么填（对齐双锚点）

工具生成的骨架有三层 + Final Boundary。每层的填法和「填实」的样子：

**Layer 1 功能设计 = Requirement Anchor（收紧目标语义，防目标发散）。** 当前 on-demand-v1 契约始终要求成功效果和明确不做，并要求 `(0)` 的 `requirement_doc` 锚点；核心问题、硬性约束、交付物槽位按任务需要填写，不再作为所有任务的统一门槛。每一格回答的是「需求」不是「实现」：
- core_need：这个任务真正要解决的问题。一句话能说清，且能区别于「相邻但不同的问题」。
- success_effect：达到什么可观察状态算满足需求。要写成能判定的，不是「质量高」这种愿望词。
- hard_requirements：必须满足的约束、输入输出、边界、运行证据要求。
- negative_requirements：本轮明确不做什么。这一格空着是设计发散的高发口，必须填。
- deliverable：最终必须产出的文件 / 工具 / 文档 / 回执 / 验证记录，具体到名字。

**Layer 2 实现设计 = Unit Anchor（收紧行为边界，防行为发散）。** 先在 D9 层适用性表中逐项评估 `multiple_paths`、`handoff`、`user_confirmation`、`cross_file_impact`。任一触发时写 `required` 并填实架构、职责和决策；全部不触发时写 `not_applicable`，给出非空理由和逐项 `trigger=false` 评估。`unwritten` 仍表示不完整。触发后，架构图给组件流向；职责表每个组件写清「负责什么 / 不负责什么 / 路径接口」；决策表写「决策点 / 本轮选择 / 选择理由 / 不选什么及原因」。

**Layer 3 代码改动清单。** 先在 D9 层适用性表中逐项评估 `existing_object_disposition`、`implementation_writeback`、`direct_multi_file_execution`。任一触发时写 `required` 并填实 ADDED / MODIFIED / REMOVED 与 before/after；全部不触发时写 `not_applicable`，给出理由和逐项 `trigger=false` 评估。`unwritten` 仍表示不完整。设计阶段还没动代码时，路径要具体到计划文件（`tools/x/y.py`），不写 `<路径>`；没有 REMOVED 就写「无」，不留占位。

**Final Boundary。** 状态三选一（DONE / PARTIAL / BLOCKED）+ 已覆盖 / 未覆盖 / 延后 / 证据边界。这是诚实边界，不留空、不全声称。

### D9 on-demand-v1 状态契约

脚手架通过元数据 `d9_contract | on-demand-v1` 标记当前契约。D9 表固定包含 `layer`、`state`、`reason`、`trigger_evaluation` 四列，并各有 Layer 2、Layer 3 一行。`state` 只有三种语义：`required` 表示对应层必须有结构化内容，且至少一个该层命名触发键必须精确为 `true`；`not_applicable` 表示本轮没有触发且必须写理由，全部命名触发键为 `false` 时应使用此状态；`unwritten` 表示判定尚未完成，始终 FLAG。`filled` 只属于三面 `face_status`，不是 D9 layer state；触发评估只接受每个键的 `key=true|false`，不接受别名。checker 只判断字段、状态和触发值是否存在，并拒绝 `required` 与全 false 触发评估的矛盾，不评价理由是否有说服力，也不据此宣称运行效果。

当前文档必须同时满足成功效果、明确不做、需求锚和 Final Boundary。没有 `d9_contract` 标记的历史文档仍按旧规则读取，供历史追溯使用，但不会因此获得当前 on-demand-v1 的认证语义；历史格式无需批量迁移。

## 意义面怎么填（M1-M5 填法）**Beta**

本节只指导 `design_doc` 骨架里的 `## §意义面`，不是把需求原文换个说法，也不是提前写设计方案。意义面回答的是：这个设计记录为什么存在、补的是哪类 LLM/系统根局限、它如何承接总领意义并约束后续设计。

**填到根局限级**：每条意义要指向问题的窟窿或根局限，例如「fresh agent 拿不到完整上下文」「执行者不能自评够没够」「确定性记录不该占模型注意力预算」。不要把用户需求原文改写成「完成某需求」「支持某功能」放进 M1/M2；那会被 DC6 regulator 当作回显需求或空泛意义。

**引需求锚，不复制需求原文**：需求面已经承接 `requirement_doc` 指针和本次涉及需求索引，意义面只引用 req_id / requirement_doc 锚。不要把逐字需求复制进意义面，避免同一信息出现第二个真源。

**承接总领意义必须具体可查**：顶部表格的「承接总领意义」行必须含 `CROSS_DOMAIN_MEANING.md` 字样，并指向 `rules/meaning/CROSS_DOMAIN_MEANING.md` 的具体条目。当前 DC6 壳允许的编号合法集是 `1`-`13` 与 `A`/`B`/`C`；`filled` 状态下，该行没有 `CROSS_DOMAIN_MEANING.md` 或没有合法编号都会 FLAG。

**M1 本域核心意义**：一句话写清这个设计文档 / 这个域为什么存在，必须能区别于相邻域。例如 DDP 的 M1 不是「记录设计需求」，而是「给 fresh agent 重建完整上下文的权威载体」。

**M2 补哪类根局限**：写它补的是哪类根局限或第一层必要条件，可以用 `(a)/(b)/(c)/(d)` 这类根局限短码，但必须解释补什么缺口。M2 是正向补口，不是任务目标清单。

**M3 总领意义锚**：列出承接的 `CROSS_DOMAIN_MEANING.md` 条目编号，例如 `#1`、`#4`、`#7`、`#8`、`#10` 或新意义 `A/B/C`。M3 要和顶部指针一致；顶部指针给确定性壳定位，M3 给读者和 regulator 理解。

**M4 防哪种不良行为**：写这条意义在反向防什么，例如 reward hacking、回显需求、自证完成、上下文断裂、设计和意义各写各的发散。M4 与 M2 正交：M2 写补什么，M4 写防什么。

**M5 意义到落地对应**：写意义如何落到确定层槽位、外部 oracle、状态门、Forbidden Read 或消费链。DC6 regulator 会看 M5 是否真的对应 M2 标的局限，而不是泛泛写「提升质量」。

**当前 checker 对齐**：`tools/design_doc/check_completeness.py` 的 DC6 壳只在检测到三面骨架时启用；它检查三面存在、每面 `face_status`、设计/执行标签、意义面 `CROSS_DOMAIN_MEANING.md` 指针和 M1-M5 标题。`face_status` 当前可通过的值只有 `unwritten` 与 `filled`。协议语义上的 `draft` 表示草稿中间态，但在当前壳扩容前不要把 `draft` 写进 `face_status`，否则会被 `DC6_FACE_STATUS_INVALID` FLAG。

## 三面异步写入纪律 **Beta**

三面是 `§需求面`、`§意义面`、`§设计面`。异步写入不是「随便留空」，而是把不同时间 / 不同模型写入的面分开，让每一面有自己的状态、锚和完成门。

1. **分面写**：一次只改一个面。需求面更新 requirement_doc 指针和涉及需求索引；意义面只写 M1-M5；设计面才写 Layer 1/2/3 与 Final Boundary。异步性可以用 `git diff` 区块隔离验证：本轮只动哪一面，应能在 diff 里看出来。
2. **后写引先写**：意义面引用需求面锚，不复制需求原文；设计面后写时，Layer 1 的 `core_need` 要能回链到意义面 M1/M2，而不是独立漂移成另一套目标。
3. **写意义面 Forbidden Read 设计草稿**：复用 v0.4 `DESIGNER-CONTRACT.md` 的 Forbidden Read 语义。写意义面的 agent 只读需求面指针、`rules/meaning/CROSS_DOMAIN_MEANING.md` 条目和本任务授权输入，不读 `§设计面` 草稿，防止先看设计再倒推意义。意义三层锚（跨域/协作/元层）见 `rules/meaning/INDEX.md`。
4. **face_status 当前落地值**：`unwritten` 表示本面尚未写，可合法保留 `<...>` 占位；`filled` 表示本面声明已填实，DC1 会检查该面残留占位，DC6 会检查意义面结构与指针。`draft` 作为协议语义保留给未来壳扩容；当前不要写入 `face_status`。
5. **DC1 状态门**：T963 后 DC1 不再是全文无占位，而是状态门：有三面状态时，只对 `filled` 面报 `DC1_PLACEHOLDER`；`unwritten` 面留 `<...>` 合法。没有三面骨架的旧文档仍走旧式占位检查。
6. **完成信号外置**：三面都填了也不靠作者自报。完成仍要跑 `design_doc` 的 `check_completeness`，由 DC1/DC2/DC5/DC6 的确定性壳和 DC3/DC4/DC5/DC6 的 regulator 共同给外部误差信号。

## 复杂设计前的准备：六要素 Designer Packet 草稿（UP-63）

三层骨架假设权威源边界已经想清楚——但一个设计任务如果牵涉 ≥2 个 Authority Target（哪个文件是权威源、要往哪几处写），或者本身就是跨文件传播，直接上手填 Layer 1/2/3 容易把还没想清楚的边界写死。这一节补的是三层骨架**之前**的准备动作。

**何时起草**：满足"何时用 design_doc"的触发条件之外，再加一条——本任务识别出 ≥2 个 Authority Target，或本任务的决定会牵连其它文件的行为/契约。只满足这条不满足"何时用 design_doc"本身的，不需要走三层骨架，草稿完就地关闭。

**六节结构**（历史模板见 `adhoc_jobs/design_doc_protocol_loop_codex_20260501/prompts/designer_prompt_reconstruction.md`，本节是按当前仓库规模的精简版，不是原样照搬）：

1. **Prompt Atoms**：把用户原话拆成可追溯的原子，每条标 requirement/decision/constraint/question/instruction 五种之一。
2. **Baseline Constraints**：写之前必须遵守的既有约束——已有字段名、路径约定、结构协议、语义不变式，每条注明来源文件或来源理由。
3. **Concept Modules**：每个概念给「用户需求 → 需求本质 → 设计 → 边界」四段（与 UP-73/DDP-13 的四段结构一致，不是重造）。
4. **Authority Targets**：`target-id / canonical-for / candidate-file / reason / touched-by` 五列表——哪个文件是这个概念的权威源，改了它之后哪些文件要跟着检查（touched-by 具体纪律见下一节）。
5. **Pending Decisions**：没有阻塞项写「无阻塞待裁决项」；有阻塞项列 `decision-id / issue / options / why blocked / affected-write-blocks`。
6. **Write Blocks**：`block-id / target / content / must-include-tokens / blocked-by`——具体要写哪块内容到哪个文件，写完这节才开始真正填三层骨架。

**这份草稿是什么、不是什么**：它是丢弃型中间产物（放在临时位置，不进 git 权威区），帮设计者把边界想清楚；写完六节之后，Concept Modules 喂 Layer 1/2，Authority Targets 喂 Layer 2 决策表和下一节的传播纪律，草稿本身不当作交付物保留、不算入 Final Boundary 的"已覆盖"证据。

**已知陷阱 T5（Designer Packet 变成新权威层）**：把六节草稿当成比三层骨架更权威的东西，后续设计变更去改草稿而不改正式骨架——草稿只在写之前用一次，写完就过期，权威永远在 design_docs/ 正式文件。

## Authority Targets 的传播纪律：touched-by / canonical-for（DDP-14）

用户原话点名了这件事该谁管："因为这涉及到 touched by 权威源等地方的写入，这是 process doc 在拿到设计文档后，由 design doc protocol 负责执行的写入任务。"——Authority Targets 表里已经有 canonical-for 和 touched-by 两列，但光填表不传播，等于没做这件事。

**触发**：Layer 2 决策表任何一条决策的影响范围超出本设计文档本身（会改变别的文件的行为、契约或读取路径）时触发。

**怎么做**（复用 `bestpractice_architecture_doc_design.md` §2.3 的三层协议，按引用不复制实现）：
1. **canonical-for**：这个决策涉及的概念，权威源是哪个文件——一个概念只能有一个权威源。
2. **touched-by**：改了权威源之后，哪些文件的契约块需要跟着检查/更新——具体到文件路径，不写"相关文件"这种空泛话。
3. **契约块**：在每个 touched-by 文件里留一段 `→ <概念名>` 格式的契约块，写清楚"本层对该概念的义务/限制"+ 指向权威源的链接，不复制权威源的完整定义。

**Final Boundary 新增一项**：touched-by 列表里的文件是否都已经完成传播（契约块已写/已核对），不是"Authority Targets 表填了 touched-by 列就算完工"。未传播完的 touched-by 项在 Final Boundary 里必须显式标"延后"，不能沉默略过。

**边界（不做什么）**：本节不重建历史 6-Phase Protocol 的 Designer/Checker/Decomposer/Writer/Propagator/Reviewer 五角色分工——那是 `design_doc_protocol_loop_codex_20260501` / `designdoc_protocol_round1_claude_code_20260501` 的实验性 Round，已被本仓库当前更轻量的 `design_docs/` + `tools/ddp/` 模型取代，不再复活。本节只吸收 touched-by 传播的判据和契约块格式，不吸收那套角色分离的运行时机制。

## 多轮迭代时的 Bad Behavior 审查 + fresh-agent 可消费性（UP-67 / DDP-16）

用户原话："每轮记录 Bad Behavior 风险：reward hacking、局部最优、自证完成、fresh-agent consumability、是否需要推翻重建。命中风险时必须影响下一步反应。"DDP-16 进一步把 fresh-agent consumability 从风险检查项升格为正向验收目标。

**触发**：DDP 域自己做多轮迭代式协议/skill 重建工作时（同一个设计对象跨多个 session/round 反复修改，例如一次改动同时牵涉三份以上文件、或分多轮逐步定稿的场景），在每个轮次边界跑一次 Bad Behavior 审查。单轮次、单文件的小改不触发。

**怎么审查**：不新造分类法，按名引用 `rules/skills/workflow_controller_loop/references/BAD_BEHAVIOR_GUIDE.md`（12 方向、36 条具体表现、审查输出 schema 该文件已定义）。DDP 场景重点覆盖：
- **D01 需求锚定**（BB-01/02/13）：多轮修改后原始需求是否还锚得住，有没有偷偷发明验收标准。
- **D04 完成替代**（BB-05/10/11）：机制成功（骨架生成、检测器 exit 0）有没有被当成任务成功。
- **D05 评价完整性**（BB-20/25/26）：自检有没有替代第二方判断，语义判断有没有被结构化分数偷换。
- **D12 收束与实验控制**（BB-15/29/35）：closure 有没有只依赖单一 agent/单一视角。

命中任何条目，按 BAD_BEHAVIOR_GUIDE 的 reaction 集合（keep/rerun/rollback/discard/rethink/redesign_test/await_user/block）之一处理，不能只记录不改变决策（BB-31）。

**fresh-agent 可消费性（正向验收项，不只是风险提示）**：一份要交给另一个 agent（含 Codex）执行的设计文档，Final Boundary 里必须有一条独立判断——一个没有先验上下文的新 agent，仅凭这份文档能不能真的把活干出来。这条判断不能由撰写者自己勾选："能" / "不确定"两种情况里，"不确定"或命中 fresh-agent consumability 风险时，验收门控必须补一份独立 fresh-agent E2E 通过证据（真的派一个不知情的 agent 拿文档去执行，看它是否卡在缺上下文），不能用撰写者的自我评估替代。

**已知陷阱 T6（fresh-agent 检查被自报替代）**：撰写者在 Final Boundary 写"fresh-agent 可消费：是"但从没有真的找一个无先验 agent 试过——这条判断和 DC3/DC4 一样必须过第二方（regulator 或真实 fresh-agent 试跑），不能自报作数。

**当前边界**：本节暂不新增 DCx 编号机械化检测——`check_completeness.py` 的 DC5 已用于 unit 职责隔离，DC6 已由 T963（意义面/三面异步互补设计，commit `e4c7028ae`）落地为意义面填实检查。Bad Behavior 审查和 fresh-agent 可消费性目前仍只是 Final Boundary 清单项 + 按名引用的判据，不与 DC6 合并：DC6 管意义面是否填实、是否回链设计面；Bad Behavior / fresh-agent 清单项管设计产物是否可消费、是否需要独立 E2E。二者语义不同，保留为独立 Final Boundary 清单项；机械化检测器留给未来独立检测器或后续 DC 编号。

## 设计来源记录纪律（provenance，SGQ-14）**Beta**

用户原话点名了这件事的目的："对于设计文档中的所有设计方案，我认为必须明确记录『设计的来源』——即为什么要这样设计。如果在设计时参考了一些业界比较优秀的实现方案，必须将这些参考来源记录下来，并在设计文档中作为一个独立的部分呈现。目的是后续调整或重构时，依然能够追溯到之前成功设计的依据，从而进行更综合的评估和考虑。"——骨架 §2.3b「设计来源与参考(provenance)」就是这个"独立的部分"的落点；本节给它的填写纪律。

**这一节管什么、不管什么（与 Layer 2 决策表的关系）**：决策表（§2.3）管"选了什么、为什么选它、放弃了什么"——它是**决策的横切面**；provenance 表（§2.3b）管"这个选择的依据从哪来"——它是**依据的溯源面**。两者正交、不重复：决策表的"为什么"是本轮的权衡逻辑（在当前约束下为何这个选择更优），provenance 的"来源"是这个逻辑站得住的外部/历史支点（业界某实现这样做过、内部某先例验证过、或纯第一性推导）。不要把决策表的理由复制进 provenance，也不要把来源锚塞进决策表撑宽表格。

**何时必填**：设计面进入 `filled` 状态时，每个进了决策表的**关键设计决策**都要在 §2.3b 有对应的一条来源。触发不限于"借鉴了业界方案"——三种情形都要写：
- **借鉴外部/业界方案** → 来源类型「业界实现」，参考锚给名称 + URL（论文/开源项目/文档/RFC）。
- **沿用内部已验证做法** → 来源类型「内部先例」，参考锚给仓内文件路径 + 该先例的验证证据位置。
- **纯第一性推导**（没有外部或内部先例，从问题本身推出）→ 来源类型「第一性推导」，参考锚写"无外部锚"并一句话说清推导依据。**纯推导也要显式写明，不能留空**——留空无法区分"确实是原创推导"和"忘了记来源"，后者正是重构时追溯断链的根因。
- **用户直接指定** → 来源类型「用户指定」，参考锚指向需求逐字真源的对应块（如 `REQUIREMENTS_VERBATIM_*.md` 块号）。

**填实判据（反例导向）**：每条来源必须可回溯到**具体锚**——一个能点开的 URL、一个仓内文件路径、或需求真源的具体块号。反例（判为空泛，应 FLAG）：泛泛写"参考了业界最佳实践""借鉴了成熟方案"而没有具体是哪个实现、哪篇文档、哪个项目。这类无锚描述在重构时等于没记，因为后人无法据此回到"之前成功设计的依据"。"采纳了什么"要写清从参考里具体吸收了哪部分（不是整个照搬时尤其要写明边界）；"与参考的差异"要写清有意偏离的地方及原因（直接照搬则写"直接采纳"），这一列是防止把参考当圣经、丢失本地约束适配的关键。

**重构时的消费方式（用户原话的目的落地）**：当后续 session 要调整或重构某个设计时，先读 §2.3b——它回答"当初为什么这样设计、依据是什么、和参考差在哪"。有了来源锚，重构者能做三件决策表本身给不了的判断：(1) 回到原始参考看它是否已演进（业界实现是否有更新版本、内部先例是否已被推翻）；(2) 判断当初的"与参考的差异"是否仍然成立（本地约束是否变了）；(3) 在"更综合的评估"里把原始依据和新证据一起权衡，而不是在真空里重做决策。这就是把"独立部分呈现"从一个格式要求变成一个可消费的追溯接口。

**与确定层的当前关系**：§2.3b 落在设计面，因此**自动继承 DC1 状态门语义**——设计面 `unwritten` 时表内 `<...>` 占位合法（异步留白）；设计面声明 `filled` 后，空 provenance 表的占位会被 DC1 逐格 FLAG（给 field:line），与其它设计面字段完全一致。本轮**不新增 DCx 编号**做"来源锚可解析性"的语义校验（来源类型是否合法四选一、参考锚 URL/路径是否真能解析、是否泛泛无锚），那属于 regulator 语义判断或未来独立检测器的范围，记录为深水区。当前 provenance 的"填实 vs 空泛"判断，与 DC3 回显需求判断同源，靠 regulator 或第二方，不靠撰写者自报。

**已知陷阱 T7（provenance 退化成空泛口号）**：把 §2.3b 填成"参考业界最佳实践"这类无锚句子——确定层查不出（不是 `<...>` 占位了），但重构时追溯断链，等于没记。这条和 T2（回显需求）同构，靠 DC3 同级的 regulator 判，或在 Final Boundary 里由第二方复核每条来源是否真有可点开的锚。

## 完成判据（可机械查，是这个协议的硬核）

一份设计文档「填完了」要全过下面，缺一不算完。确定性壳负责结构、占位、状态和指针；regulator 负责空泛、决策回链、职责隔离与意义质量：

- **DC1 状态门占位检查**：旧单面文档仍按残留 `<...>` 报 `DC1_PLACEHOLDER`；三面骨架文档按 `face_status` 走状态门，只对 `filled` 面查占位，`unwritten` 面留 `<...>` 合法。这一条挡住 T631 那种已声明填完却留占位的空骨架，同时不阻断三面异步留白。
- **DC2 当前契约的必填格不空**：`success_effect`、`negative_requirements`、需求锚和 Final Boundary 状态行始终需要非空内容；D9 中标为 `required` 且至少一个命名触发为 `true` 的 Layer 2/3 才分别要求决策表或代码改动清单，全部触发为 `false` 却写 `required` 会 FLAG；`not_applicable` 必须有理由和触发评估，`unwritten` FLAG。没有 D9 标记的历史文档仍按兼容路径检查旧五格和决策表，不取得当前契约认证。确定性可查（结构层）。
- **DC3 不是回显需求**：填的内容是真设计，不是把原始 prompt 换个说法抄一遍。比如 success_effect 给的是可判定的状态，不是「完成这个需求」；决策表给的是真选择 + 真理由，不是复述任务描述。这一条要第二方（regulator）判，确定性壳判不出空泛。
- **DC4 决策可回链**：Layer 2 每个关键决策有理由 + 明确「不选什么及原因」（双锚点的行为收紧落到纸面）。regulator 判。
- **DC5 unit 职责隔离**：Layer 2 的 component responsibilities / boundaries 要有真实职责隔离和 forbidden_read 边界。壳检查 skill_injection / forbidden_read 的基本结构，regulator 判 unit 职责是否语义重叠、scope_out 是否只是 scope_in 的反话。
- **DC6 意义面填实**：检测到三面骨架时，壳检查三面齐、每面 `face_status`、设计/执行标签、意义面 `CROSS_DOMAIN_MEANING.md` 指针和 M1-M5；regulator 判意义面是否说明根局限 / 上下文缺口，是否回显需求或设计计划，以及设计面 `core_need` 是否能回链意义面。

**收口调用**：设计文档填完跑 `python3 tools/design_doc/check_completeness.py <设计文档路径> --regulator --regulator-tier codex:high`：DC1/DC2/DC5/DC6 的壳面给确定性 verdict（残留占位、空格、缺状态/标签/指针、非法编号 → FLAG，给字段:行号），DC3/DC4/DC5/DC6 的 regulator 喂文档判空泛、决策回链、职责隔离与意义质量。完成判断不让写文档的 agent 自己勾，过检测器或第二方。

**Final Boundary 补充项（触发时生效，不是每份文档都要）**：touched-by 传播是否完成（见「Authority Targets 的传播纪律」节，未传播完须显式标延后）；fresh-agent 可消费性判断是否给出且非撰写者自报（见「多轮迭代时的 Bad Behavior 审查」节，命中风险须补独立 E2E 证据）。这两项不占用 DCx 编号，是 DC1-DC6 之外的独立清单项，只在各自触发条件成立时才是必填。

## 方法论建议（可按情况调整）

- **先填 Layer 1 再填 Layer 2**：目标语义没冻结就写架构，架构会跟着模糊目标飘。双锚点是有序的——先收目标（Requirement Anchor），再收行为（Unit Anchor）。
- **negative_requirements 和「不选什么」是边界，不是凑数**：这两格最容易留空，但它们恰恰是设计文档防发散的主要价值。空着等于没设错边界。
- **设计阶段 vs 实现后**：设计阶段 Layer 3 写「planned 改动 + 具体计划路径」，实现后回填真实 path + before/after。两个阶段都不留 `<...>`。
- **设计文档不混协议**：一份设计文档只描述「这个任务怎么设计」，不把通用流程/协议写进去（协议独立化，见陷阱 T3）。

## 已知陷阱（来自真实案例）

- **T1 骨架生成即停**：工具 exit 0 生成了骨架，agent 把「骨架存在」当成「设计完成」就停。T631 是标本：106 行里 20 个核心字段是 `<...>`，确定层跑了、语义层没填。修法是 DC1 状态门——旧单面文档有 `<...>` 残留不算完成；三面文档只有 `filled` 面承诺完成后才允许被占位门追责，`unwritten` 面可异步留白。
- **T2 填了但空泛（回显需求）**：把 `<...>` 替换成「解决这个问题」「让它正常工作」这种没信息量的话，确定性检测器查不出（不是 `<...>` 了），但等于没填。靠 DC3 的 regulator 判：填的是真设计还是换个说法抄需求。
- **T3 设计文档与协议混写**：把通用工作流/协议内容写进具体任务的设计文档，导致文档臃肿且协议无法复用。正解是协议独立成 skill（就是本文件），设计文档只写本任务的设计。
- **T4 不信 builder 自报检测器**：完成度检测器实现交出去后，它报 PASS 不作数。亲自重跑 + 亲读，确认确定性壳真扫了占位、regulator 隔离成立（同 `workflow_complexity_drift_detection` T5）。
- **T5 / T6（2026-07-07 新增，详见各自小节）**：T5 Designer Packet 变成新权威层（草稿被当成比正式骨架更权威，后续改草稿不改正式文件）；T6 fresh-agent 检查被自报替代（Final Boundary 写"可消费"但没真的找无先验 agent 试过）。两条分别挂在「六要素 Designer Packet」和「Bad Behavior 审查」小节下，此处只做索引。
- **T7（2026-07-10 新增，详见「设计来源记录纪律」小节）**：provenance 退化成空泛口号（§2.3b 填"参考业界最佳实践"这类无锚句子，确定层查不出但重构追溯断链）。与 T2 同构，靠 DC3 同级 regulator 或第二方复核每条来源有可点开的锚。

## 输出规格

- 设计文档落在工具固定目录 `adhoc_jobs/landing_requirement_decomposition_20260531/design_docs/<T-id>_<slug>.md`（工具生成，本协议指导填写）。
- 完成度检测器 `tools/design_doc/check_completeness`（路径查 `tools/INDEX.md`）：确定性扫 DC1/DC2/DC5/DC6（状态门占位、必填空格、职责边界结构、三面/意义面结构 → 给字段:行号），regulator 喂全文判 DC3/DC4/DC5/DC6。
- regulator 后端按名引用 `cli_agent` 路由。
- Designer Packet 草稿（触发时）：写在任务自己的临时/scratch 位置，不进 `design_docs/` 权威区，写完即可丢弃或随任务证据一并归档，不单独注册。
- touched-by 契约块（触发时）：写在被牵连文件里自己的位置（不新建集中登记文件），格式见「Authority Targets 的传播纪律」节。

## 跨域根与联系

- 双锚点（Requirement Anchor 收目标语义 / Unit Anchor 收行为边界）：来自 AAU `DESIGN_FINAL_v3`，三层结构是它的工程投影（USER.md 的功能/实现/代码改动三层偏好）。
- 语义层必须配确定层完成信号否则被跳过：来自本轮诊断（确定层有完成信号、语义层没有，agent 滑向有信号的一侧；T631 是最干净证据）。
- 完成判断要可操作（指出哪个字段:行号没填，不是「填得不够」）+ 由第二方判：来自可验证 checkpoint 实验 + 开环控制。
- Designer Packet 六要素（UP-63）：历史模板 `adhoc_jobs/design_doc_protocol_loop_codex_20260501/prompts/designer_prompt_reconstruction.md`；六要素结构本身源自已废弃的 6-Phase Protocol 实验轮，本文件只吸收输出格式，不吸收角色分离运行时。
- touched-by / canonical-for 传播（DDP-14）：机制按引用复用 `rules/skills/drafts/bestpractice_architecture_doc_design.md` §2.3（权威源/契约块/依赖头三层协议），该文件原为 NightCode 目标系统而写，本文件只借传播判据和契约块格式，不借其目录结构。
- Bad Behavior 分类法（UP-67）：按引用复用 `rules/skills/workflow_controller_loop/references/BAD_BEHAVIOR_GUIDE.md`（12 方向/36 条），不新造第二套分类。
- fresh-agent E2E 独立验证（DDP-16）：概念上与 `workflow_real_task_test_case_design.md` 的 read_isolation / reviewer_visibility 思想一致（执行者与验证者看到的材料不同），需要真实验证时按该 skill 的 schema 设计验证 case。
- 与 T963（DC6 意义面/三面异步互补设计，源 `cross_domain_design_meaning_20260619/per_domain_design/ddp_DESIGN.md`）关系：T963 已在 commit `e4c7028ae` 落地 DC6 意义面填实检查与 DC1 状态门；本文件的 Bad Behavior / fresh-agent 内容仍不占用 DC6 编号。核对结论：不合并 Final Boundary 清单项。DC6 管意义面填实质量和设计面回链，Bad Behavior / fresh-agent 清单项管多轮协议产物的可消费性和独立验证义务，语义不同，保留为清单项；机械化检测器留给未来独立检测器或后续 DC 编号。
- 配合：检测器有效性标准 → `workflow_complexity_drift_detection`（V1–V6）；遇阻判断 → `workflow_manage_unexpected`；产物是否真 landed（设计完 ≠ landed）→ `workflow_landing_to_production`；具名任务/phase 收口报告 → `bestpractice_final_report`。
