# ABLATION_RESULT · D3 三层拆分逐层剥离实验（降级收口 · T2-only）

- 席：ddp-opt（第 5 棒 glm-ollama，承接 R1-R5）；日期：2026-08-30
- 上游：`PREREGISTRATION_D3.md`（预注册 + AMENDMENT-A1 + DEVIATION-01..06）、`PACKET_DDP` D3、RULINGS 块 B/E
- 判词：`verdicts/SOL_D3_JUDGE_VERDICT.md`（Sol 双盲，gpt-5.6-sol）
- 收口形态：DEVIATION-06 降级收口。T1 六格结构性缺失，本报告只承载 T2 单任务可读数，跨任务外推不可用。

## 结论卡

**D3 未产出可解释证据回答实验问题（Layer 2 边际贡献是否为正）。** 两个任务都未能提供有效数据：T1（pytest-7490，brownfield 文献可比锚）因 415KB prompt 撞传输层 argv 天花板（OS E2BIG ~131072B < 415486B）且全部 415KB-capable 通道配额死亡，六格结构性缺失；T2（commit-0/tinydb，greenfield 多模块）六格虽全 PASS（200/0），但 Sol 双盲 judge 独立观察 + md5 机械双证显示六格最终产物逐字复现 PyPI 官方 tinydb 4.8.0（worker 形态无工具无网络，唯一解释是 deepseek-v4-pro 训练数据记忆），三臂无可见差异，M4/M5/M1 全部 ceiling。这是任务选定与 worker 模型记忆的交互所致，**不构成"协议有效/无效"的普遍结论**，也**不构成"Layer 2 有用/无用"的任何方向证据**。三层取舍终裁归用户（`USER_DECISION_PENDING`）。

## 实验问题与结论边界（预注册 §1，冻结）

问题：DDP 三层设计文档中，**实现设计层（Layer 2）对实现质量与成本的边际贡献是否为正**。

结论边界：只产条件性结论 + 建议；不回答、不得被引用为"DDP 有效/无效"普遍结论。本报告进一步收窄：因 T1 缺失 + T2 记忆 ceiling，连"条件性方向"都给不出，只能给"本次设计下无可解释证据"的诚实空结论与归因。

## T2 每格读数（M1-M5）

| 格 | 臂 | rep | M1 遗漏 | M2 返工 | M3 成本 | M4 测试 | M5 judge（覆盖/架构/可运行/工程度） | 最终产物来源 |
|---|---|---|---|---|---|---|---|---|
| T2/A1 | A | 1 | 0 | 0 | wall 468s | 200/0 | 4/5/4/4 | ==官方 tinydb 4.8.0 |
| T2/A2 | A | 2 | 0 | 1 | wall 652s | 200/0 | 5/5/4/4 | ==官方 |
| T2/B1 | B | 1 | 0 | 1 | wall 719s | 200/0 | 4/5/4/4 | ==官方 |
| T2/B2 | B | 2 | 0 | 1 | wall 719s | 200/0 | 5/5/4/4 | ==官方 |
| T2/C1 | C | 1 | 0 | 0 | wall 274s | 200/0 | 4/5/4/4 | ==官方 |
| T2/C2 | C | 2 | 0 | 1 | wall 635s | 200/0 | 5/5/4/4 | ==官方 |

指标说明与诚实声明：
- **M1 需求遗漏=0（ceiling，非协议成果）**：六格产物 == 官方 tinydb，官方实现覆盖 R2.1-R2.9 全部条目，故遗漏 0。这是记忆复现的副产品，不是任何臂的设计活动产出的覆盖。
- **M2 返工**：A1/C1 一次过（0），A2/B1/B2/C2 经 1 轮修复（1）。需指出：修复轮的走向是从"原始变体首稿"收敛到"记忆中的官方实现"（work_r1 为较短变体、work_r2 为官方版），即 fix loop 在记忆任务上有"向记忆锚收敛"的倾向，n=2 不构成臂间结论。
- **M3 token 成本不可机械采集**：dsh/ollama-cloud 通道不回 token 用量，`route.json` 仅路由元数据、`progress.json` 仅活性心跳，均无 token 字段。以 receipt `wall_secs` 为成本代理（含失败首稿的墙钟，故 fix-round 格偏高）。这是预注册 §5 M3 采集路径的实测落空，如实声明。
- **M4 测试全 200/0（ceiling）**：六格全过，无区分。
- **M5 judge**：详见 `SOL_D3_JUDGE_VERDICT.md`。同 rep 内 X/Y/Z 分数一致；rep1 覆盖=4、rep2 覆盖=5 的差异经 hash 证为同一代码，属 judge 噪声非质量差异。

