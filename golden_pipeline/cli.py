"""골든 파이프라인 실행기. golden.cmd (Windows) 와 golden.command (macOS) 가 모두 이 모듈 하나를 부른다.

API 를 부르는 명령(run · audit · resume)은 모델 · 추론 강도 · 단가 · 최대 호출 수 · 예산을 모두 받아야 시작한다.
기본값을 두지 않아, 값을 정하지 않은 채 유료 호출이 나가지 않는다.
"""
import argparse
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import openai
from dotenv import load_dotenv

from golden_pipeline import evidence, generation, improvement, plan, report, storage, validation
from golden_pipeline.schema import TOPICS


def main(argv=None):
    args = _parser().parse_args(argv)
    print(args.handler(args))


@contextmanager
def api_client():
    """명령 하나 동안 OpenAI 클라이언트 하나를 열어 생성기 · 검증기가 함께 쓰고, 명령이 끝나면 닫는다.

    키는 저장소 .env 의 OPENAI_API_KEY 다. model 은 요청한 이름이 아니라 API 응답이 알려 준 이름을 돌려준다.
    거절 · 길이 초과로 본문이 없으면 빈 글을 돌려줘, run 을 멈추지 않고 그 출력을 거절 행으로 남긴다.
    """
    load_dotenv(storage.PACKAGE.parent / ".env")
    with openai.OpenAI(max_retries=3) as client:
        def call(model, reasoning_effort, messages):
            response = client.chat.completions.create(model=model, reasoning_effort=reasoning_effort, messages=messages)
            return {"model": response.model, "text": response.choices[0].message.content or "",
                    "input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
        yield call


def _evidence(args):
    return evidence.run(args.run_id, args.copy)


def _plan(args):
    counts = {topic: int(n) for topic, n in args.count}
    return plan.make_plan(args.plan_id, args.evidence_run, counts, args.max_context_chars, package=evidence.PACKAGE)


def _run(args):
    """A 는 자기 개선 loop (생성 → 검증 → 실패 기록을 round 마다), B 는 고정 프롬프트 생성만 한다 (검증은 audit)."""
    generator = _priced(args.model, args.reasoning_effort, args.price)
    limits = {"max_calls": args.max_calls, "budget_usd": args.budget}
    if args.method == "B":
        if args.max_rounds or args.validator_model or args.validator_reasoning_effort or args.validator_price:
            raise SystemExit("--max-rounds · --validator-model · --validator-reasoning-effort · --validator-price 는 A 만 받습니다")
        with _config_file({**generator, **limits}) as path, api_client() as call:
            return generation.generate("B", args.topic, args.plan, args.id, path, call)
    if not (args.max_rounds and args.validator_model and args.validator_reasoning_effort and args.validator_price):
        raise SystemExit("A 는 --max-rounds · --validator-model · --validator-reasoning-effort · --validator-price 도 받아야 시작합니다")
    validator = _priced(args.validator_model, args.validator_reasoning_effort, args.validator_price)
    config = {"max_rounds": args.max_rounds, **limits, "generator": generator, "validator": validator}
    with _config_file(config) as path, api_client() as call:
        return _json(improvement.improve(args.topic, args.plan, args.id, path, call, call))


def _resume(args):
    """A 는 끊긴 loop 를 start.json 에 고정된 설정으로 잇고, B · C 는 한도에 닿은 검증의 pending 후보를 검증한다.

    B · C 의 모델 · 단가는 앞 검증 기록의 것을 그대로 쓰고, 새 최대 호출 수 · 예산만 받는다.
    """
    if args.method == "A":
        if args.max_calls or args.budget:
            raise SystemExit("A 의 한도는 loop 를 시작할 때 고정됩니다. --max-calls · --budget 없이 이으세요")
        start = storage._read_json(improvement._loop_path(args.topic, args.id) / "start.json")
        with _config_file(start["config"]) as path, api_client() as call:
            return _json(improvement.improve(args.topic, start["plan_id"], args.id, path, call, call))
    if not (args.max_calls and args.budget):
        raise SystemExit("B · C 의 검증을 이으려면 --max-calls · --budget 을 받아야 합니다")
    storage.read_validated(args.topic, args.method, args.id)
    run_dir = storage.run_path(args.topic, args.method, args.id)
    last = storage._read_json(storage.validation_records(run_dir)[-1])
    config = {**last["run_config"], "max_calls": args.max_calls, "budget_usd": args.budget}
    with _config_file(config) as path, api_client() as call:
        return validation.resume_validation(args.topic, args.method, args.id, path, call)


def _import(args):
    return generation.import_c(args.topic, args.plan, args.id, args.export, args.sidecar)


def _audit(args):
    config = {**_priced(args.model, args.reasoning_effort, args.price), "max_calls": args.max_calls, "budget_usd": args.budget}
    with _config_file(config) as path, api_client() as call:
        return validation.validate(args.topic, args.method, args.id, path, call)


def _release(args):
    runs = [tuple(run.split(":", 1)) for run in args.run]
    return validation.release(args.topic, args.version, runs, args.confirmations)


def _report(args):
    rounds = []
    for loop_id in args.a or []:
        # 생성한 round 가 없는 loop 를 빼고 쓰면 요청한 비교가 말없이 다른 비교가 된다.
        found = [run_dir.name for run_dir in improvement._rounds(args.topic, loop_id)]
        if not found:
            raise SystemExit(f"loop {loop_id} 에 생성한 round 가 없습니다")
        rounds += found
    path, compared = report.write_report(args.topic, args.id, {"A": rounds, "B": args.b, "C": args.c})
    return f"{report.render(compared)}\n\n{path}"


def _priced(model, reasoning_effort, price):
    return {"model": model, "reasoning_effort": reasoning_effort, "usd_per_million_input_tokens": price[0], "usd_per_million_output_tokens": price[1]}


@contextmanager
def _config_file(config):
    """생성 · 검증 · loop 는 설정을 파일로 받는다. 내용과 SHA-256 은 run 매니페스트 · 검증 기록 · start.json 에 남으므로
    파일은 outputs 아래 임시 폴더에 두었다가 지운다."""
    storage.OUTPUTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=storage.guard(storage.OUTPUTS)) as folder:
        path = Path(folder) / "config.json"
        path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        yield path


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


