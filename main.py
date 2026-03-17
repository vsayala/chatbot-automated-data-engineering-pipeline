"""Single entry point for local agentic data engineering automation."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

import uvicorn

from agentic_de_pipeline.config import load_config
from agentic_de_pipeline.services.chat_api import create_app
from agentic_de_pipeline.workflow.bootstrap import build_orchestrator


def _print_summary(summary) -> None:
    payload = asdict(summary)
    payload["generated_at"] = summary.generated_at.isoformat()
    for stage in payload["stage_results"]:
        stage["started_at"] = stage["started_at"].isoformat()
        stage["finished_at"] = stage["finished_at"].isoformat()
    print(json.dumps(payload, indent=2))


def run_once(config_path: str) -> None:
    """Run a single orchestration cycle."""
    config = load_config(config_path)
    orchestrator = build_orchestrator(config)
    summary = orchestrator.run_once()
    if summary:
        _print_summary(summary)
    else:
        print(json.dumps({"status": "no_work_items"}, indent=2))


def run_loop(config_path: str) -> None:
    """Continuously process work items in polling mode."""
    config = load_config(config_path)
    orchestrator = build_orchestrator(config)

    while True:
        summary = orchestrator.run_once()
        if summary:
            _print_summary(summary)
        time.sleep(config.runtime.poll_interval_seconds)


def serve_chat(config_path: str, host: str, port: int) -> None:
    """Run the chatbot approval API server."""
    app = create_app(config_path)
    uvicorn.run(app, host=host, port=port)


def run_preflight(config_path: str) -> None:
    """Run preflight validation checks and print report."""
    config = load_config(config_path)
    orchestrator = build_orchestrator(config)
    checks = orchestrator.preflight_validator.validate_or_raise()
    print(json.dumps({"checks": checks}, indent=2))


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Agentic data engineering CI/CD orchestrator")
    parser.add_argument(
        "--config",
        default="config/config_simulate.yaml",
        help="Path to config file",
    )

    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run-once", help="Process one work item")
    subcommands.add_parser("run-loop", help="Continuously process work items")
    subcommands.add_parser("preflight", help="Run service connectivity checks")

    serve_parser = subcommands.add_parser("serve-chat", help="Start chatbot API server")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)

    return parser.parse_args()


def main() -> None:
    """CLI dispatcher."""
    args = parse_args()
    if args.command == "run-once":
        run_once(args.config)
    elif args.command == "run-loop":
        run_loop(args.config)
    elif args.command == "preflight":
        run_preflight(args.config)
    elif args.command == "serve-chat":
        serve_chat(args.config, args.host, args.port)


if __name__ == "__main__":
    main()
