# Dogfood Record Convention

> **版本**: v1
> **状态**: 约定已确认，`--save-dogfood` CLI 实现待执行

## 目录结构

```
{project-root}/
└── .crossreview/
    ├── .gitignore          # 可提交；内容: dogfood/
    └── dogfood/
        ├── index.jsonl     # 每行一条摘要记录
        └── runs/
            ├── 20260428T173000-a1b2c3d4.json
            ├── 20260429T091500-e5f6a7b8.json
            └── ...
```

### 设计决策

| 决策 | 理由 |
|------|------|
| 放在被 review 仓库 | CrossReview 是独立产品，不依赖 Sopify 目录结构 |
| `.crossreview/` 命名空间 | 和 CrossReview 品牌一致，不和 `.sopify-skills/` 混 |
| `.gitignore` 可提交 | 所有 clone 自动忽略 `dogfood/`；不碰 `.git/info/exclude` |
| dogfood 不进 git | 原始使用数据不是 ground truth，不需要版本管理 |
| JSONL index + full JSON runs | 机器可查（`wc -l` 看次数，`jq` 算分布），同时保留完整信号 |

## 文件命名

```
{YYYYMMDD}T{HHMMSS}-{artifact_fingerprint[:8]}.json
```

- `artifact_fingerprint` = ReviewResult 中的 `artifact_fingerprint` 字段（= `sha256(diff_content)`，pack 阶段计算）
- 时间戳精确到秒，消除同 diff 重复 dogfood 的覆盖风险

## index.jsonl 字段

每行一个 JSON 对象：

```json
{
  "schema_version": "1",
  "crossreview_version": "0.1.0a2",
  "run_id": "20260428T173000-a1b2c3d4",
  "timestamp": "2026-04-28T17:30:00+08:00",
  "repo": "cross-review",
  "diff_source": {
    "type": "committed",
    "base": "HEAD~1",
    "head": "HEAD",
    "captured_at": null
  },
  "artifact_fingerprint": "a1b2c3d4e5f6a7b8...",
  "pack_fingerprint": "f7e8d9c0b1a2...",
  "review_status": "complete",
  "verdict": "pass_candidate",
  "findings_count": 2,
  "high_count": 0,
  "model": "claude-sonnet-4-20250514",
  "command": "crossreview verify --diff HEAD~1 --format json",
  "intent": "refactor: streamline review result assembly"
}
```

### 字段说明

| 字段 | 来源 | 说明 |
|------|------|------|
| `schema_version` | 固定 `"1"` | 约定版本，便于未来迁移 |
| `crossreview_version` | `crossreview.__version__` | 回溯 prompt 版本和回归 |
| `run_id` | 计算 | `{timestamp_compact}-{artifact_fingerprint[:8]}` |
| `timestamp` | 运行时 | ISO 8601 带时区 |
| `repo` | git remote 或目录名 | 被 review 的仓库 |
| `diff_source` | ReviewPack | diff 来源。committed/range 记录 base/head；staged/unstaged 记录 captured_at |
| `artifact_fingerprint` | ReviewResult | `sha256(diff_content)` |
| `pack_fingerprint` | ReviewResult | `sha256(pack_json_without_pack_fp)` |
| `review_status` | ReviewResult | `complete` / `rejected` / `failed` |
| `verdict` | ReviewResult | `pass_candidate` / `concerns` / `needs_human_triage` / `inconclusive` |
| `findings_count` | ReviewResult | emitted findings 数量 |
| `high_count` | ReviewResult | severity=high 的 finding 数量 |
| `model` | ReviewResult `.reviewer.model` | 执行 review 的模型 |
| `command` | 运行时 | 完整命令行（便于复现） |
| `intent` | ReviewResult | 任务意图（如果提供了 `--intent`） |

## runs/ 文件内容

完整的 `ReviewResult` JSON（`crossreview verify --format json` 的原始输出）。不做任何裁剪或变换。

## .gitignore 内容

```gitignore
dogfood/
```

只忽略 `dogfood/` 子目录。`.gitignore` 文件本身可提交。

## CLI 实现计划（待执行）

```bash
# 目标 UX
crossreview verify --diff HEAD~1 --save-dogfood
crossreview verify --staged --save-dogfood

# 等价于手工：
crossreview verify --diff HEAD~1 --format json > .crossreview/dogfood/runs/{run_id}.json
# + 自动追加 index.jsonl
```

实现要点：
- `--save-dogfood` 与 `--format` 独立（`--save-dogfood` 总是存 JSON，终端输出仍受 `--format` 控制）
- 自动创建 `.crossreview/dogfood/runs/` 目录
- 自动创建 `.crossreview/.gitignore`（如不存在）
- `--dogfood-dir DIR` 可选覆盖默认路径
