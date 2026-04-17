"""Command-line interface for mito-overview."""

from __future__ import annotations

import argparse

from .config import PipelineConfig
from .workflow import list_steps, plan_steps, run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable scaffold for mito-overview")
    parser.add_argument("--config", help="Path to a shell-style config.env file")
    parser.add_argument("--steps", help="Comma-separated subset of workflow steps to run")
    parser.add_argument("--list-steps", action="store_true", help="List available workflow steps and exit")
    parser.add_argument("--dry-run", action="store_true", help="Plan steps and write context files without running them")
    parser.add_argument(
        "--strict-files",
        action="store_true",
        help="Require input paths from the config to exist during validation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_steps:
        for step_name, description in plan_steps():
            print(f"{step_name}\t{description}")
        return 0

    if not args.config:
        raise SystemExit("Missing required --config <config.env>")

    config = PipelineConfig.from_env_file(args.config)
    steps = [step.strip() for step in args.steps.split(",")] if args.steps else list_steps()
    results = run_pipeline(config, steps=steps, dry_run=args.dry_run, strict_files=args.strict_files)
    for result in results:
        print(f"{result.step_name}\t{result.status}\t{result.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
