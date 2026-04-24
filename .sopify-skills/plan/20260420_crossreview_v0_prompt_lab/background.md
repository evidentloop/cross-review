# CrossReview v0 Prompt Lab + Phase 1 — 背景

## 目标

验证 "fresh LLM reviewer 能否从 ReviewPack 中稳定产出真 finding"，如果成立则实现 v0 verification core + minimal CLI surface。

默认产品语义优先支持 host-integrated same-model fresh review；standalone provider backend 作为 fallback / portable mode。v0 当前分支可先落地 standalone backend，但这不改变默认用户路径判断。

## 上游 Scope

产品范围定义来自 [docs/v0-scope.md](../../../docs/v0-scope.md)（canonical，Status: Confirmed）。

## 当前阶段

**Phase 1 — 核心管线已完成，进入 Phase 1D (Fixture & Validation)**

- Phase 0.5 Prompt Lab — ✅ 已通过 gate，raw finding 质量可接受。
- Phase 1A Schema & Config — ✅ 全部完成。
- Phase 1B Core Pipeline — ✅ 大部分完成（evidence collector 和 output formatter 除外）。
- Phase 1C CLI — ✅ pack / verify / render-prompt / ingest 全部完成。
- Phase 1D Fixture & Validation — 🔜 进行中。
  - eval harness 框架已就绪（`crossreview_eval.py` 634 行 + 534 行测试），不是从零任务
  - 实际 fixture = 0，Prompt Lab 有 13 个 case 待迁移/形式化
  - 下一步重点：1D.2/1D.3/1D.4（fixture 资产建设 + release gates 达标）

Host-integrated CLI 通道（render-prompt + ingest）已实现。宿主集成不需要实现 Python `ReviewerBackend`；集成方式是 `crossreview render-prompt` → 宿主隔离执行 → `crossreview ingest` 回传。

## Gate

Prompt Lab 通过（模型能稳定给出真问题 + 噪音来源可控）→ ✅ 已进入 Phase 1。

Phase 1 完成 gate：v0 release gates（v0-scope.md §12）达标 → 产品化。

## 非目标

本 plan 不涉及：

- SDK / MCP Server / Agent Skill / CI/CD Action
- Sopify adapter / review.md 资产面
- cross_model_reviewer / skill_guided_reviewer
- verdict = block
- 三层产品线落地（CrossReview > sopify-code-review > Sopify）
