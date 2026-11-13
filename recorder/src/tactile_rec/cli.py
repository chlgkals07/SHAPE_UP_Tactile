"""Command line entry point: `tactile-rec`."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from tactile_rec.config import Config, ConfigError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tactile-rec",
        description="Record arm + hand + tactile + camera episodes and convert them to LeRobot v2.1.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="start the hub and the recording UI")
    record.add_argument("--config", required=True, type=Path)
    record.add_argument("--root", type=Path, help="data root (overrides data_root in the config)")
    record.add_argument("--task", help="task name (folder name)")
    record.add_argument("--text", help="task sentence stored with every episode")
    record.add_argument("--operator")
    record.add_argument("--ui", choices=("web", "terminal", "none"), default="web")
    record.add_argument("--host", help="web UI bind address")
    record.add_argument("--port", type=int, help="web UI port")
    record.add_argument(
        "--auto", type=float, metavar="SECONDS",
        help="with --ui none: record episodes of this length without interaction (for testing)",
    )
    record.add_argument("--episodes", type=int, default=1, help="with --auto: how many")

    convert = sub.add_parser("convert", help="raw episodes -> dataset")
    convert.add_argument("--config", required=True, type=Path)
    convert.add_argument("--in", dest="inputs", required=True, nargs="+", type=Path,
                         help="episode, session, task or data-root folders")
    convert.add_argument("--out", required=True, type=Path)
    convert.add_argument("--format", choices=("lerobot", "npz"), default="lerobot")
    convert.add_argument("--repo-id", help="LeRobot repo id, e.g. shape_up/pick_cup")
    convert.add_argument("--fps", type=float, help="dataset fps (overrides the config)")
    convert.add_argument("--image-mode", choices=("image", "video"), default="image",
                         help="how LeRobot stores camera frames (openpi examples use image)")
    convert.add_argument("--include-failed", action="store_true",
                         help="also convert episodes labelled failure")
    convert.add_argument("--include-flagged", action="store_true",
                         help="also convert episodes with dropouts or stale values")
    convert.add_argument("--overwrite", action="store_true")

    inspect = sub.add_parser("inspect", help="summarise recorded episodes")
    inspect.add_argument("path")

    check = sub.add_parser("check", help="run one stream for a few seconds and report")
    check.add_argument("stream")
    check.add_argument("--config", required=True, type=Path)
    check.add_argument("--seconds", type=float, default=5.0)

    tap = sub.add_parser("tap", help="measure time offsets between streams from sharp events")
    tap.add_argument("episode")
    tap.add_argument("--ref", help="reference signal (default: the one with most events)")

    replay = sub.add_parser("replay", help="view an episode in Rerun")
    replay.add_argument("episode")
    replay.add_argument("--save", help="write an .rrd file instead of opening the viewer")
    replay.add_argument("--image-stride", type=int, default=1, help="log every Nth camera frame")
    return parser


def _apply_record_overrides(config: Config, args: argparse.Namespace) -> Config:
    session = dataclasses.replace(
        config.session,
        **{k: v for k, v in (("task", args.task), ("text", args.text),
                             ("operator", args.operator)) if v is not None},
    )
    ui = dataclasses.replace(
        config.ui, **{k: v for k, v in (("host", args.host), ("port", args.port)) if v is not None}
    )
    from tactile_rec.config import _check_label

    _check_label(session.task, "task")
    _check_label(session.operator, "operator")
    return dataclasses.replace(
        config, session=session, ui=ui,
        data_root=args.root.expanduser() if args.root is not None else config.data_root,
    )


def _record(args: argparse.Namespace) -> int:
    from tactile_rec.hub import Hub
    from tactile_rec.record.session import Recorder, RecorderError

    config = _apply_record_overrides(load_config(args.config), args)
    hub = Hub(config)
    recorder = Recorder(hub)
    print(f"[tactile-rec] rig {config.rig_name} ({config.mount}), data under {config.data_root}")
    hub.start()
    try:
        if args.ui == "web":
            from tactile_rec.ui.server import serve

            serve(hub, recorder)
        elif args.ui == "terminal":
            from tactile_rec.ui import terminal

            terminal.run(hub, recorder)
        else:
            if args.auto is None:
                print("error: --ui none needs --auto SECONDS", file=sys.stderr)
                return 2
            time.sleep(2.0)  # let every stream fill its pre-roll buffer
            for _ in range(args.episodes):
                try:
                    number = recorder.start()
                except RecorderError as error:
                    print("not ready:\n  " + "\n  ".join(error.problems), file=sys.stderr)
                    return 1
                end = time.monotonic() + args.auto
                while time.monotonic() < end:
                    time.sleep(0.1)
                    recorder.tick()
                summary = recorder.stop()
                path = recorder.save(True)
                print(f"[tactile-rec] episode {number}: {summary['duration_s']} s -> {path}")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if recorder.state == "recording":
            recorder.discard()
        hub.stop()
    return 0


def _convert(args: argparse.Namespace) -> int:
    from tactile_rec.convert.dataset import (
        LeRobotV21Writer,
        NpzWriter,
        convert_many,
        prepare_output,
    )
    from tactile_rec.convert.episode import ConvertError

    config = load_config(args.config)
    cfg = config.dataset
    if args.fps is not None:
        cfg = dataclasses.replace(cfg, fps=args.fps)
    try:
        prepare_output(args.out, args.overwrite)
        if args.format == "npz":
            writer = NpzWriter(args.out)
        else:
            if not args.repo_id:
                raise ConvertError("--repo-id is required for --format lerobot")
            writer = LeRobotV21Writer(
                args.repo_id, args.out, cfg.fps, cfg.robot_type, args.image_mode
            )
        report = convert_many(
            args.inputs, cfg, writer,
            include_failed=args.include_failed, include_flagged=args.include_flagged,
        )
    except ConvertError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report_path = args.out.parent / f"{args.out.name}.conversion_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\n{report['written']} of {report['found']} episodes written to {args.out} "
        f"({report['skipped']} skipped). Report: {report_path}"
    )
    return 0 if report["written"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "record":
            return _record(args)
        if args.command == "convert":
            return _convert(args)
        if args.command == "inspect":
            from tactile_rec.tools import inspect

            return inspect.run(args.path)
        if args.command == "check":
            from tactile_rec.tools import check

            return check.run(load_config(args.config), args.stream, args.seconds)
        if args.command == "tap":
            from tactile_rec.tools import tap

            return tap.run(args.episode, args.ref)
        from tactile_rec.tools import replay

        return replay.run(args.episode, args.save, args.image_stride)
    except ConfigError as error:
        print(f"config error: {error}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
