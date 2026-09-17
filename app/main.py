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
    parser.add_argument("--company-name", default=None, help="Company name")
    parser.add_argument("--role-title", default=None, help="Requester role title")
    parser.add_argument(
        "--primary-systems",
        default=None,
        help="Primary systems (ERP, CRM, warehouse…)",
    )
    parser.add_argument("--constraints", default=None, help="Budget, compliance, timeline")
    parser.add_argument("--success-metric", default=None, help="Success metric")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip SQLite persistence",
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

    intake = dict(
        industry=args.industry,
        company_size=args.company_size,
        company_name=args.company_name,
        role_title=args.role_title,
        primary_systems=args.primary_systems,
        constraints=args.constraints,
        success_metric=args.success_metric,
    )

    assessment_id = None
    if not args.no_persist:
        from app import db

        db.ensure_db()
        assessment_id = db.create_assessment(
            question=str(question).strip(),
            status="running",
            **intake,
        )

    try:
        report = run_assessment(question=str(question).strip(), **intake)
    except Exception as exc:
        if assessment_id:
            from app import db

            db.update_status(assessment_id, "failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if assessment_id:
        from app import db

        db.save_report(assessment_id, report)
        print(f"Assessment id: {assessment_id}", file=sys.stderr)
        print(f"Share link path: /r/{assessment_id}", file=sys.stderr)

    if args.format == "json":
        print(json.dumps(report.model_dump(), indent=2))
    else:
        print(to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
