# CrossReview v0 Prompt Lab + Phase 1 — 任务清单

## Source-of-Truth

实现只认 [docs/v0-scope.md](../../../docs/v0-scope.md)（Status: Confirmed）+ 本文件。

---

## Phase 0.5 — Prompt Lab（✅ 已完成，gate 已通过）

> 目标：验证核心假设——fresh LLM reviewer 能否从 ReviewPack 中稳定产出真 finding。
> 如果 prompt lab 结果很差，后续 schema / adjudicator / formatter 都是在包装失败。

- [x] 0.5.1 准备 3-5 个真实 diff fixture
  - 来源：近期开发的真实 diff（非玩具示例）
  - 每个包含：diff + intent（可选）+ 手工 cross-review 的 expected findings
- [x] 0.5.2 手写/半手写 ReviewPack
  - 不需要 CLI 工具，手工组装 diff + intent + focus + context
  - 保存为 JSON
- [x] 0.5.3 固定 reviewer prompt 模板
  - 关键约束：intent/focus/task 是待验证背景声明，不是真相；raw diff 是优先证据
  - reviewer 先做自由分析，不强制输出 Finding JSON schema
  - 实现位置：`crossreview/core/prompt.py` (product/v0.1)
- [x] 0.5.4 运行 prompt → 保存 raw model output
  - 单脚本实现（prompt-lab/run.py），不搭框架
  - 记录：model, latency_sec, input_tokens, output_tokens
- [x] 0.5.5 人工 adjudication + 记录
  - 回答三个问题：
    1. 模型是否能稳定给出真问题？
    2. 需要哪些 context 才能给出真问题？
    3. 主要噪音来自 prompt 还是 pack 缺失？

> **Gate**: ✅ 通过，已进入 Phase 1。

---

## Phase 1A — Schema & Config（✅ 已完成）

- [x] 1A.1 实现 ReviewPack schema（v0-scope.md §7）
  - artifact_type: "code_diff" only
  - 必填: artifact, changed_files
  - 可选: intent, focus, context_files, evidence
  - 实现位置：`crossreview/schema.py`
- [x] 1A.2 实现 Finding schema（v0-scope.md §7）
  - 包含: locatability / confidence(plausible|speculative) / evidence_related_file / actionable
  - severity 约束规则（locatability × confidence 矩阵）
  - 实现位置：`crossreview/schema.py`
- [x] 1A.3 实现 ReviewResult schema（v0-scope.md §7）
  - 包含: review_status, findings, advisory_verdict, quality_metrics
  - 实现位置：`crossreview/schema.py`
- [x] 1A.4 实现 reviewer backend resolution
  - 显式 override: --model / --provider > crossreview.yaml > ~/.crossreview/config.yaml > env
  - 默认产品语义: host-integrated same-model fresh review when host backend available
  - fallback: standalone provider backend
  - 实现位置：`crossreview/config.py`

## Phase 1B — Core Pipeline（✅ 大部分完成）

- [x] 1B.1 实现 Pack 阶段
  - `crossreview pack --diff HEAD~1 --intent "..." --focus auth --context ./plan.md`
  - 实现位置：`crossreview/pack.py`
- [ ] 1B.2 实现 Evidence Collector（deterministic_evidence）
  - 安全边界：只从 CLI --evidence-cmd 或 crossreview.yaml 读取命令
  - 状态：ReviewPack.evidence 字段通路已有，空 evidence 可正常运行。collector 逻辑未实现。
- [x] 1B.3 实现 Budget Gate
  - 三状态: complete / truncated / rejected
  - 实现位置：`crossreview/budget.py`
- [x] 1B.4 实现 reviewer interface + v0 first backend
  - 定义 `ReviewerBackend` 抽象接口
  - `fresh_llm_reviewer` 是逻辑角色，不绑定具体 provider
  - 当前分支实现 standalone concrete backend（Anthropic）
  - 全新 session，无 producer 上下文
  - 输出自由分析文本（鼓励半结构化 markdown）
  - prompt 声明：intent/focus/task 是待验证背景声明
  - 保留 raw analysis 文本作为审计证据
  - 记录 latency_sec / input_tokens / output_tokens
  - 实现位置：`crossreview/reviewer.py`
- [x] 1B.5 实现 FindingNormalizer
  - 从 reviewer raw analysis 提取结构化 Finding（regex / heuristic only）
  - 不引入 LLM fallback
  - parse 失败视为 reviewer / prompt 质量信号
  - 实现位置：`crossreview/normalizer.py`
- [x] 1B.6 实现 Adjudicator（确定性，非 LLM）
  - verdict: pass_candidate / concerns / needs_human_triage / inconclusive
  - v0 只做 advisory
  - 实现位置：`crossreview/adjudicator.py`
- [ ] 1B.7 实现 Output Formatter
  - 支持 --format json/human
  - 状态：JSON 输出已有，human-readable 格式未实现

## Phase 1C — CLI（✅ 已完成）

- [x] 1C.1 实现 `crossreview pack` 命令
- [x] 1C.2 实现 `crossreview verify` 命令
  - `crossreview verify --pack pack.json`
  - 输出：ReviewResult JSON to stdout
  - `--diff` 与 `--format human` 延后
- [x] 1C.3 实现 `crossreview render-prompt` 命令（host-integrated 前半段）
  - `crossreview render-prompt --pack pack.json [--template custom.md]`
  - 渲染 canonical reviewer prompt → stdout
  - 不调用 LLM，不需要 API key
  - 实现位置：`crossreview/cli.py`
- [x] 1C.4 实现 `crossreview ingest` 命令（host-integrated 后半段）
  - `crossreview ingest --raw-analysis FILE --pack pack.json --model MODEL`
  - 接收宿主 raw analysis → normalizer + adjudicator → ReviewResult JSON
  - 不调用 LLM，不需要 API key
  - 支持 stdin (`--raw-analysis -`)
  - 实现位置：`crossreview/ingest.py` + `crossreview/cli.py`

## Phase 1D — Fixture & Validation（🔜 进行中）

- [x] 1D.1 实现 eval harness（dev-only）
  - `crossreview_eval.py`（634 行）：离线聚合器，读取 fixture 目录，计算 release-gate 指标
  - `tests/test_eval_harness.py`（534 行）：完整测试覆盖
  - `fixtures/README.md`：fixture 格式定义（fixture.yaml / pack.json / review-result.json / manual-findings.yaml / auto-adjudications.yaml）
  - 状态：框架已就绪，后续只做补齐/打磨，不是从零任务
- [ ] 1D.2 Fixture 格式对齐与打磨
  - 确保 eval harness 代码与 fixtures/README.md 格式定义完全一致
  - 建立从 prompt-lab/cases → fixtures/ 的迁移规范
- [ ] 1D.3 收集 ≥ 20 个真实 fixture
  - 当前 fixtures/ 目录实际 fixture = 0
  - prompt-lab/cases/ 有 13 个已验证 case，可形式化迁移
  - 需额外新增 ≥ 7 个真实 diff fixture
- [ ] 1D.4 达成 v0 release gates（v0-scope.md §12）
  - manual_recall ≥ 0.80, precision ≥ 0.70
  - invalid_findings_per_run ≤ 2, unclear_rate ≤ 0.15
  - context_fidelity ≥ 0.80, actionability ≥ 0.90
  - failure_rate ≤ 0.10, fixture_count ≥ 20

**优先级**：1D.2/1D.3/1D.4 > 1B.7 > 1B.2（1D 是 v0 release gate blocker）
