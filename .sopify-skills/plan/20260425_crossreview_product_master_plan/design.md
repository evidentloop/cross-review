# CrossReview 产品总纲 — 技术设计

> **Status**: Draft — 待评审确认
> **前置**: background.md（产品定位与竞争分析）
> **执行约束 (2026-04-26)**：v0→v2 完整技术架构，实际执行按 tasks.md 分阶段推进。v1.5/v2 为 Vision only。
> **Sopify 协同**：CrossReview 是 Sopify 生态的独立质量验证产品。Sopify Phase 4a 依赖 CR v0 release gate。详见 Sopify design.md §3.2。

---

## §1 设计目标

### 关键设计约束

1. **协议稳定优先** — ReviewPack / ReviewResult schema 是面向外部的契约，breaking change 必须有明确的 migration path
2. **确定性判定不可退让** — Normalizer + Adjudicator 永远不引入 LLM fallback
3. **全制品可扩展** — 新 artifact type 接入只需新增模板 + 约束参数 + eval baseline，不改核心管线
4. **接入无门槛** — `render-prompt + ingest` 模式下，接入方无需 API key / SDK / 额外成本
5. **评审体系独立迭代** — eval 不依赖产品形态，可以在任何通道发布前验证质量

---

## §2 核心管线设计

### 当前架构（v0）

```
Pack → BudgetGate → [Isolation] → Reviewer(LLM) → Normalizer → Adjudicator → ReviewResult
  │        │                           │                │             │
  │        │                           │                │             └── 10 条规则链
  │        │                           │                └── regex 提取 + 5 条约束降级
  │        │                           └── fresh session, canonical prompt
  │        └── focus-priority + 软硬截断
  └── SHA-256 双指纹 + 44 语言检测
```

### 全制品扩展设计（v1+）

```python
# artifact_type 决定三个维度的适配
ARTIFACT_ADAPTERS = {
    "code_diff": {
        "prompt_template": "templates/code_diff.md",      # diff-specific instructions
        "constraint_config": CODE_DIFF_CONSTRAINTS,        # HIGH requires EXACT+PLAUSIBLE
        "eval_config": "eval/code_diff/release-gate.yaml", # 8 指标
    },
    "design_doc": {
        "prompt_template": "templates/design_doc.md",      # 耦合度/扩展性/遗漏检查
        "constraint_config": DESIGN_DOC_CONSTRAINTS,       # 段落定位，非 file:line
        "eval_config": "eval/design_doc/release-gate.yaml",
    },
    "plan": {
        "prompt_template": "templates/plan.md",            # 任务完整性/依赖合理性
        "constraint_config": PLAN_CONSTRAINTS,             # 任务项定位
        "eval_config": "eval/plan/release-gate.yaml",
    },
}
```

**不变的部分**（跨 artifact type 共享）：
- ReviewPack / ReviewResult schema 核心结构
- Normalizer 的 Finding 提取逻辑（Section 1: Findings 格式统一）
- Adjudicator 的规则链框架（规则可按 artifact type 参数化，但评估顺序不变）
- Budget Gate 的截断逻辑
- 双指纹机制

**变化的部分**（按 artifact type 适配）：
- Prompt 模板（检查重点不同）
- Finding 约束参数（locatability 要求不同）
- Eval baseline 和 release gate 阈值

### Finding 约束适配

| 约束规则 | code_diff | design_doc | plan |
|---------|-----------|-----------|------|
| HIGH 要求 EXACT 定位 | EXACT = file:line | EXACT = section:paragraph | EXACT = task_ref |
| SPECULATIVE 降级 | → MEDIUM | → MEDIUM | → MEDIUM |
| NONE 定位上限 | LOW | LOW | LOW |
| SPECULATIVE+NONE | NOTE | NOTE | NOTE |
| SPECULATIVE 不可操作 | ✅ | ✅ | ✅ |

---

## §3 产品形态技术设计

### 3.1 Sopify 插件

**Phase 4a — Advisory 模式（v0.5，对标 Graphify）**：

```
.agents/skills/cross-review/
├── SKILL.md          # LLM 读取的编排指令: develop 后调用 CLI
└── skill.yaml        # advisory mode, 无 bridge.py
```

