"""ResonanceForge CLI."""

from __future__ import annotations

import argparse
import json
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resonanceforge",
        description="ResonanceForge — multi-agent AI readiness assessment CLI",
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Company situation / assessment question",
    )
    parser.add_argument(
        "-q",
        "--question-flag",
        dest="question_flag",
        default=None,
        help="Assessment question (alternative to positional)",
    )
    parser.add_argument("--industry", default=None, help="Industry context")
    parser.add_argument(
        "--company-size",
        dest="company_size",
        default=None,
        help="Company size context",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    question = args.question_flag or args.question
    if not question or not str(question).strip():
        parser.error("question is required (positional or -q/--question-flag)")

    from app.graphs.resonance_graph import run_assessment
    from app.services.report import to_markdown

    try:
        report = run_assessment(
            question=str(question).strip(),
            industry=args.industry,
            company_size=args.company_size,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(report.model_dump(), indent=2))
    else:
        print(to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
