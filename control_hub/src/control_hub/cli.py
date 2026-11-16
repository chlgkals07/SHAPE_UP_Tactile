"""control-hub serve | validate | status"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from control_hub.checks import CheckRunner
from control_hub.config import ConfigError, load_config
from control_hub.supervisor import STATE_LABEL, Supervisor
from control_hub.tmux import Tmux


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="control-hub", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="웹 UI 를 띄운다")
    serve.add_argument("--config", required=True, type=Path)
    serve.add_argument("--host", help="바인드 주소 (기본: 설정의 ui.host, 127.0.0.1)")
    serve.add_argument("--port", type=int, help="포트 (기본: 설정의 ui.port, 8700)")
    validate = sub.add_parser("validate", help="설정 파일만 검사한다")
    validate.add_argument("--config", required=True, type=Path)
    status = sub.add_parser("status", help="프로세스와 점검 상태를 한 번 출력한다")
    status.add_argument("--config", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate":
        print(f"정상: 프로세스 {len(cfg.processes)}개, 점검 {len(cfg.checks)}개, "
              f"실행표 {len(cfg.profiles)}개, 장치 {len(cfg.devices)}개")
        return 0

    if not Tmux.available():
        print("tmux 가 없습니다: sudo apt install tmux", file=sys.stderr)
        return 2
    tmux = Tmux(cfg.tmux_socket, cfg.tmux_session)

    if args.command == "status":
        runner = CheckRunner(cfg)
        runner.run_once()
        for pid, info in Supervisor(cfg, tmux, runner.results).status().items():
            title = cfg.processes[pid].title if pid in cfg.processes else "(설정에 없음)"
            print(f"{STATE_LABEL[info['state']]:<6} {pid:<18} {title}")
        print()
        for cid, result in runner.results().items():
            mark = "정상" if result.ok else "실패"
            print(f"{mark:<6} {cid:<18} {cfg.checks[cid].title}  {result.detail}")
        return 0

    import uvicorn

    from control_hub.server import create_app

    host, port = args.host or cfg.ui_host, args.port or cfg.ui_port
    print(f"Control Hub: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
    print(f"터미널로 보기: {tmux.attach_hint()}")
    if host not in ("127.0.0.1", "localhost"):
        print("주의: 로그인이 없습니다. 믿을 수 있는 네트워크에서만 씁니다.")
    uvicorn.run(create_app(args.config, tmux), host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
