"""CrossReview CLI — ``crossreview pack`` / ``crossreview verify`` / ``crossreview render-prompt`` / ``crossreview ingest``.

Usage::

    crossreview pack --diff HEAD~1 > pack.json
    crossreview pack --diff HEAD~1 --intent "fix auth" --focus auth > pack.json
    crossreview pack --diff HEAD~1 --task ./task.md --context ./plan.md > pack.json
    crossreview verify --diff HEAD~1                               # one-stop: pack + verify (default: --format human)
    crossreview verify --diff HEAD~1 --intent "fix auth"
    crossreview verify --pack pack.json                            # verify pre-built pack (default: --format json)
    crossreview render-prompt --pack pack.json > prompt.md
    crossreview ingest --raw-analysis raw.md --pack pack.json --model claude-sonnet-4-20250514
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError, resolve_reviewer_config
from .core.prompt import (
    get_default_reviewer_template,
    render_reviewer_prompt,
)
from .formatter import format_human
from .ingest import run_ingest
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
    ReviewPack,
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

    # --- verify ---
    verify_p = sub.add_parser(
        "verify",
        help="Review a change and emit ReviewResult. Accepts --pack (pre-built) or --diff (one-stop).",
    )
    _mode = verify_p.add_mutually_exclusive_group(required=True)
    _mode.add_argument(
        "--pack",
        default=None,
        metavar="FILE",
        help="Path to a ReviewPack JSON file.",
    )
    _mode.add_argument(
        "--diff",
        default=None,
        metavar="REF",
        help="Git ref for diff base (e.g. HEAD~1, abc123, main..feat). Assembles a ReviewPack inline.",
    )
    # pack flags (only meaningful with --diff; ignored with --pack)
    verify_p.add_argument("--intent", default=None, help="Task intent string (--diff mode).")
    verify_p.add_argument("--task", default=None, metavar="FILE", help="Task description file (--diff mode).")
    verify_p.add_argument("--focus", action="append", default=None, help="Focus area, repeatable (--diff mode).")
    verify_p.add_argument(
        "--context",
        action="append",
        default=None,
        metavar="FILE",
        help="Extra context file, repeatable (--diff mode).",
    )
    verify_p.add_argument(
        "--format",
        choices=["json", "human"],
        default=None,
        dest="output_format",
        help="Output format. Defaults to 'human' with --diff, 'json' with --pack.",
    )
    verify_p.add_argument("--model", default=None, help="Override reviewer model.")
    verify_p.add_argument("--provider", default=None, help="Override reviewer provider.")
    verify_p.add_argument(
        "--api-key-env",
        default=None,
        metavar="ENV_VAR",
        help="Override API key environment variable name.",
    )

    # --- render-prompt ---
    rp_p = sub.add_parser(
        "render-prompt",
        help="Render the canonical reviewer prompt from a ReviewPack.",
    )
    rp_p.add_argument(
        "--pack",
        required=True,
        metavar="FILE",
        help="Path to a ReviewPack JSON file.",
    )
    rp_p.add_argument(
        "--template",
        default=None,
        metavar="FILE",
        help="Custom prompt template file (default: built-in product/v0.1).",
    )

    # --- ingest ---
    ingest_p = sub.add_parser(
        "ingest",
        help="Ingest raw analysis text from a host-integrated review and emit ReviewResult JSON.",
    )
    ingest_p.add_argument(
        "--raw-analysis",
        required=True,
        metavar="FILE",
        help="Path to raw analysis text file, or '-' for stdin.",
    )
    ingest_p.add_argument(
        "--pack",
        required=True,
        metavar="FILE",
        help="Path to the original ReviewPack JSON file.",
    )
    ingest_p.add_argument(
        "--model",
        required=True,
        help="Model used by the host (e.g. 'claude-sonnet-4-20250514' or 'host_unknown').",
    )
    ingest_p.add_argument("--prompt-source", default=None, help="Prompt source identifier.")
    ingest_p.add_argument("--prompt-version", default=None, help="Prompt version identifier.")
    ingest_p.add_argument("--latency-sec", type=float, default=None, help="Host-measured LLM latency in seconds.")
    ingest_p.add_argument("--input-tokens", type=int, default=None, help="Host-reported input token count.")
    ingest_p.add_argument("--output-tokens", type=int, default=None, help="Host-reported output token count.")
    ingest_p.add_argument(
        "--format",
        choices=["json", "human"],
        default="json",
        dest="output_format",
        help="Output format (default: json). Use 'human' for terminal-friendly output.",
    )

    return parser


def _build_pack_from_diff(args: argparse.Namespace) -> ReviewPack | None:
    """Assemble a ReviewPack from ``--diff`` args. Returns the pack or None on error.

    Note: ``--intent``, ``--task``, ``--focus``, and ``--context`` are pack flags
    shared by the ``pack`` subcommand and ``verify --diff`` mode; they are ignored
    when ``verify --pack`` is used.
    """
    try:
        diff = diff_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None

    if not diff.strip():
        print("error: git diff produced empty output — nothing to pack.", file=sys.stderr)
        return None

    try:
        changed_files = changed_files_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None

    task_content: str | None = None
    if args.task:
        try:
            task_content = read_task_file(args.task)
        except OSError as exc:
            print(f"error: cannot read task file: {exc}", file=sys.stderr)
            return None
        except UnicodeDecodeError as exc:
            print(f"error: task file is not valid UTF-8: {exc}", file=sys.stderr)
            return None

    context_files = None
    if args.context:
        try:
            context_files = read_context_files(args.context)
        except OSError as exc:
            print(f"error: cannot read context file: {exc}", file=sys.stderr)
            return None
        except UnicodeDecodeError as exc:
            print(f"error: context file is not valid UTF-8: {exc}", file=sys.stderr)
            return None

    try:
        return assemble_pack(
            diff,
            changed_files=changed_files,
            intent=args.intent,
            task_file=task_content,
            focus=args.focus,
            context_files=context_files,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute ``crossreview pack``."""
    pack = _build_pack_from_diff(args)
    if pack is None:
        return 1

    completeness = compute_pack_completeness(pack)
    n_files = len(pack.changed_files)
    print(
        f"crossreview pack: {n_files} file(s), completeness={completeness:.2f}, "
        f"artifact={pack.artifact_fingerprint[:12]}",
        file=sys.stderr,
    )

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
    """Execute ``crossreview verify`` (--pack or --diff mode)."""
    # Resolve output format: --diff defaults to human, --pack defaults to json
    output_format = args.output_format or ("human" if args.diff else "json")

    # Build pack
    if args.diff:
        pack = _build_pack_from_diff(args)
        if pack is None:
            return 1
        completeness = compute_pack_completeness(pack)
        print(
            f"crossreview pack: {len(pack.changed_files)} file(s), completeness={completeness:.2f}, "
            f"artifact={pack.artifact_fingerprint[:12]}",
            file=sys.stderr,
        )
    else:
        _diff_only = [f for f in ("intent", "task", "focus", "context") if getattr(args, f, None)]
        if _diff_only:
            print(
                f"warning: --{'/--'.join(_diff_only)} ignored in --pack mode (only used with --diff)",
                file=sys.stderr,
            )
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

    if output_format == "human":
        print(format_human(result, pack))
    else:
        print(review_result_to_json(result))
    print(
        f"crossreview verify: review_status={result.review_status.value}, "
        f"findings={len(result.findings)}, model={result.reviewer.model}",
        file=sys.stderr,
    )
    return 0