## 三臂对比条件性结论

在"任务（tinydb 4.8.0）处于 worker 模型（deepseek-v4-pro）训练数据中"这一条件下：
- 三臂（A 全三层 / B 去实现设计层 / C 直接实现）的最终产物逐字相同（md5 双证），M4 全 200/0、M1 全 0、M5 同 rep 同分，**臂间无任何指标可见差异**。
- 因此，**在本任务与本模型下，Layer 2 的有无不产生可观测的实现质量或成本差异**。但这是记忆 ceiling 压平了协议可能的作用，**不能外推为"Layer 2 无用"**，也**不能反向声称"Layer 2 有用"**。结论是空：本次数据不携带该方向信号。
- 唯一表现出臂间数值差的是 M2（B 臂两次都需 1 轮修复，A/C 臂各有一次 0 轮），但 n=2 且产物最终都收敛到同一记忆实现，该差异不构成 Layer 2 的证据，更像是记忆复现的随机收敛时序。

## n 与外推边界（诚实声明）

- n=2/格，单 worker 模型族（deepseek-v4-pro，T2 全程同族；T1 因通道墙未跑成，无 worker 数据）。
- 单任务有可读数（T2）；T1 结构性缺失。**跨任务外推不可用**（预注册 §1 结论边界 + DEVIATION-06：T1 缺失使跨任务外推不可用）。
- 即便在 T2 单任务内部，记忆 ceiling 使臂间无区分，故单任务内外推 Layer 2 作用也不可用。
- worker 运行时形态：T2 = dsh 一次性文本（无工具无网络，AMENDMENT-A1 §1），部分格经同组 fallback 到 dsh-ollama:pro（同模型 deepseek-v4-pro:0813，receipt 记回执）。T1 运行时形态因通道墙未定型。
- judge = gpt-5.6-sol（与 worker 不同族，与预注册 §6 一致）。

## 记忆污染发现（核心诚实残差）

**发现**：T2 任务（commit-0/tinydb，base `ed761a72`）的官方实现 tinydb 4.8.0 是知名 PyPI 库，deepseek-v4-pro 训练数据含其源码。六格最终产物 `tinydb/database.py` md5 全部 = `b2a5321ae50625cac693f56061ca3055`，与 PyPI 官方 4.8.0 逐字相同（`diff` rc=0）；`table.py` 六格 md5 全同（`19e99a8…`，769L，与官方同长、仅等价写法差异）。A1(A 臂)==C1(C 臂) 等跨臂逐字一致。

**独立印证**：Sol 双盲 judge 在不知臂、不知假设前提下，rep1 判"X/Y/Z 逐字一致…极强雷同或共同来源迹象"，rep2 判"几乎逐字一致…不能视为真正独立实现"（逐字见 verdict）。

**对实验的影响**：记忆复现使 M4/M1 触顶、M5 无臂间区分，T2 丧失区分协议臂的能力。这是任务选定（选了知名库的 Commit0 仓）与 worker 模型记忆的交互失效，属实验设计的可复算失效模式，如实登记。

**归因**：预注册 §2 T2 选择理由以"零第三方运行时依赖、10 模块全 stub、1890 行测试"为据，未把"tinydb 是否在主流代码模型训练数据中"纳入选择判据。这是本实验在任务选定上的盲点。Commit0 的奖励黑客防护（剥 .git、禁 clone）防的是 git history 泄露，防不了训练数据记忆。

## DEVIATION 全列（01..06）

