from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "policy_runner"

MUTANTS = {
    "M01": ("align_obs.py", [
        ("arrived = [s for s in stream.recent(0) if s.t_recv_ns <= t_obs_ns]",
         "arrived = list(stream.recent(0))"),
        ("index = int(np.searchsorted(times[rows], t_obs_ns, side=\"right\")) - 1",
         "index = len(rows) - 1"),
    ]),
    "M02": ("align_obs.py", [
        ("usable = {self.hand: has_hand_feedback}", "usable = {}"),
    ]),
    "M03": ("inference.py", [
        ("        except TimeoutError as error:\n            self.close()\n",
         "        except TimeoutError as error:\n"),
    ]),
    "M04": ("chunk.py", [
        ("if not np.isfinite(actions).all():", "if False:"),
    ]),
    "M05": ("executor.py", [
        ("            self._late(now_ns, skipped)",
         "            self._send(now_ns, self.t_start_ns + skipped * self.dt_ns, skipped)"),
    ]),
    "M06": ("executor.py", [
        ("chunk, chunk, grid_ns, 0", "chunk, chunk, chunk.t_reply_ns, 0"),
    ]),
    "M07": ("executor.py", [
        ("        if row >= self.k:\n", "        if row >= len(self.active.actions):\n"),
    ]),
    "M08": ("commands/hand_udp.py", [
        ("np.rad2deg(np.asarray(row, dtype=np.float64)[self.hand])",
         "np.asarray(row, dtype=np.float64)[self.hand]"),
    ]),
    "M09": ("align_obs.py", [
        ("decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)", "decoded = sample.data[\"image\"]"),
    ]),
    "M10": ("executor.py", [
        ("            if self.state not in (RUNNING, HOLD):\n",
         "            if self.state == FAULT:\n"),
    ]),
}


def mutate(text: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"mutant target found {count} times: {old!r}")
        text = text.replace(old, new)
    return text


def run_suite() -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/acceptance", "-x", "-q", "-p", "no:warnings",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    )
    failed = [line for line in result.stdout.splitlines() if line.startswith("FAILED")]
    return result.returncode != 0, failed[0] if failed else result.stdout.strip().splitlines()[-1]


def main() -> int:
    survivors = []
    for mid, (name, replacements) in MUTANTS.items():
        path = SRC / name
        original = path.read_text(encoding="utf-8")
        path.write_text(mutate(original, replacements), encoding="utf-8")
        start = time.monotonic()
        try:
            killed, detail = run_suite()
        finally:
            path.write_text(original, encoding="utf-8")
        verdict = "killed" if killed else "SURVIVED"
        print(f"{mid} {verdict:8s} {time.monotonic() - start:5.1f}s  {detail}", flush=True)
        if not killed:
            survivors.append(mid)
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