def _cmd_render_prompt(args: argparse.Namespace) -> int:
    """Execute ``crossreview render-prompt --pack pack.json``."""
    pack = _load_pack(args.pack)
    if pack is None:
        return 1

    violations = validate_review_pack(pack)
    if violations:
        print(f"error: invalid ReviewPack: {', '.join(violations)}", file=sys.stderr)
        return 1

    # Load template
    template_source = "product/v0.1"
    if args.template:
        try:
            template = open(args.template, encoding="utf-8").read()
            template_source = args.template
        except OSError as exc:
            print(f"error: cannot read template file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: template file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1
    else:
        template = get_default_reviewer_template()

    rendered = render_reviewer_prompt(template, pack)
    print(rendered)
    print(
        f"crossreview render-prompt: {len(rendered)} chars, template={template_source}",
        file=sys.stderr,
    )
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Execute ``crossreview ingest --raw-analysis FILE --pack pack.json --model MODEL``."""
    pack = _load_pack(args.pack)
    if pack is None:
        return 1

    violations = validate_review_pack(pack)
    if violations:
        print(f"error: invalid ReviewPack: {', '.join(violations)}", file=sys.stderr)
        return 1

    # Read raw analysis
    if args.raw_analysis == "-":
        raw_analysis = sys.stdin.read()
    else:
        try:
            raw_analysis = open(args.raw_analysis, encoding="utf-8").read()
        except OSError as exc:
            print(f"error: cannot read raw analysis file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: raw analysis file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    if not raw_analysis.strip():
        print("error: raw analysis is empty.", file=sys.stderr)
        return 1

    result = run_ingest(
        pack,
        raw_analysis,
        model=args.model,
        prompt_source=args.prompt_source,
        prompt_version=args.prompt_version,
        latency_sec=args.latency_sec,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
    )

    violations = validate_review_result(result)
    if violations:
        print(f"error: internal invalid ReviewResult: {', '.join(violations)}", file=sys.stderr)
        return 1

    if args.output_format == "human":
        print(format_human(result, pack))
    else:
        print(review_result_to_json(result))
    print(
        f"crossreview ingest: review_status={result.review_status.value}, "
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
    if args.command == "render-prompt":
        return _cmd_render_prompt(args)
    if args.command == "ingest":
        return _cmd_ingest(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def _entry_point() -> None:
    """Console-script entry point — propagates return code to exit status."""
    raise SystemExit(main())
