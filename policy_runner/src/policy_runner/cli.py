from __future__ import annotations

import argparse
import statistics
import sys
import time

from tactile_rec.hub import Hub

from policy_runner import config as runner_config
from policy_runner import fake_server
from policy_runner.chunk import check_reply
from policy_runner.inference import (
    ACTION_DIM,
    Disconnected,
    InferTimeout,
    PolicyClient,
    ServerError,
    manifest_problems,
)
from policy_runner.manifest import Manifest
from policy_runner.runner import Runner, StartError, synthetic_request


def load_or_exit(path: str, allow_hand: bool) -> runner_config.RunnerConfig:
    try:
        return runner_config.load(path, allow_hand=allow_hand)
    except runner_config.ConfigError as error:
        for problem in error.problems:
            print(f"config: {problem}", file=sys.stderr)
        raise SystemExit(1) from error


def cmd_check(args: argparse.Namespace) -> int:
    cfg = load_or_exit(args.config, args.allow_hand)
    print(f"rig {cfg.rig.rig_name} ({cfg.rig.source}), mode {cfg.mode}")
    print(f"policy {cfg.endpoint}, checkpoint {cfg.manifest.checkpoint}")
    print(f"streams {', '.join(cfg.required_streams)}; prompt {cfg.prompt!r}")
    print(f"K {cfg.exec_horizon} of H {cfg.manifest.pred_horizon} at {cfg.rig.dataset.fps} fps")
    return 0


def cmd_fake_server(args: argparse.Namespace) -> int:
    manifest = Manifest.load(args.manifest).to_dict()
    server = fake_server.start(args.host, args.port, metadata={"manifest": manifest},
                               delay_ms=args.delay_ms, jitter_ms=args.jitter_ms,
                               nan_every=args.nan_every, bad_shape_every=args.bad_shape_every,
                               stall_every=args.stall_every, drop_every=args.drop_every,
                               error_every=args.error_every)
    print(f"[fake-server] ws://{args.host}:{server.port} (hold policy, delay {args.delay_ms} ms)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    cfg = load_or_exit(args.config, allow_hand=True)
    client = PolicyClient(args.endpoint or cfg.endpoint, cfg.connect_timeout_s)
    try:
        metadata = client.connect()
    except Disconnected as error:
        print(error, file=sys.stderr)
        return 1
    differences = manifest_problems(cfg.manifest, metadata)
    print(f"metadata keys {sorted(metadata)}")
    for line in differences:
        print(f"manifest: {line}")
    request = synthetic_request(cfg, Hub(cfg.rig))
    rtts, infers, problems = [], [], []
    try:
        for _ in range(args.count):
            start = time.monotonic()
            reply = client.infer(request, args.timeout_ms / 1000)
            rtts.append((time.monotonic() - start) * 1000)
            infers.append(reply.get("server_timing", {}).get("infer_ms"))
            problems += check_reply(reply, cfg.manifest.pred_horizon, ACTION_DIM)
    except (InferTimeout, Disconnected, ServerError) as error:
        print(f"probe stopped after {len(rtts)} replies: {error}", file=sys.stderr)
        return 1
    finally:
        client.close()
    print(f"first {rtts[0]:.1f} ms; rest median {statistics.median(rtts[1:] or rtts):.1f} ms, "
          f"max {max(rtts[1:] or rtts):.1f} ms over {len(rtts)} requests")
    server_ms = [v for v in infers[1:] if v is not None]
    if server_ms:
        print(f"server infer median {statistics.median(server_ms):.1f} ms")
    for problem in sorted(set(problems)):
        print(f"reply: {problem}")
    return 1 if differences or problems else 0


def cmd_run(args: argparse.Namespace) -> int:
    from policy_runner import ui

    cfg = load_or_exit(args.config, args.allow_hand)
    runner = Runner(cfg)
    try:
        runner.start()
    except StartError as error:
        print(f"[policy-runner] {error}", file=sys.stderr)
        runner.stop()
        return 1
    print(f"[policy-runner] {cfg.mode}, trace {runner.trace_path}")
    try:
        ui.serve(runner)
    finally:
        runner.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="policy-runner")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a runner config against its rig and manifest")
    check.add_argument("config")
    check.add_argument("--allow-hand", action="store_true")
    check.set_defaults(fn=cmd_check)

    fake = sub.add_parser("fake-server", help="serve a hold policy with the openpi protocol")
    fake.add_argument("--manifest", required=True)
    fake.add_argument("--host", default="127.0.0.1")
    fake.add_argument("--port", type=int, default=8000)
    fake.add_argument("--delay-ms", type=float, default=0.0)
    fake.add_argument("--jitter-ms", type=float, default=0.0)
    fake.add_argument("--nan-every", type=int, default=0)
    fake.add_argument("--bad-shape-every", type=int, default=0)
    fake.add_argument("--stall-every", type=int, default=0)
    fake.add_argument("--drop-every", type=int, default=0)
    fake.add_argument("--error-every", type=int, default=0)
    fake.set_defaults(fn=cmd_fake_server)

    probe = sub.add_parser("probe", help="send synthetic observations and time the replies")
    probe.add_argument("config")
    probe.add_argument("--endpoint", default="")
    probe.add_argument("--count", type=int, default=20)
    probe.add_argument("--timeout-ms", type=float, default=30000)
    probe.set_defaults(fn=cmd_probe)

    run = sub.add_parser("run", help="run the policy against the rig with the web UI")
    run.add_argument("config")
    run.add_argument("--allow-hand", action="store_true")
    run.set_defaults(fn=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