**触发链路（Phase 4a）**：
```
Sopify develop 完成所有 task
  ↓
LLM 发现 cross-review SKILL.md（advisory mode）
  ↓
LLM 自行执行: crossreview verify --diff --format human
  └─ 回退: crossreview pack --diff → crossreview verify --pack
  ↓
├── pass_candidate → 继续 finalize
├── concerns → 展示 findings，用户决定
├── needs_human_triage → 展示 finding，请用户判断
└── inconclusive → 记录，继续
```

**Phase 4b — Runtime 模式（v1，依赖 Sopify Phase 3，🧊 冻结，不进入 0-6 个月承诺）**：

```
.agents/skills/cross-review/
├── SKILL.md          # 保留 advisory 指令 + 新增 runtime 编排说明
├── skill.yaml        # 升级为 runtime mode: pipeline_hooks.after_develop
└── bridge.py         # Python bridge: run_verify_pack() → verdict → checkpoint proposal (Core validates & materializes)
```

**触发链路（Phase 4b）**：
```
Sopify develop 完成所有 task
  ↓
Plugin Runtime / Core validation layer 检查 enabled pipeline hook (after_develop)
  ↓
发现 cross-review skill (runtime mode)
  ↓
bridge.py: git diff → build_pack → run_verify_pack → verdict + checkpoint proposal
  ↓
Sopify Core validates checkpoint proposal → Core materializes decision/clarification checkpoint
  ↓
├── pass_candidate → 继续 finalize
├── concerns → decision checkpoint: 修改代码 / 接受风险 / 忽略
├── needs_human_triage → clarification checkpoint: 请用户判断
└── inconclusive → 静默记录
  ↓
如选择"修改代码" → 修复 → 重新审查（最多 2 轮）
```

**默认 OFF**（ADR-009 flow priority）：Phase 4a 由 LLM 自主决定是否调用；Phase 4b 需用户在 `sopify.config.yaml` 中显式启用 pipeline_hooks。

### 3.2 GitHub Action（v1）

```yaml
# crossreview/action@v1
name: CrossReview
description: Context-isolated code review for AI-generated PRs
inputs:
  model:
    description: Reviewer model
    default: claude-sonnet-4-20250514
  provider:
    description: LLM provider
    default: anthropic
  intent:
    description: PR intent (defaults to PR title)
  focus:
    description: Focus areas (comma-separated)
  artifact_type:
    description: Artifact type to review
    default: code_diff
  fail_on:
    description: Verdict that triggers failure
    default: never  # advisory only by default

runs:
  using: composite
  steps:
    - name: Pack
      run: crossreview pack --diff ${{ github.event.pull_request.base.sha }}..${{ github.sha }} --intent "${{ inputs.intent || github.event.pull_request.title }}" > pack.json
    - name: Verify
      run: crossreview verify --pack pack.json --model ${{ inputs.model }} --provider ${{ inputs.provider }} > result.json
    - name: Comment
      run: crossreview format --result result.json --github-pr ${{ github.event.pull_request.number }}
```

**关键设计决策**：
- `fail_on: never` — v1 默认 advisory only，不阻断 CI
- 后续可配置 `fail_on: concerns` 让 verdict=concerns 时 CI 失败
- inline comment 使用 GitHub Review API，不是 issue comment

### 3.3 MCP Server（v1）

```json
{
  "tools": [
    {
      "name": "crossreview_pack",
      "description": "Assemble a ReviewPack from diff + intent + focus",
      "inputSchema": {
        "type": "object",
        "properties": {
          "diff": {"type": "string"},
          "intent": {"type": "string"},
          "focus": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    {
      "name": "crossreview_verify",
      "description": "Run isolated review on a ReviewPack",
      "inputSchema": {
        "type": "object",
        "properties": {
          "pack": {"type": "object"},
          "model": {"type": "string"}
        }
      }
    },
    {
      "name": "crossreview_render_prompt",
      "description": "Render canonical reviewer prompt for host execution",
      "inputSchema": {
        "type": "object",
        "properties": {
          "pack": {"type": "object"}
        }
      }
    },
    {
      "name": "crossreview_ingest",
      "description": "Process raw analysis into structured ReviewResult",
      "inputSchema": {
        "type": "object",
        "properties": {
          "pack": {"type": "object"},
          "raw_analysis": {"type": "string"},
          "model": {"type": "string"}
        }
      }
    }
  ]
}
```

