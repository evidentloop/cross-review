# Prompt Lab Summary

> **Latest**: prompt-lab-v0-round2
> **Reviewer model**: claude-opus-4.6 (tool-assisted isolated reviewer — agent 有文件系统读权限，非 render-only 纯隔离)
> **Template**: v0.2 (Findings/Observations split, diff-only constraint, semantic equivalence instruction)
> **Date**: 2026-04-23
> **Adjudication standard**: strict — valid 仅限当前 diff 可见且可归责的真实问题；observation 桶不计入 precision
> **隔离级别**: tool-assisted (见 [隔离级别说明](#隔离级别说明))

## Prompt 来源

Prompt Lab 区分历史实验入口与产品 prompt 入口：

| 轮次 | Runner 模式 | Prompt 来源 | 版本 | 状态 |
|------------|-------------|---------------|---------|--------|
| Round 1 | manual/tool-assisted | `prompt-lab/prompt-template.md` | v0 | 历史数据 |
| Round 2 | manual/tool-assisted | `prompt-lab/prompt-template.md` | v0.2 | 下方最新已 adjudicate 摘要 |
| Round 3 | manual/tool-assisted | 未可复现入库 | v0.3 | 仅作历史数据，不作为 product baseline |
| Round 4 | `run.py --api-only` | `crossreview/core/prompt.py` | product/v0.1 | 计划中的 product-prompt baseline |

Round 3 数据仍可用于提示词设计参考，但它标注的 `template: v0.3` 文件不在仓库中，无法严格复现。API-only run 有意使用 canonical product prompt，而不是 `prompt-lab/prompt-template.md`；其 `ReviewResult.reviewer` metadata 必须记录 `prompt_source: "product"` 与 `prompt_version: "v0.1"`。

Product prompt `v0.1` 包含 Round 2 的核心改进（Findings/Observations split、diff-only constraint、semantic equivalence），并针对 Round 2 recall gap 增加 shell/command continuation 指令。由于 prompt 已变化，新的 `run-r4.json` 输出必须重新生成 `adjudication-r4.yaml`；不能复用 `adjudication-r3.yaml`。

## Adjudication Schema

> **口径定义**: valid = 当前 diff 可见且可归责的真实问题（含 introduced 和 preexisting_visible）

```yaml
judgment: valid | invalid | unclear | observation
provenance: introduced | preexisting_visible | speculative_unseen | n/a
counted_in_precision: true | false

# valid 范围：diff 中可见且可归责（introduced OR preexisting_visible）
# observation 范围：事实正确但不构成 finding，不计入 precision
# precision = valid / (valid + invalid)；unclear 和 observation 均不计入分母

判定表:
  defect_in_new_code:                    valid, introduced, counted=true
  defect_in_old_code_visible_in_diff:    valid, preexisting_visible, counted=true
  latent_bug_in_new_code:                valid, introduced, counted=true
  missing_test_for_specific_new_risk:    valid, introduced, counted=true
  style_cosmetic_observation:            observation, counted=false
  speculation_about_unseen_code:         unclear, counted=false
  clean_diff_note:                       observation, counted=false
  factually_wrong_about_code:            invalid, counted=true
```

## Results

### Round 2 (v0.2 template)

| fixture_id | clean_diff | valid | invalid | unclear | observation | recall | delta_vs_r1 |
|------------|:----------:|:-----:|:-------:|:-------:|:-----------:|:------:|-------------|
| 001-hermes-subshell-leak | no | 5 | 0 | 0 | 5 | 1/2 (50%) | valid +4, invalid -2, unclear -2, recall +1 |
| 002-helloagents-codex-config | no* | 2 | 0 | 0 | 3 | 1/1 (100%) | valid +1, invalid -2, stable recall |
| 003-crossreview-review-fixes | no | 3 | 0 | 0 | 4 | 1/1 (100%) | valid ±0, invalid -2, stable recall |
| 004-graphify-download-badge | yes | 0 | 0 | 0 | 3 | n/a† | stable (clean control passed both rounds) |
| **TOTAL** | | **10** | **0** | **0** | **15** | **3/4 (75%)** | |

### Round 1 (v0 template) — for comparison

| fixture_id | clean_diff | valid | invalid | unclear | observation | recall |
|------------|:----------:|:-----:|:-------:|:-------:|:-----------:|:------:|
| 001-hermes-subshell-leak | no | 1 | 2 | 2 | 4 | 0/2 (0%) |
| 002-helloagents-codex-config | no* | 1 | 2 | 0 | 2 | 1/1 (100%) |
| 003-crossreview-review-fixes | no | 3 | 2 | 0 | 3 | 1/1 (100%) |
| 004-graphify-download-badge | yes | 0 | 0 | 0 | 3 | n/a† |
| **TOTAL** | | **5** | **6** | **2** | **12** | **2/4 (50%)** |

> \* 002 manual baseline supplemented after Round 1.
> † No manual findings to recall against.

## Aggregate Metrics

### Round 2 vs Round 1 Comparison

```yaml
                    Round 1         Round 2         Delta       Gate
precision:          0.45            1.00            +0.55       >= 0.70 ✓ (was ✗)
manual_recall:      0.50            0.75            +0.25       >= 0.80 ✗ (improved)
invalid_per_run:    1.50            0.00            -1.50       <= 2.0  ✓ (was ✓)
max_invalid_run:    2               0               -2          <= 5    ✓ (was ✓)
actionability:      1.00            1.00            ±0          >= 0.90 ✓ (was ✓)
```

> **Round 2 定位**: v0.2 template 的 A/B 对比。相同 4 case、相同模型、相同 adjudication 口径。
> precision 从 0.45 → 1.00，recall 从 0.50 → 0.75 (001 mf-001 新匹配)。
> **precision 达标，但不等于 prompt 本身满分**：invalid 清零的主因是 F/O 重分桶（R1 的 speculative items 被路由到 Observations，
> 不再计入 precision 分母），且 reviewer 实际使用了文件系统补证（非 render-only 纯隔离），详见 [隔离级别说明](#隔离级别说明)。
> 此外 002-f-002 (dead export) 和 003-f-002 (usage spec mismatch) 属边界 finding，收紧口径后 precision 可能低于 1.00。
> 更准确的结论：**"当前 reviewer setup（tool-assisted + v0.2 template）明显优于 Round 1"**，而非 "纯 prompt 已经满分"。
> 唯一未过 gate 的是 recall (0.75 < 0.80)，差距 = 1 条 baseline finding (001 mf-002)。

## Key Observations

### Round 2 改进归因

| v0.2 变更 | 效果 | 证据 |
|-----------|------|------|
| Findings/Observations 输出分离 | invalid 清零（precision 计算层面） | R1 的 6 条 invalid 中 3 条是 speculative，R2 全部路由到 Observations；**注意：这是分桶改善，不是事实判别能力提升** |
| Instruction #5: diff-only constraint | 消除 speculative_unseen findings | 001 R1 有 f-004/f-007 推测 unseen code；R2 对等项全在 o-001~o-005 |
| Instruction #6: semantic equivalence | recall +1 (001 mf-001) | R1 没有 "检查重写后语义等价" 指引；R2 f-001 精确命中 mf-001 — **最硬的证据** |
| 移除 Confidence 字段 | 简化输出，无负面影响 | R1 的 confidence=speculative 没有防止 invalid；R2 用 F/O split 替代 |

### 剩余 Gap

**Recall gap (0.75 vs 0.80 gate):**
- 唯一遗漏: 001 mf-002 — multiline continuation (`A &&\nB &` 中 `&&` 在行尾是 bash continuation，但 rewriter 在 `\n` 重置 chain state 导致 `B &` 被当作 simple background 不做 rewrite)
- 这需要理解 bash 在非交互模式下 `&&` 后接 newline 是 continuation 而非 statement terminator
- v0.2 的 instruction #6 (semantic equivalence) 没有覆盖到这个层次 — 它提到了 "execution order, side effects, error handling paths" 但没有提到 "multiline statement continuation semantics"

### 边界 Findings (Borderline)

> 以下 finding 在当前口径下判 valid，但收紧后可能降为 observation。保留以供后续口径校准参考。

| finding | 当前判定 | 争议点 |
|---------|----------|--------|
| 002-f-002 (dead exported function) | valid, introduced | 更接近 cleanup/observation 而非 defect；函数确实只剩导出无调用，但"死代码"是否算 finding 取决于口径 |
| 003-f-002 (usage message spec_mismatch) | valid, introduced | reviewer 混入了对当前 run.py / call_reviewer 未实现的外部确认（工具补证），与 template "only report from diff" 有张力 |

### 隔离级别说明

**当前级别: tool-assisted isolated reviewer**
- Reviewer 以独立 task agent 运行，**有完整文件系统读权限**
- 实际使用了工具补证：001 reviewer 读取 `_read_shell_token` 源码验证，003 reviewer 读取当前 run.py 确认 `NotImplementedError`
- 这 **不是 render-only 纯隔离实验**

**对结果的影响：**
- 对 precision: 正面（额外验证减少 false positive，但也意味着 precision=1.00 不能完全归因于 prompt）
- 对 recall: 中性（额外文件访问没有帮助发现遗漏的 baseline findings）
- 对 cross-review 核心论证: 有效——证明 context isolation + independent review 能发现 production session 遗漏的问题

**未来隔离级别路线图：**
| 级别 | 工具权限 | 验证的是 | 状态 |
|------|---------|---------|------|
| render-only | 无 | 纯 prompt 质量 | 未实现 |
| tool-assisted | 文件系统只读 | reviewer setup 整体效果 | ← **Round 2 在此** |
| full-agent | 完整工具 | 生产环境代码审查 | 未来 |

## 待办

- [ ] Round 4 — 用 `run.py --api-only --label r4` 对 13 个 case 跑 product/v0.1，生成结构化 `run-r4.json`
- [ ] Round 4 adjudication — 基于 `run-r4.json` 重做 `adjudication-r4.yaml`，不复用 R3 判定
- [ ] Context isolation 方法改进 — API-only reviewer 已无文件系统工具访问；继续记录 `prompt_source/prompt_version` 以防混算
- [ ] 边界 finding 口径校准 — 002-f-002 / 003-f-002 在扩大 fixture 后重新评估
- [ ] 扩大 fixture 数量至 20+ 以满足 release gate
