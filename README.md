# CrossReview

> Context-isolated verification for AI-generated code — value comes from isolation, not model diversity.

CrossReview 把手工 fresh-session cross-review 流程协议化、自动化。同一模型新开 session（无生产过程上下文）就能发现问题。

## Quick Start

```bash
# 1. Install
pip install -e .                    # core (pack only)
pip install -e '.[anthropic]'       # + standalone Anthropic reviewer backend

# 2. Pack a diff into ReviewPack JSON
crossreview pack --diff HEAD~1 --intent "fix auth token refresh" > pack.json

# 3. Verify the pack (requires reviewer backend)
crossreview verify --pack pack.json
```

`crossreview verify` outputs a `ReviewResult` JSON to stdout with structured findings, advisory verdict, and quality metrics.

## Architecture

```
                         ┌─────────────┐
  git diff ──────────▶   │  Pack CLI    │  ──▶  ReviewPack JSON
                         └─────────────┘

  ReviewPack JSON ──▶  ┌───────────────────────────────────────────┐
                        │            Verify Pipeline                │
                        │                                           │
                        │  Budget Gate ─▶ Reviewer ─▶ Normalizer   │
                        │       │              │            │       │
                        │       ▼              ▼            ▼       │
                        │  complete/      raw_analysis   Findings   │
                        │  truncated/                               │
                        │  rejected     ┌──────────────┐            │
                        │               │ Adjudicator  │            │
                        │               └──────┬───────┘            │
                        │                      ▼                    │
                        │              ReviewResult JSON            │
                        └───────────────────────────────────────────┘
```

- **Budget Gate** — focus 文件优先 + diff 原顺序，按 max_files / max_chars_total 截断
- **Reviewer** — context-isolated LLM session，输出自由分析文本（raw_analysis）
- **Normalizer** — deterministic regex/heuristic，从 raw_analysis 提取结构化 Finding
- **Adjudicator** — deterministic 规则引擎，产出 advisory verdict（不做 block）

## Installation

```bash
pip install -e .                    # 最小安装（pack CLI + schema）
pip install -e '.[anthropic]'       # 加 Anthropic standalone backend
pip install -e '.[dev]'             # 开发依赖（pytest + ruff）
```

Reviewer backend 有两种模式：

| 模式 | 说明 | 依赖 |
|------|------|------|
| **Host-integrated** | 宿主（AI 编码助手）提供 fresh-session backend | 无额外 SDK |
| **Standalone** | CLI 直接调 LLM API | `crossreview[anthropic]` + API key |

Host-integrated 是默认产品路径；standalone 是 portable fallback。

## Commands

### `crossreview pack`

```bash
crossreview pack --diff HEAD~1 > pack.json
crossreview pack --diff main..feat --intent "add caching" --focus cache --context ./plan.md > pack.json
crossreview pack --diff abc123..def456 --task ./task.md > pack.json
```

| 参数 | 说明 |
|------|------|
| `--diff REF` | Git ref（`HEAD~1`）或范围（`main..feat`） |
| `--intent TEXT` | 任务意图（背景声明，非真相） |
| `--task FILE` | 完整任务描述文件 |
| `--focus TERM` | 重点审查区域（可重复） |
| `--context FILE` | 额外 context 文件（可重复） |

### `crossreview verify`

```bash
crossreview verify --pack pack.json
crossreview verify --pack pack.json --model claude-sonnet-4-20250514 --provider anthropic
```

| 参数 | 说明 |
|------|------|
| `--pack FILE` | ReviewPack JSON 文件路径 |
| `--model TEXT` | 覆盖 reviewer 模型 |
| `--provider TEXT` | 覆盖 provider（当前仅 `anthropic`） |
| `--api-key-env VAR` | 覆盖 API key 环境变量名 |

## 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| Schema (1A) | ✅ 完成 | ReviewPack / Finding / ReviewResult / Config |
| Pack CLI (1B.1 + 1C.1) | ✅ 完成 | `crossreview pack` |
| Budget Gate (1B.3) | ✅ 完成 | focus 优先 + soft/hard 截断 |
| Reviewer (1B.4) | ✅ 完成 | ReviewerBackend 接口 + Anthropic standalone |
| Normalizer (1B.5) | ✅ 完成 | deterministic regex/heuristic |
| Adjudicator (1B.6) | ✅ 完成 | 最小 advisory verdict 规则 |
| Verify CLI (1C.2) | ✅ 完成 | `crossreview verify --pack` |
| Evidence Collector (1B.2) | 🔜 待做 | ReviewPack.evidence 通路已有，空 evidence 可正常运行 |
| Eval Harness (1D.1) | 🔜 待做 | 依赖已稳定的 ReviewResult 语义 |
| Output Formatter (1B.7) | 🔜 待做 | `--format human` |
| Full Verify CLI (1C.2+) | 🔜 待做 | `--diff` 一站式路径 |

## v0 边界

### 当前支持

- `code_diff` artifact only
- Advisory verdict（建议，不做 block）
- Single reviewer（`fresh_llm_reviewer`）
- Deterministic adjudicator（规则引擎，不涉及 LLM）
- Deterministic normalizer（regex/heuristic，不做 LLM fallback）

### 明确不做（v0）

- ❌ Python SDK（v1）
- ❌ MCP Server（v1+）
- ❌ Agent Skill
- ❌ CI/CD GitHub Action
- ❌ cross_model_reviewer / skill_guided_reviewer
- ❌ verdict = block

## Release Gate

v0 发布需通过 [8 项 blocking release gates](docs/v0-scope.md)（见 §12）：

- manual_recall ≥ 0.80
- precision ≥ 0.70
- fixture_count ≥ 20

不满足 → 退回为 prompt pattern，不做独立产品化。

详细 scope → [docs/v0-scope.md](docs/v0-scope.md)

## License

MIT
