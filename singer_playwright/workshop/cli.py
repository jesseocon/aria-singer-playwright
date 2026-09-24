"""CLI handlers for the Playwright scraper workshop."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from singer_playwright.workshop import client as workshop_client
from singer_playwright.workshop.brief import evaluate_success, load_brief
from singer_playwright.workshop.codegen import compile_recipe_file
from singer_playwright.workshop.daemon import run_daemon
from singer_playwright.workshop.recipe import load_recipe, replay_recipe


def _print_json(payload: Any) -> None:  # noqa: ANN401
    print(json.dumps(payload, indent=2, default=str))


def handle_workshop(args: argparse.Namespace) -> None:
    command = args.workshop_command

    if command == "start":
        run_daemon(
            storage_state_path=args.storage_state,
            headless=not args.headed,
            host=args.host,
            port=args.port,
            detach=args.detach,
        )
        return

    if command == "stop":
        _print_json(workshop_client.stop())
        return

    if command == "observe":
        _print_json(
            workshop_client.observe(
                frame_index=args.frame_index,
                frame_url_pattern=args.frame_url_pattern,
                label=args.label,
            ),
        )
        return

    if command == "goto":
        _print_json(workshop_client.goto(args.url, wait_until=args.wait_until))
        return

    if command == "act":
        params: dict[str, Any] = {}
        if args.selector:
            params["selector"] = args.selector
        if args.value is not None:
            params["value"] = args.value
        if args.url_pattern:
            params["url_pattern"] = args.url_pattern
        if args.frame_url_pattern:
            params["frame_url_pattern"] = args.frame_url_pattern
        if args.frame_index is not None:
            params["frame_index"] = args.frame_index
        if args.timeout_ms is not None:
            params["timeout_ms"] = args.timeout_ms
        if args.ms is not None:
            params["ms"] = args.ms
        if args.query_params:
            params["query_params"] = json.loads(args.query_params)
        _print_json(workshop_client.act(args.action, **params))
        return

    if command == "extract":
        _print_json(
            workshop_client.extract(
                extract_type=args.extract_type,
                selector=args.selector,
                frame_index=args.frame_index,
                frame_url_pattern=args.frame_url_pattern,
                limit=args.limit,
            ),
        )
        return

    if command == "screenshot":
        _print_json(workshop_client.screenshot(name=args.name))
        return

    if command == "evaluate":
        brief = load_brief(args.brief)
        records = json.loads(args.records)
        evaluation = evaluate_success(
            brief,
            records=records,
            login_page=args.login_page,
        )
        _print_json({"ok": evaluation["passed"], "evaluation": evaluation})
        return

    if command == "recipe":
        if args.recipe_command == "save":
            brief = load_brief(args.brief).to_dict()
            sample_records = json.loads(args.records) if args.records else []
            extract = {
                "type": args.extract_type,
                "selector": args.selector,
                "frame_url_pattern": args.frame_url_pattern,
                "frame_index": args.frame_index,
                "limit": args.limit,
            }
            _print_json(
                workshop_client.recipe_save(
                    brief=brief,
                    extract=extract,
                    sample_records=sample_records,
                    output_path=args.output,
                ),
            )
            return

        if args.recipe_command == "replay":
            recipe = load_recipe(args.recipe)
            _print_json(
                replay_recipe(
                    recipe,
                    storage_state_path=args.storage_state,
                    headless=not args.headed,
                    brief_path=args.brief,
                ),
            )
            return

        msg = f"Unknown recipe command: {args.recipe_command}"
        raise SystemExit(msg)

    if command == "codegen":
        manifest = compile_recipe_file(
            args.recipe,
            output_dir=args.output_dir,
            tap_package=args.tap_package,
        )
        _print_json({"ok": True, "manifest": manifest})
        return

    msg = f"Unknown workshop command: {command}"
    raise SystemExit(msg)


def add_workshop_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    workshop = subparsers.add_parser("workshop", help="AI-forward scraper workshop")
    workshop_sub = workshop.add_subparsers(dest="workshop_command", required=True)

    start = workshop_sub.add_parser("start", help="Start persistent workshop daemon")
    start.add_argument("--storage-state", required=True, help="Path to storage_state.json")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=18742)
    start.add_argument("--headed", action="store_true", help="Run browser headed")
    start.add_argument("--detach", action="store_true", help="Fork daemon to background")
    start.set_defaults(workshop_command="start")

    stop = workshop_sub.add_parser("stop", help="Stop workshop daemon")
    stop.set_defaults(workshop_command="stop")

    observe = workshop_sub.add_parser("observe", help="Observe compact page model")
    observe.add_argument("--frame-index", type=int, default=None)
    observe.add_argument("--frame-url-pattern", default=None)
    observe.add_argument("--label", default="current")
    observe.set_defaults(workshop_command="observe")

    goto = workshop_sub.add_parser("goto", help="Navigate main page")
    goto.add_argument("--url", required=True)
    goto.add_argument("--wait-until", default="domcontentloaded")
    goto.set_defaults(workshop_command="goto")

    act = workshop_sub.add_parser("act", help="Perform a page action")
    act.add_argument("action", choices=["click", "fill", "wait", "wait_for_frame", "frame_goto", "assert_authenticated"])
    act.add_argument("--selector", default=None)
    act.add_argument("--value", default=None)
    act.add_argument("--url-pattern", default=None)
    act.add_argument("--frame-url-pattern", default=None)
    act.add_argument("--frame-index", type=int, default=None)
    act.add_argument("--timeout-ms", type=int, default=None)
    act.add_argument("--ms", type=int, default=None)
    act.add_argument("--query-params", default=None, help="JSON object of query params for frame_goto")
    act.set_defaults(workshop_command="act")

    extract = workshop_sub.add_parser("extract", help="Extract candidate records")
    extract.add_argument("--extract-type", default="table")
    extract.add_argument("--selector", default=None)
    extract.add_argument("--frame-index", type=int, default=None)
    extract.add_argument("--frame-url-pattern", default=None)
    extract.add_argument("--limit", type=int, default=50)
    extract.set_defaults(workshop_command="extract")

    screenshot = workshop_sub.add_parser("screenshot", help="Capture screenshot artifact")
    screenshot.add_argument("--name", default="screenshot")
    screenshot.set_defaults(workshop_command="screenshot")

    evaluate = workshop_sub.add_parser("evaluate", help="Evaluate records against a brief")
    evaluate.add_argument("--brief", required=True)
    evaluate.add_argument("--records", required=True, help="JSON array of records")
    evaluate.add_argument("--login-page", action="store_true")
    evaluate.set_defaults(workshop_command="evaluate")

    recipe = workshop_sub.add_parser("recipe", help="Recipe save/replay")
    recipe_sub = recipe.add_subparsers(dest="recipe_command", required=True)

    recipe_save = recipe_sub.add_parser("save", help="Save recipe from current session steps")
    recipe_save.add_argument("--brief", required=True)
    recipe_save.add_argument("--records", default="[]", help="JSON array of sample records")
    recipe_save.add_argument("--extract-type", default="table")
    recipe_save.add_argument("--selector", default=None)
    recipe_save.add_argument("--frame-url-pattern", default=None)
    recipe_save.add_argument("--frame-index", type=int, default=None)
    recipe_save.add_argument("--limit", type=int, default=500)
    recipe_save.add_argument("--output", default=None)
    recipe_save.set_defaults(workshop_command="recipe", recipe_command="save")

    recipe_replay = recipe_sub.add_parser("replay", help="Replay a saved recipe in a cold browser")
    recipe_replay.add_argument("--recipe", required=True)
    recipe_replay.add_argument("--storage-state", required=True)
    recipe_replay.add_argument("--brief", default=None)
    recipe_replay.add_argument("--headed", action="store_true")
    recipe_replay.set_defaults(workshop_command="recipe", recipe_command="replay")

    codegen = workshop_sub.add_parser("codegen", help="Compile recipe into stream scaffolding")
    codegen.add_argument("--recipe", required=True)
    codegen.add_argument("--output-dir", required=True)
    codegen.add_argument("--tap-package", default="tap_lighthouse")
    codegen.set_defaults(workshop_command="codegen")

    workshop.set_defaults(func=handle_workshop)
