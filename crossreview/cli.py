"""CrossReview CLI — ``crossreview pack`` / ``crossreview verify``.

Usage::

    crossreview pack --diff HEAD~1 > pack.json
    crossreview pack --diff HEAD~1 --intent "fix auth" --focus auth > pack.json
    crossreview pack --diff HEAD~1 --task ./task.md --context ./plan.md > pack.json
    crossreview verify --pack pack.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError, resolve_reviewer_config
from .pack import (
    GitDiffError,
    assemble_pack,
    changed_files_from_git,
    compute_pack_completeness,
    diff_from_git,
    pack_to_json,
    read_context_files,
    read_task_file,
)
from .verify import run_verify_pack
from .schema import (
    review_pack_from_dict,
    review_result_to_json,
    validate_review_pack,
    validate_review_result,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crossreview",
        description="Context-isolated verification harness for AI-generated code.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- pack ---
    pack_p = sub.add_parser(
        "pack",
        help="Assemble a ReviewPack from a git diff.",
    )
    pack_p.add_argument(
        "--diff",
        required=True,
        metavar="REF",
        help="Git ref for diff base (e.g. HEAD~1, abc123, main..feat).",
    )
    pack_p.add_argument(
        "--intent",
        default=None,
        help="Task intent string.",
    )
    pack_p.add_argument(
        "--task",
        default=None,
        metavar="FILE",
        help="Path to a task description file (content stored in task_file).",
    )
    pack_p.add_argument(
        "--focus",
        action="append",
        default=None,
        help="Focus area (repeatable).",
    )
    pack_p.add_argument(
        "--context",
        action="append",
        default=None,
        metavar="FILE",
        help="Extra context file path (repeatable).",
    )

    # --- verify (stub) ---
    verify_p = sub.add_parser(
        "verify",
        help="Review a ReviewPack and emit ReviewResult JSON.",
    )
    verify_p.add_argument(
        "--pack",
        required=True,
        metavar="FILE",
        help="Path to a ReviewPack JSON file.",
    )
    verify_p.add_argument("--model", default=None, help="Override reviewer model.")
    verify_p.add_argument("--provider", default=None, help="Override reviewer provider.")
    verify_p.add_argument(
        "--api-key-env",
        default=None,
        metavar="ENV_VAR",
        help="Override API key environment variable name.",
    )

    return parser


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute ``crossreview pack``."""

    # 1. Obtain diff
    try:
        diff = diff_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not diff.strip():
        print("error: git diff produced empty output — nothing to pack.", file=sys.stderr)
        return 1

    # 2. Get changed files via git (NUL-delimited, handles special-char paths)
    try:
        changed_files = changed_files_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # 3. Read optional files
    task_content: str | None = None
    if args.task:
        try:
            task_content = read_task_file(args.task)
        except OSError as exc:
            print(f"error: cannot read task file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: task file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    context_files = None
    if args.context:
        try:
            context_files = read_context_files(args.context)
        except OSError as exc:
            print(f"error: cannot read context file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: context file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    # 4. Assemble
    try:
        pack = assemble_pack(
            diff,
            changed_files=changed_files,
            intent=args.intent,
            task_file=task_content,
            focus=args.focus,
            context_files=context_files,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # 5. Diagnostic to stderr
    completeness = compute_pack_completeness(pack)
    n_files = len(pack.changed_files)
    print(
        f"crossreview pack: {n_files} file(s), completeness={completeness:.2f}, "
        f"artifact={pack.artifact_fingerprint[:12]}",
        file=sys.stderr,
    )

    # 6. JSON to stdout
    print(pack_to_json(pack))
    return 0


def _load_pack(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as exc:
        print(f"error: cannot read pack file: {exc}", file=sys.stderr)
        return None
    except UnicodeDecodeError as exc:
        print(f"error: pack file is not valid UTF-8: {exc}", file=sys.stderr)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: pack file is not valid JSON: {exc}", file=sys.stderr)
        return None

    try:
        return review_pack_from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: pack JSON has invalid structure: {exc}", file=sys.stderr)
        return None


def _cmd_verify(args: argparse.Namespace) -> int:
    """Execute ``crossreview verify --pack pack.json``."""
    pack = _load_pack(args.pack)
    if pack is None:
        return 1

    violations = validate_review_pack(pack)
    if violations:
        print(f"error: invalid ReviewPack: {', '.join(violations)}", file=sys.stderr)
        return 1

    try:
        reviewer_config = resolve_reviewer_config(
            cli_model=args.model,
            cli_provider=args.provider,
            cli_api_key_env=args.api_key_env,
        )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        result = run_verify_pack(pack, reviewer_config)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    violations = validate_review_result(result)
    if violations:
        print(f"error: internal invalid ReviewResult: {', '.join(violations)}", file=sys.stderr)
        return 1

    print(review_result_to_json(result))
    print(
        f"crossreview verify: review_status={result.review_status.value}, "
        f"findings={len(result.findings)}, model={result.reviewer.model}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "pack":
        return _cmd_pack(args)
    if args.command == "verify":
        return _cmd_verify(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def _entry_point() -> None:
    """Console-script entry point — propagates return code to exit status."""
    raise SystemExit(main())
