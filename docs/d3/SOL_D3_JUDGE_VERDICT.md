# SOL_D3_JUDGE_VERDICT（T2 六格双盲判词 · 降级收口）

- 判定者：`llm -m gpt`（Sol，gpt-5.6-sol，2026-08-30 11:36-11:37 CEST）
- 范围：D3 降级收口，只判 T2 六格（DEVIATION-06）；T1 六格结构性缺失，不判。
- 协议：预注册 §5 M5 rubric（4 维 1-5 分）+ §6 双盲（judge 只见 X/Y/Z 匿名产物与任务原文，不知臂、不知重复、不知假设、不知其他 rep 存在）。blind_map 落 `materials/judge_only/blind_map.json`（judge 不可见目录）。judge prompt 落 `runs/judge_prompts/judge_rep{1,2}.txt`，原出落 `runs/judge_out/rep{1,2}.txt`。
- 任务原文：从 `materials/T2/context_pack.md` 抽行为相关 docs（api/usage/getting-started），剥 stub 源码。
- 产物：每格按 rounds_fix 取最终通过产物目录（r0→work_r1，r1→work_r2）的 8 个 `tinydb/*.py`。

## 盲映射（判后揭盲）

| rep | X | Y | Z |
|---|---|---|---|
| rep1 | T2/B1（B 臂） | T2/A1（A 臂） | T2/C1（C 臂） |
| rep2 | T2/B2（B 臂） | T2/C2（C 臂） | T2/A2（A 臂） |

## 判词（揭盲后按格归位）

| 格 | 臂 | rep | 覆盖 | 架构 | 可运行 | 工程度 | 判词来源 |
|---|---|---|---|---|---|---|---|
| T2/A1 | A | 1 | 4 | 5 | 4 | 4 | rep1-Y |
| T2/B1 | B | 1 | 4 | 5 | 4 | 4 | rep1-X |
| T2/C1 | C | 1 | 4 | 5 | 4 | 4 | rep1-Z |
| T2/A2 | A | 2 | 5 | 5 | 4 | 4 | rep2-Z |
| T2/B2 | B | 2 | 5 | 5 | 4 | 4 | rep2-X |
| T2/C2 | C | 2 | 5 | 5 | 4 | 4 | rep2-Y |

## judge 整体观察（逐字引用，关键发现）

- rep1：「X、Y、Z 在所展示的全部文件中逐字一致，包括实现、类型标注、注释、文档字符串以及相同的边界缺陷，属于极强的雷同或共同来源迹象；仅凭代码无法判定具体成因或抄袭方向。」
- rep2：「X/Y/Z 几乎逐字一致，连注释、类型标注、控制流及细小缺陷都相同；唯一可见差异主要是 touch 的等价写法以及 Storage.close 使用 pass 或 return None，这种异常一致性强烈表明三者共享同一代码来源或存在直接复制，不能视为真正独立实现。」

**judge 在不知臂、不知假设的前提下，独立得出"产物非独立实现、共享同一来源"的结论。**

## 机械印证（编排侧，hash 双证 judge 观察）

六格最终产物 `tinydb/database.py` 的 md5 全部 = `b2a5321ae50625cac693f56061ca3055`，与 PyPI 官方 tinydb 4.8.0 的 `database.py` 逐字相同（`diff` rc=0）；`table.py` 六格 md5 全部 = `19e99a87495ba0c5f33d39f93f593515`（769L，六格一致；官方 table.py 同为 769L、md5 `d430500…`，差异在等价写法）。worker 形态为一次性文本无工具无网络（AMENDMENT-A1 §1），不可能下载；A1 raw 自报"下载并解包 PyPI tinydb-4.8.0 wheel"是 confabulation。唯一自洽解释：deepseek-v4-pro 训练数据含 tinydb 4.8.0，六格均复现记忆中的官方实现，与 A/B/C 臂无关。

## 跨 rep 分数差异 = judge 噪声（非质量差异）

rep1 三格覆盖=4、rep2 三格覆盖=5，但六格代码逐字一致（hash 证）。同一份代码在两次 judge 会话得到不同覆盖分，是 judge 随机性，不携带质量区分信号。架构/可运行/工程度六格全相同。

## 第三方裁定状态

未触发。预注册 §6 规定第三方裁定（`llm -m glm`）用于"judge 对同格两次重复给出方向冲突判词、或自报判不了"。本次 judge 判词无方向冲突（同 rep 内 X/Y/Z 分数一致）、未自报判不了，故第三方裁定不触发。judge 的"非独立实现"观察已由编排侧 md5 机械印证，无需第三方佐证即成立。

## 总体判定

T2 六格 M5 判词落盘。**判词不构成对 DDP 协议任何臂优劣的证据**：六格产物经 judge 独立观察与 md5 双证为同一记忆来源的复现，臂间无可见差异；M5 分数仅反映 judge 对"该记忆实现"的绝对质量评价（覆盖 4-5、架构 5、可运行 4、工程度 4），不携带臂间区分信号。结合 M4 全 200/0（ceiling）、M1 全覆盖（ceiling），T2 对实验问题（Layer 2 边际贡献）无可解释证据。详见 `ABLATION_RESULT.md`。