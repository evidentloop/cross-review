# Prompt Lab

验证核心假设：fresh LLM reviewer 能否从 ReviewPack 中稳定产出真 finding。

## 为什么在工程实现前做这一步

CrossReview 的全部价值取决于"给模型一个 ReviewPack，它能输出多少真 finding"。如果 raw output 质量不行，schema / adjudicator / formatter 都是在包装失败。

## 单次评审 vs 交叉验证

Prompt Lab 默认评估的是 **单次评审（single-pass review）**，不是完整的 cross-review workflow。

- **单次评审**：给 reviewer 一个 ReviewPack，让它在独立 fresh session 中输出第一轮 raw findings。Prompt Lab 的 precision / recall / invalid rate 默认只看这一轮原始输出，不把后续人工修正、第二模型批判、或回喂复核混进指标。
- **交叉验证**：reviewer 先输出 findings，再由另一个独立 session / agent 对这些 findings 做实现核查、打掉幻觉、补充遗漏，必要时再把验证结果回喂给原 reviewer 复核。这是 CrossReview 的真实使用场景之一，但它评估的是 **workflow 质量**，不是 reviewer prompt 的 first-pass 质量。

两者都合理，但不能混算：

- 要验证 `prompt-template.md` 是否有效，使用 **单次评审** 口径。
- 要验证“reviewer + validator + adjudicator”整条链路能否提升 precision，使用 **交叉验证** 口径。

如果同一批 case 既跑单次评审，又跑交叉验证，结果应分别记录，避免把 workflow 增益误记为 prompt 本身的能力。

## 怎么跑

Prompt Lab 目前有两条 prompt 入口：

- `python run.py --render-only ...` 渲染 `prompt-lab/prompt-template.md`，用于手动粘贴实验。
- `python run.py --api-only ...` 调用产品 verify 管道，渲染 `crossreview/core/prompt.py`；产出的 `ReviewResult.reviewer` 会记录 `prompt_source` 与 `prompt_version`。

Host-integrated（宿主集成）模式始终使用产品 prompt（`crossreview/core/prompt.py`），通过 `crossreview render-prompt` 获取。Prompt Lab template 仅用于手动实验迭代，不用于 host-integrated 或 eval baseline。

除非 summary 明确标注 prompt source/version，否则不要跨入口混用 adjudication。历史 Round 3 输出标注为 `template: v0.3`，但对应模板没有入库，因此不能作为可复现的 product baseline。

```bash
# 1. 在 cases/ 下创建新 case 目录
mkdir cases/001-auth-refresh

# 2. 准备 diff 和 pack
#    - diff.patch: 真实 git diff
#    - pack.json: 手工/半手写 ReviewPack（格式见下方）
#    - manual-findings.yaml: 手工 cross-review 发现的问题（gold baseline）

# 3. 渲染 prompt → 手动粘贴给模型
python run.py --render-only cases/001-auth-refresh
# → 生成 cases/001-auth-refresh/rendered-prompt.md
# → 粘贴到 Claude/ChatGPT session，保存 output 到 raw-output.md

# 4. 查看 raw output → cases/001-auth-refresh/raw-output.md

# 5. 人工 adjudication → 编辑 cases/001-auth-refresh/adjudication.yaml
# 6. 更新 prompt-lab/summary.md 汇总表

# API-only product-prompt run (writes ReviewResult JSON)
python run.py --api-only --label r4 cases/001-auth-refresh
# → 生成 cases/001-auth-refresh/run-r4.json
```

## manual-findings.yaml 格式

手工 baseline 格式与 [fixtures/README.md](../fixtures/README.md) 一致：

```yaml
fixture_id: "001-auth-refresh"
source: manual_fresh_session
reviewer_model: "claude-sonnet-4-20250514"
reviewed_at: "2026-04-20T16:00:00+08:00"
findings:
  - id: "mf-001"
    summary: "Token expiry off-by-one"
    file: "src/auth/token.ts"
    severity_estimate: high
```

