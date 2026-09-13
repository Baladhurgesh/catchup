from __future__ import annotations

import argparse
import asyncio
import logging

from agent.orchestrator import new_job, process_job
from slack.bot import start
from util import parse_youtube_urls


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CatchUp — YouTube talks to a short podcast")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single job from the CLI instead of starting the Slack bot",
    )
    parser.add_argument("--urls", help="YouTube URLs, comma or newline separated")
    parser.add_argument("--focus", default="the most important technical ideas")
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument(
        "--expertise",
        default="intermediate",
        choices=["beginner", "intermediate", "expert"],
    )
    parser.add_argument(
        "--style",
        default="conversational",
        choices=["concise", "conversational", "technical", "debate"],
    )
    return parser


async def run_once(args: argparse.Namespace) -> None:
    urls = parse_youtube_urls(args.urls or "")
    if not urls:
        raise SystemExit("Pass at least one YouTube URL with --urls")

    job = new_job(
        urls,
        focus=args.focus,
        target_minutes=args.minutes,
        expertise=args.expertise,
        style=args.style,
    )

    async def progress(message: str) -> None:
        print(message)
        print()

    result = await process_job(job, update_slack=progress)
    if result.episode:
        print(f"Title: {result.episode.title}")
        print(f"Script: {result.script_path}")
        print(f"MP3: {result.mp3_path or 'not generated'}")
        print(f"Drive: {result.drive_url or 'not uploaded'}")
        print(f"Notion: {result.notion_url or 'not created'}")
        if result.evaluation:
            print(
                f"Words: {result.evaluation.actual_words} / {result.evaluation.target_words} | "
                f"Claims: {result.evaluation.grounded_claim_count} | "
                f"Coverage: {result.evaluation.source_coverage}/{result.evaluation.source_total}"
            )
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f" - {warning}")
    if result.job.status == "failed":
        raise SystemExit(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args()
    if args.once:
        asyncio.run(run_once(args))
        return
    start()


if __name__ == "__main__":
    main()
