"""`tactile-rec inspect <path>`: what is in an episode (or in every episode under a folder)."""

from __future__ import annotations

from tactile_rec.convert.load import Episode, find_episodes


def describe(episode: Episode) -> list[str]:
    meta = episode.meta
    flags = meta.get("flags", {})
    lines = [
        f"{episode.name}   {meta.get('result')}   {meta['duration_s']:.1f} s   "
        f"task={meta['task']}   mount={meta['mount']}",
        f"  text: {meta.get('text', '')}",
    ]
    for name, count in flags.get("dropouts", {}).items():
        lines.append(f"  FLAG: {name} dropped out {count} time(s)")
    if flags.get("forced_start"):
        lines.append("  FLAG: started although the pre-check failed")
    lines.append(f"  {'stream':12s} {'count':>7s} {'Hz':>7s} {'expected':>8s} {'max gap':>9s} "
                 f"{'missed':>6s}  fields")
    for name, stream in meta["streams"].items():
        stats = stream["stats"]
        fields = ", ".join(
            f"{key}{field['shape']}" for key, field in stream["fields"].items()
        )
        extra = f"  write-dropped {stats['dropped_write']}" if stats.get("dropped_write") else ""
        lines.append(
            f"  {name:12s} {stats['count']:7d} {stats['hz']:7.1f} {stream['nominal_hz']:8.0f} "
            f"{stats['max_gap_ms']:7.1f}ms {stats['missed']:6d}  {fields}{extra}"
        )
    return lines


def run(path: str, out=print) -> int:
    paths = find_episodes(path)
    if not paths:
        out(f"error: no episodes under {path}")
        return 2
    for episode_path in paths:
        for line in describe(Episode(episode_path)):
            out(line)
        out("")
    out(f"{len(paths)} episode(s)")
    return 0
