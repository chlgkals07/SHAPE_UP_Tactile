from __future__ import annotations

import argparse
import json
import time
import urllib.request


def call(base: str, path: str, method: str = "GET") -> dict:
    request = urllib.request.Request(f"{base}{path}", method=method)
    with urllib.request.urlopen(request, timeout=5) as reply:
        return json.loads(reply.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", default="http://127.0.0.1:8810")
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()
    call(args.ui, "/api/arm", "POST")
    end = time.monotonic() + args.seconds
    resets = 0
    while time.monotonic() < end:
        state = call(args.ui, "/api/state")
        if state["state"] == "FAULT":
            print(f"fault: {state['problems'][-1] if state['problems'] else '?'}", flush=True)
            call(args.ui, "/api/reset", "POST")
            call(args.ui, "/api/arm", "POST")
            resets += 1
        time.sleep(0.2)
    final = call(args.ui, "/api/disarm", "POST")
    print(f"resets {resets}, rows sent {final['sent']['sent']}, trace {final['trace']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
