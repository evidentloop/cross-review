# CrossReview — 项目背景

## 是什么

CrossReview 是一个独立验证引擎，核心价值是 **context isolation**：用全新 LLM session（无生产过程上下文）对 code diff 进行独立审查，产出结构化 finding 和 advisory verdict。

## 为什么做

手工 fresh-session cross-review 已被证明有效——新开 session 往往比原 session 的"自审"更容易发现回归、遗漏和逻辑不一致。但手工流程不可重复、不可度量、每次 ~5 分钟 copy-paste。

CrossReview 把这个手工模式协议化：ReviewPack（结构化输入）→ Finding（结构化输出）→ Verdict（建议性判定）。

## 上游决策来源

产品命名、架构边界、MVP 范围等核心决策来自上游方案包 `sopify-skills/.sopify-skills/plan/20260418_cross_review_engine/`（Q1-Q9 已拍板）。

## 当前定位

验证型 incubator。不是正式产品发布仓库。v0 release gate 通过后再考虑产品化。