## ReviewPack 手写格式

```json
{
  "artifact_type": "code_diff",
  "diff": "<unified diff text>",
  "changed_files": ["src/auth/token.ts", "src/auth/types.ts"],
  "intent": "修复 token refresh 过期判断",
  "focus": ["auth"],
  "context_files": [],
  "evidence": []
}
```

## Baseline 独立性要求（扩样规则）

`manual-findings.yaml` 是 recall 计算的分母定义，不是普通标注文件。如果 baseline 不独立，recall 数字会变成自证循环。

**强制要求：**

1. **先 baseline，再 reviewer** — `manual-findings.yaml` 必须先于 reviewer 输出落盘。不允许先跑 reviewer、看到 findings 再回填 baseline。
2. **baseline 与 reviewer 隔离** — 写 baseline 的人/session 不得接触当次 reviewer 输出。最低标准：人工独立 fresh-session cross-review，或由未参与本次 reviewer run 的人来写。
3. **事后补 baseline 必须显式标注** — 如果某个 case 的 baseline 确实是事后补的（特殊情况），必须在 summary.md 对应行显式标注（如 `baseline: post-reviewer`），不得和原生独立 baseline 混算 recall。
4. **每批新增 ≥1 clean diff** — 不允许所有 case 都是 bug-heavy case；否则 precision=1.00 只反映样本偏差。

**到 10 个 fixture 时的过程检查：**

除 precision / recall / unclear_rate / 边界项占比外，额外统计：
- 有多少 baseline 是"先 reviewer 后补"？
- 该比例如果超过 20%，需在 summary 中单独注明 recall 解释力下降。

## Fixture 选择约束

Prompt Lab 第一批 case 固定使用 3-5 个真实 diff，不使用纯合成 case。

- 来源限定为近期真实 commit，优先从 `cross-review/`、`helloagents/`、`hermes-agent/` 提取
- 至少包含 1 个 clean diff（应当基本无有效 finding）
- 其余 case 优先覆盖：
  - 小型、意图清晰的修复
  - 中等体量、跨 3-5 文件的真实改动
  - 工程性更强、带测试或系统性约束的 bugfix

## Adjudication 记录格式

```yaml
fixture_id: "001-auth-refresh"
adjudicated_at: "2026-04-20T16:00:00+08:00"
model: "claude-sonnet-4-20250514"
latency_sec: 45.2
input_tokens: 3200
output_tokens: 1800

findings:
  - auto_finding_id: "f-001"
    judgment: valid        # valid | invalid | unclear
    matched_manual_id: "mf-001"  # 匹配手工 baseline 的哪条 finding
    actionability_judgment: actionable  # actionable | not_actionable | unclear
    notes: ""

  - auto_finding_id: "f-002"
    judgment: invalid
    matched_manual_id: null
    actionability_judgment: not_actionable
    notes: "模型编造了一个不存在的竞态条件"

summary:
  valid_count: 1
  invalid_count: 1
  unclear_count: 0
  observations: "模型在 auth 逻辑上能发现真问题，但容易在并发场景编造 finding"
```

## 要回答的三个问题

完成 3-5 个 case 后，总结：

1. **模型是否能稳定给出真问题？** → valid rate 是否 > 50%
2. **需要哪些 context 才能给出真问题？** → 哪些 case 因为缺 context 导致 finding 质量差
3. **主要噪音来自 prompt 还是 pack 缺失？** → invalid finding 的根因分类

这些结论不应只停留在口头总结。Prompt Lab 结束时，需同步更新 `prompt-lab/summary.md`，至少按 case 记录：

- fixture_id
- source_commit / source_repo
- 是否 clean diff
- valid_count / invalid_count / unclear_count
- 缺失 context 观察
- 噪音归因（prompt / pack / 其他）

## Gate

Prompt Lab 通过 → 进入 Phase 1 正式实现。
Prompt Lab 不通过 → 调整 prompt / pack 策略重试，或存档方案等待模型能力提升。
