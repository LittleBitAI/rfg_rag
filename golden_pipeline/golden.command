#!/bin/bash
# 골든 데이터 파이프라인: 받은 인자를 모두 CLI 하나(python -m golden_pipeline.cli)에 넘긴다.
# 지금 폴더는 바꾸지 않는다. --export 같은 상대 경로가 명령을 친 곳 기준으로 읽혀야 하기 때문이다.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Finder 에서 더블클릭하면 인자가 없다. 명령 목록을 보여 준다.
[ $# -eq 0 ] && set -- --help
PYTHONPATH="$ROOT" exec "$ROOT/.venv/bin/python" -m golden_pipeline.cli "$@"