- **DEVIATION-01**：wave-1 全量传输层失败，wave-2 原序重跑（8 格零内容，§4 允许重跑情形）。
- **DEVIATION-02**：T1 prompt 415KB 超 dsh argv 限（131072B OS / 256000B adapter）；skill 注入关停（`--skill-discovery off`）。
- **DEVIATION-03**：T1 因 deepseek 余额墙改 qwen3.8-max；T2 按 dsh-bailian:pro 原样跑。补记：(b) deepseek-oc:pro 同 402，opencode 通道叠加 `stall_timeout` TypeError（router 生产面，本席写权限外）。
- **DEVIATION-04**：T1 改 claude-kimi:medium（k3）；T2 pkg 07:49 冻结材料污染事件（prompts 干净、评测惰性、材料已 git 恢复，登记备审）。补记：router 路径给 worker 挂全工具且 r1 自报下载 sdist 字节对照 gold，wave-4 r1 作废，形态纠正为 claude-kimi 零工具单轮。
- **DEVIATION-05**：总编排裁定 T1 改 dsh-bailian:pro 逐字照抄 T2 配方（"stdin 不走 argv"）；R5 实测证前提为假——T2 配方走 argv 位置参数（`build_dsh_command args.append(prompt)`，dsh adapter 不收 stdin），OS E2BIG ~131072B，T1 415486B 3.2x 超限，任何 dsh 档不可载（与 DEVIATION-02 一致）。5 探针 route.json 双证。不盲跑六格，HANDBACK。
- **DEVIATION-06**：总编排裁定降级收口——T1 六格结构性缺失（传输层天花板 + 全部可载通道配额死亡），非任务失败非协议失败；judge 只判 T2、本报告 T2-only、D6 README T2-only、RECEIPT。residual 三条。

## 三层取舍 · USER_DECISION_PENDING

本实验未对 Layer 1 / Layer 2 / Layer 3 的存废产出任何可据以裁决的证据：
- T2 记忆 ceiling 压平臂间差异，无法判 Layer 2 边际贡献；
- T1 结构性缺失，无法提供 brownfield 任务的对照；
- 任何"三层全留 / 砍并某层"的结构终裁**归用户**，本报告不预设、不建议方向。

协议结构可能随三层拆分终裁调整（同 PACKET_DDP D6 / D5 调研口径）。

## 残差

1. **T1 六格待补跑**：415KB-capable 通道（HTTP/会话态，1M context）复活后用一次性纯文本形态跑 T1，落新 run 目录，不改本轮产物。候选通道：kimi（403 待窗口）、qwen（429 待周配额）、deepseek-oc（402 待充值）、claude-zai（未探）。
2. **T2 记忆污染**：T2 任务对 deepseek-v4-pro 不具区分力。补跑 T2 需换一个不在该模型训练数据中的 greenfield 多模块任务（或换 worker 模型族），属新一次实验，不在本轮收口范围。
3. **M3 token 成本采集路径落空**：dsh/ollama-cloud 不回 token 用量；后续若用回 token 用量的通道（如 opencode HTTP 路径）可补。
4. **dsh stdin 基建 follow-up**：给 dsh 加真 stdin 通道以解 131KB argv 天花板（router 生产面改动，campaign 后处理）。
5. **deepseek 直连 402 待用户充值**（可选；充值属用户付费边界）。
6. **opencode 路径 `stall_timeout` TypeError**（DEVIATION-03 补记）：router 生产面 bug，本席写权限外，登记 follow-up。

## 复现命令

- 判词原出：`cat ddp/runs/judge_out/rep{1,2}.txt`；盲映射：`cat ddp/materials/judge_only/blind_map.json`；judge prompt：`ddp/runs/judge_prompts/judge_rep{1,2}.txt`。
- 产物 hash 复算：`for c in A1 A2 B1 B2 C1 C2; do w=$([ $c = A1 -o $c = C1 ] && echo work_r1 || echo work_r2); md5sum ddp/runs/T2/$c/$w/tinydb/database.py; done`（应全 = b2a5321…）。
- 官方对照：`diff <(cat ddp/runs/T2/A1/work_r1/tinydb/database.py) /tmp/tinydb_ref/tinydb/database.py`（rc=0）。
- T1 阻塞复算：`llm -m deepseek-pro -f ddp/runs/T1/C1/prompt_r1.txt --skill-discovery off`（415486B → dispatch_failed_no_observation，DEVIATION-05 探针）。