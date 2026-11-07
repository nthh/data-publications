"""Run pinned validator console scripts with socket access disabled."""
from __future__ import annotations

import json
from importlib.metadata import entry_points, version
from pathlib import Path
import socket
import sys


class OfflineNetworkAttempt(RuntimeError):
    """Raised when a validator tries to use the network."""


def install_network_guard():
    attempted = {"value": False}

    def denied(*_args, **_kwargs):
        attempted["value"] = True
        raise OfflineNetworkAttempt("OFFLINE GUARD: validator attempted a network operation")

    original = (socket.create_connection, socket.getaddrinfo,
                socket.socket.connect, socket.socket.connect_ex)
    socket.create_connection = denied
    socket.getaddrinfo = denied
    socket.socket.connect = denied
    socket.socket.connect_ex = denied

    def restore():
        socket.create_connection, socket.getaddrinfo = original[:2]
        socket.socket.connect, socket.socket.connect_ex = original[2:]

    return attempted, restore


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("rashid", "stac-check"):
        print("usage: offline_cli.py {rashid|stac-check} [arguments...]", file=sys.stderr)
        return 2
    command, tool_args = args[0], args[1:]
    pins_path = Path(__file__).with_name("pins.json")
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    expected = pins["tools"][command]
    actual = version(command)
    if actual != expected:
        print(f"Pinned tool version mismatch: {command} expected {expected}, found {actual}", file=sys.stderr)
        return 87
    scripts = {ep.name: ep for ep in entry_points(group="console_scripts")}
    if command not in scripts:
        print(f"Installed console entry point not found: {command}", file=sys.stderr)
        return 88

    attempted, restore = install_network_guard()
    sys.argv = [command, *tool_args]
    try:
        try:
            scripts[command].load()()
            result = 0
        except SystemExit as exc:
            result = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        except OfflineNetworkAttempt as exc:
            print(str(exc), file=sys.stderr)
            result = 86
        if attempted["value"]:
            print("OFFLINE GUARD: validator attempted a network operation", file=sys.stderr)
            if result == 0:
                result = 86
        return result
    finally:
        restore()


if __name__ == "__main__":
    raise SystemExit(main())