def _parser():
    parser = argparse.ArgumentParser(prog="golden", description="골든 데이터 파이프라인 (golden_pipeline/README.md)")
    commands = parser.add_subparsers(dest="command", required=True)
    _prepare_commands(commands)
    _paid_commands(commands)
    _record_commands(commands)
    return parser


def _prepare_commands(commands):
    command = commands.add_parser("evidence", help="v11 근거 어댑터 (API 호출 없음)")
    command.add_argument("run_id")
    command.add_argument("copy", help="내려받은 압축의 안쪽 RFP_Preprocessing_Final_v11_Team 폴더")
    command.set_defaults(handler=_evidence)

    command = commands.add_parser("plan", help="주제별 개수 · 근거 묶음을 고정한 분포 계획 (API 호출 없음)")
    command.add_argument("plan_id")
    command.add_argument("evidence_run", help="golden_pipeline/outputs/evidence 아래 근거 어댑터 run_id")
    command.add_argument("--count", nargs=2, action="append", required=True, metavar=("TOPIC", "N"),
                         help="주제와 목표 개수. 주제마다 한 번씩")
    command.add_argument("--max-context-chars", type=int, required=True)
    command.set_defaults(handler=_plan)


def _paid_commands(commands):
    command = commands.add_parser("run", help="A 자기 개선 loop 또는 B 생성 (유료 호출)")
    _target(command, ("A", "B"))
    command.add_argument("--plan", required=True)
    _limits(command)
    command.add_argument("--max-rounds", type=int, help="A 만: 최대 round 수")
    command.add_argument("--validator-model", help="A 만: 검증기 모델")
    command.add_argument("--validator-reasoning-effort", help="A 만: 검증기 추론 강도 (예: low · medium · high)")
    command.add_argument("--validator-price", nargs=2, type=float, metavar=("IN", "OUT"),
                         help="A 만: 검증기 단가 (USD / 100만 토큰)")
    command.set_defaults(handler=_run)

    command = commands.add_parser("resume", help="끊긴 A loop, 또는 한도에 닿은 B · C 검증의 pending 후보를 잇기 (유료 호출)")
    _target(command, ("A", "B", "C"))
    command.add_argument("--max-calls", type=int, help="B · C 만: 이번에 쓸 최대 호출 수")
    command.add_argument("--budget", type=float, help="B · C 만: 이번에 쓸 예산 USD")
    command.set_defaults(handler=_resume)

    command = commands.add_parser("audit", help="B · C run 의 독립 검증 (유료 호출)")
    _target(command, ("B", "C"))
    _limits(command)
    command.set_defaults(handler=_audit)


def _record_commands(commands):
    command = commands.add_parser("import", help="C 가져오기 (API 호출 없음)")
    command.add_argument("--topic", choices=TOPICS, required=True)
    command.add_argument("--plan", required=True)
    command.add_argument("--id", required=True, help="새 C run_id")
    command.add_argument("--export", nargs="+", required=True, help="웹에서 내보낸 JSONL 파일들")
    command.add_argument("--sidecar", required=True, help="관측 기록 JSON")
    command.set_defaults(handler=_import)

    command = commands.add_parser("release", help="검증한 run 들을 출시본으로 (API 호출 없음)")
    command.add_argument("--topic", choices=TOPICS, required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--run", action="append", required=True, metavar="METHOD:RUN_ID")
    command.add_argument("--confirmations", help="사람이 held 항목을 확인한 JSONL")
    command.set_defaults(handler=_release)

    command = commands.add_parser("report", help="A · B · C 비교 보고서 (API 호출 없음)")
    command.add_argument("--topic", choices=TOPICS, required=True)
    command.add_argument("--id", required=True, help="새 보고서 id")
    command.add_argument("--a", nargs="+", metavar="LOOP_ID", help="A 자기 개선 loop id")
    command.add_argument("--b", nargs="+", metavar="RUN_ID")
    command.add_argument("--c", nargs="+", metavar="RUN_ID")
    command.set_defaults(handler=_report)


def _target(command, methods):
    command.add_argument("--topic", choices=TOPICS, required=True)
    command.add_argument("--method", choices=methods, required=True)
    command.add_argument("--id", required=True, help="run_id (A 는 loop_id)")


def _limits(command):
    command.add_argument("--model", required=True)
    command.add_argument("--reasoning-effort", required=True, help="추론 강도 (예: low · medium · high)")
    command.add_argument("--price", nargs=2, type=float, required=True, metavar=("IN", "OUT"),
                         help="단가 (USD / 100만 토큰)")
    command.add_argument("--max-calls", type=int, required=True)
    command.add_argument("--budget", type=float, required=True, help="총예산 USD")


if __name__ == "__main__":
    main()