**4 个 MCP tool** 直接映射 CLI 的 4 个命令。AI 助手可以：
- 直接调 `verify`（standalone 模式）
- 或调 `render_prompt` → 自己在隔离 context 执行 → 调 `ingest`（host-integrated 模式）

### 3.4 Hosted API（v1.5, 待定）

> **状态**：商业化路径待定。以下为架构预设计，不做投入承诺。

```
POST /v1/pack
POST /v1/verify
POST /v1/render-prompt
POST /v1/ingest
GET  /v1/result/{fingerprint}
```

**定价模型（待定）**：
- 需要用户采纳数据支撑，v1 之前不做定价决策
- 可能方向：Free tier + pay-per-review + Enterprise 年订阅

---

## §4 评审体系详细设计

CrossReview 的结构化输出不仅是一次性审查结果，也应成为可沉淀的项目审查资产。`review-result.json`、adjudication 记录和未来面向用户的 `review.md` 应支持被 Sopify 的 plan / history / blueprint 链路二次消费；该价值需在 v0 release gate 通过后通过真实二次消费路径验证。

### 4.1 Fixture 结构（跨 artifact type 统一）

```yaml
fixture:
  id: string                    # 唯一标识
  artifact_type: string         # code_diff | design_doc | plan
  pool: string                  # external | self_hosting | dogfood
  source_project: string        # 来源项目
  created_at: ISO 8601

  # 输入
  pack: ReviewPack              # 标准化输入

  # 自动化输出
  review_result: ReviewResult   # 管线输出

  # 人工标注
  manual_findings:
    source: manual_fresh_session
    findings: list[ManualFinding]

  # 判定映射
  auto_adjudications:
    findings: list[AdjudicationEntry]
```

### 4.2 per-artifact-type Release Gate

```yaml
# eval/code_diff/release-gate.yaml
artifact_type: code_diff
version: v0
gates:
  manual_recall: {min: 0.80}
  precision: {min: 0.70}
  invalid_findings_per_run: {max: 2}
  unclear_rate: {max: 0.15}
  context_fidelity: {min: 0.80}
  actionability: {min: 0.90}
  failure_rate: {max: 0.10}
  fixture_count: {min: 20}

# eval/design_doc/release-gate.yaml
artifact_type: design_doc
version: v1
gates:
  manual_recall: {min: 0.70}     # 初期可低于 code_diff
  precision: {min: 0.65}         # 架构审查更主观
  invalid_findings_per_run: {max: 3}
  unclear_rate: {max: 0.20}
  # context_fidelity / actionability 需要为 design_doc 重新定义
  fixture_count: {min: 10}       # 初期 fixture 少于 code_diff
```

### 4.3 Eval 独立迭代原则

1. **eval 先于产品形态**：新 artifact type 的 eval baseline 必须在对应产品形态发布前建立
2. **不达标不发布**：任何 artifact type 不通过 release gate，不发布对应的 CLI/Action/MCP 支持
3. **fixture 持续增长**：每个真实 dogfood 使用都应产出新 fixture
4. **eval 独立仓库可考虑**：当 fixture 数量超过 100，考虑分离 eval 数据到独立仓库

---

## §5 协议演进策略

### Schema 版本管理

```
v0-alpha (当前): code_diff only, advisory verdict
v0: code_diff, release gate 通过后锁定
v1: + design_doc + plan artifact types
v2: + analysis + review_result + multi-round review
```

### Breaking Change 策略

| 变更类型 | 处理方式 |
|---------|---------|
| 新增 optional field | 兼容，minor version bump |
| 新增 artifact_type | 兼容，minor version bump |
| 修改 Finding 约束规则 | 需要 eval 重跑验证，patch version bump |
| 修改 ReviewPack 必填字段 | **Breaking**，major version bump + migration guide |
| 修改 ReviewResult 结构 | **Breaking**，major version bump |

### 长期愿景：协议标准化

ReviewPack / ReviewResult 的目标是成为 **AI 审查的标准协议**（类似 SARIF 之于静态分析）：

- 任何工具可以产出 ReviewPack
- 任何 reviewer 可以消费 ReviewPack
- 任何消费方可以解析 ReviewResult
- 指纹机制保证可追溯性
- quality_metrics 保证可度量性
