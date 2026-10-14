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
            capture_types=tuple(t.strip() for t in args.capture_types.split(",") if t.strip())
            if args.capture_types
            else None,
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

    if command == "network":
        _handle_network(args)
        return

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


def _compact_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": catalog.get("path"),
        "call_count": catalog.get("call_count"),
        "since_mark": catalog.get("since_mark"),
        "endpoints": [
            {
                "endpoint": e["endpoint"],
                "count": e["count"],
                "statuses": e["statuses"],
                "response_bytes": e["response_bytes"],
                "query_params": sorted(e["query_params"]),
                "after_marks": e["after_marks"],
                "seqs": e["seqs"][:8],
            }
            for e in catalog.get("endpoints", [])
        ],
    }


def _handle_network(args: argparse.Namespace) -> None:
    sub = args.network_command
    if sub == "mark":
        _print_json(workshop_client.network_mark(args.label))
        return
    if sub == "catalog":
        response = workshop_client.network_catalog(since_mark=args.since_mark, host_pattern=args.host_pattern)
        catalog = response["result"]
        _print_json(catalog if args.full else _compact_catalog(catalog))
        return
    if sub == "show":
        _print_json(workshop_client.network_show(args.seq, preview_chars=args.preview_chars))
        return
    if sub == "replay":
        _print_json(
            workshop_client.network_replay(
                args.seq,
                query=json.loads(args.query) if args.query else None,
                json_patch=json.loads(args.json_patch) if args.json_patch else None,
                body=args.body,
                url=args.url,
                method=args.method,
                preview_chars=args.preview_chars,
            ),
        )
        return
    msg = f"Unknown network command: {sub}"
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
    start.add_argument(
        "--capture-types",
        default=None,
        help="Comma-separated Playwright resource types to record (default: xhr,fetch,eventsource)",
    )
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

    network = workshop_sub.add_parser("network", help="Catalog and replay captured page API calls")
    network_sub = network.add_subparsers(dest="network_command", required=True)

    network_mark = network_sub.add_parser("mark", help="Insert a labelled marker into the capture log")
    network_mark.add_argument("--label", required=True)

    network_catalog = network_sub.add_parser("catalog", help="Group captured calls by endpoint")
    network_catalog.add_argument("--since-mark", default=None, help="Only calls after the last mark with this label")
    network_catalog.add_argument("--host-pattern", default=None, help="Regex filter on request host")
    network_catalog.add_argument("--full", action="store_true", help="Print shapes, frames, and samples")

    network_show = network_sub.add_parser("show", help="Show one captured call with a body preview")
    network_show.add_argument("--seq", type=int, required=True)
    network_show.add_argument("--preview-chars", type=int, default=2000)

    network_replay = network_sub.add_parser("replay", help="Re-issue a captured call with overrides")
    network_replay.add_argument("--seq", type=int, required=True)
    network_replay.add_argument("--query", default=None, help="JSON object of query param overrides (null removes)")
    network_replay.add_argument("--json-patch", default=None, help="JSON object of dotted-path body overrides")
    network_replay.add_argument("--body", default=None, help="Replacement raw request body")
    network_replay.add_argument("--url", default=None, help="Replacement URL")
    network_replay.add_argument("--method", default=None)
    network_replay.add_argument("--preview-chars", type=int, default=1000)
    network.set_defaults(workshop_command="network")

    codegen = workshop_sub.add_parser("codegen", help="Compile recipe into stream scaffolding")
    codegen.add_argument("--recipe", required=True)
    codegen.add_argument("--output-dir", required=True)
    codegen.add_argument("--tap-package", default="tap_lighthouse")
    codegen.set_defaults(workshop_command="codegen")

    workshop.set_defaults(func=handle_workshop)
