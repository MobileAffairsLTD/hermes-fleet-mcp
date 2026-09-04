"""Command-line entry point for the hermes-fleet MCP server."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .auth import generate_key
from .server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hermes-fleet-mcp",
        description="MCP server exposing a Hermes deployment's state + chat surface.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("gen-key", help="Generate a bearer token")
    gen.add_argument("--output", "-o", help="Write the key to a file instead of stdout")

    serve_p = sub.add_parser("serve", help="Run the MCP server (streamable HTTP)")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port (default 8000)")
    serve_p.add_argument("--token", help="Bearer token (or --token-file / HERMES_FLEET_MCP_TOKEN)")
    serve_p.add_argument("--token-file", help="Read the bearer token from a file")
    serve_p.add_argument("--hermes-home", help="Override HERMES_HOME (default: $HERMES_HOME or ~/.hermes)")
    serve_p.add_argument("--hermes-bin", default="hermes", help="Path to the hermes CLI (default: hermes on PATH)")
    serve_p.add_argument(
        "--allowed-host",
        action="append",
        dest="allowed_hosts",
        metavar="HOST",
        help="Re-enable DNS-rebinding protection and whitelist this Host header value "
        "(repeatable). Pass your public domain/hostname (e.g. dmsdevteam1.ngrok.app) "
        "or host:* to allow any port. Localhost is always allowed.",
    )

    args = parser.parse_args(argv)

    if args.command == "gen-key":
        key = generate_key()
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(key + "\n")
            print(f"Key written to {args.output}", file=sys.stderr)
        else:
            print(key)
        return 0

    if args.command == "serve":
        serve(
            host=args.host,
            port=args.port,
            token=args.token,
            token_file=args.token_file,
            hermes_home=args.hermes_home,
            hermes_bin=args.hermes_bin,
            allowed_hosts=args.allowed_hosts,
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
