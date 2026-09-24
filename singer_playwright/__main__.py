"""CLI entry point: ``python -m singer_playwright auth|workshop ...``."""

from __future__ import annotations

import argparse

from singer_playwright.auth import run_interactive_auth
from singer_playwright.workshop.cli import add_workshop_parser, handle_workshop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="singer-playwright")
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="Interactive login → storage_state.json")
    auth.add_argument("--url", required=True, help="Login page URL")
    auth.add_argument(
        "--out",
        default="storage_state.json",
        help="Output path for storage_state.json",
    )
    auth.add_argument(
        "--success-pattern",
        default=None,
        help="Optional regex matched against URL when login succeeds",
    )

    add_workshop_parser(sub)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "auth":
        run_interactive_auth(
            login_url=args.url,
            output_path=args.out,
            success_url_pattern=args.success_pattern,
        )
        return

    if args.command == "workshop":
        handle_workshop(args)
        return


if __name__ == "__main__":
    main()
