from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

MS = 1_000_000


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summarize(events: list[dict]) -> list[str]:
    kinds = Counter(e["ev"] for e in events)
    sends = [e for e in events if e["ev"] == "send"]
    replies = [e for e in events if e["ev"] == "reply"]
    chunks = [e for e in events if e["ev"] == "chunk"]
    faults = [e for e in events if e["ev"] == "state" and e["state"] == "FAULT"]
    lateness = [(e["t_ns"] - e["due_ns"]) / MS for e in sends]
    ticks = kinds["send"] + kinds["late"] + kinds["hold"]
    rtts = [e["rtt_ms"] for e in replies if e["ok"]]
    failed = Counter(p.split(":")[0] for e in replies if not e["ok"] for p in e["problems"])
    lines = [
        f"events {dict(kinds)}",
        f"ticks while armed {ticks}: send {kinds['send']}, late {kinds['late']}, "
        f"hold {kinds['hold']} ({100 * kinds['hold'] / max(ticks, 1):.1f}%)",
        f"chunks {len(chunks)}: adopted {sum(c['adopted'] for c in chunks)}, "
        f"rejected {sum(not c['adopted'] for c in chunks)}",
        f"replies ok {len(rtts)}, failed {dict(failed)}",
        f"faults {len(faults)}: {Counter(f['reason'].split(':')[0] for f in faults)}",
    ]
    if lateness:
        lines.append(f"send lateness ms p50 {percentile(lateness, .5):.2f} "
                     f"p99 {percentile(lateness, .99):.2f} max {max(lateness):.2f}")
    if rtts:
        lines.append(f"rtt ms p50 {percentile(rtts, .5):.1f} p99 {percentile(rtts, .99):.1f} "
                     f"max {max(rtts):.1f}")
    return lines


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    events = [json.loads(line) for line in path.read_text().splitlines() if line]
    print("\n".join(summarize(events)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
