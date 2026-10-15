"""실행기 · CLI · 비교 보고서. API 클라이언트는 가짜로 바꿔 돌린다. 네트워크 호출은 없다."""
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from golden_pipeline import cli, evidence, storage
from golden_pipeline.improvement import PREVENTION_RULES
from golden_pipeline.plan import load_plan

GENERATOR = ["--model", "generator-test", "--reasoning-effort", "low", "--price", "1", "4"]
VALIDATOR = ["--model", "validator-test", "--reasoning-effort", "high", "--price", "1", "4"]
A_ONLY = ["--max-rounds", "3", "--validator-model", "validator-test",
          "--validator-reasoning-effort", "high", "--validator-price", "1", "4"]
LIMITS = ["--max-calls", "50", "--budget", "1"]
BUDGET = {"question": "사업 예산은 얼마인가?", "answer": "130,000,000원(부가세 포함)", "evidence": ["E1"],
          "structure": {"value": "130,000,000", "unit": "원"}, "secondary_tags": []}
# 같은 질문에 근거의 다른 값(계약 기간)을 답한 후보. 독립 답과 달라 거절된다.
WRONG = {**BUDGET, "answer": "12개월", "structure": {"value": "12", "unit": "개월"}}
BOND = {"question": "입찰 보증금은 입찰 금액의 몇 % 이상인가?", "answer": "입찰 금액의 5% 이상", "evidence": ["E2"],
        "structure": {"value": "5", "unit": "%"}, "secondary_tags": []}
VERDICTS = {
    "E1": {"answerable": True, "answer": "130,000,000원", "conditions": ["부가세 포함"], "conflict": False,
           "comparison": None},
    "E2": {"answerable": True, "answer": "입찰 금액의 5% 이상", "conditions": [], "conflict": False, "comparison": None},
}
SCREEN = (storage.PROMPTS / "screen.txt").read_text(encoding="utf-8")
# 호출마다 입력 10 · 출력 10 토큰, 단가 1 · 4 USD / 100만 토큰.
CALL_USD = 50 / 1_000_000


class FakeAPI:
    """생성기와 검증기를 함께 맡는 가짜 API. 사용자 메시지가 검증기 입력(JSON)이면 검증기로 답한다.

    생성기: 예산 묶음은 answer_mismatch 예방 규칙을 받기 전엔 틀린 값을, 받은 뒤엔 맞는 값을 답하고,
    보증금 묶음은 늘 맞게 답하며, 표 묶음은 늘 JSON 이 아닌 글을 낸다.
    """

    def __init__(self, crash_on=None):
        self.requests, self.validations, self.crash_on = [], 0, crash_on

    def __call__(self, model, reasoning_effort, messages):
        system, user = messages[0]["content"], messages[1]["content"]
        self.requests.append((model, reasoning_effort, user))
        if system == SCREEN:
            # 출시 전 쓸모 판정: 보증금 질문은 쓸모 없다고 본다.
            useful = "보증금" not in json.loads(user)["question"]
            text = json.dumps({"useful": useful, "code": None if useful else "useless_answer", "reason": "판정 이유"},
                              ensure_ascii=False)
        elif user.startswith("{"):
            text = self._verdict(json.loads(user))
        elif "130,000,000원" in user:
            text = json.dumps(BUDGET if PREVENTION_RULES["answer_mismatch"] in system else WRONG, ensure_ascii=False)
        elif "5%" in user:
            text = json.dumps(BOND, ensure_ascii=False)
        else:
            text = "표만으로는 질문을 만들 수 없습니다"
        return {"model": model, "text": text, "input_tokens": 10, "output_tokens": 10}

    def _verdict(self, asked):
        self.validations += 1
        if self.validations == self.crash_on:
            raise ConnectionError("검증 도중 끊김")
        [unit] = asked["evidence"]
        return json.dumps(VERDICTS[unit["label"]], ensure_ascii=False)


@pytest.fixture
def api(monkeypatch):
    """cli.api_client 를 가짜로 바꾼다. opened 는 클라이언트를 연 횟수다."""
    fake = FakeAPI()
    fake.opened = 0

    @contextmanager
    def client():
        fake.opened += 1
        yield fake
    monkeypatch.setattr(cli, "api_client", client)
    return fake


@pytest.fixture
def planned(evidence_run, measure_bundles, monkeypatch):
    """CLI 로 계획 p3 을 만든다: train 몫 numeric 묶음 셋 (예산 · 보증금 · 표) 과
    A loop 가 정책을 재는, 예산 묶음을 본뜬 validation · held-out 묶음 하나씩."""
    monkeypatch.setattr(evidence, "PACKAGE", evidence_run)
    golden("plan", "p3", "ev1", "--count", "numeric", "3", "--max-context-chars", "2000")
    bundles = {"budget" if "130,000,000원" in b["context"] else "bond" if "5%" in b["context"] else "table": b["bundle_id"]
               for b in load_plan("p3")[0]["bundles"]}
    measure_bundles("p3")
    return bundles


def golden(*args):
    cli.main([str(arg) for arg in args])


def export_c(tmp_path, rows):
    """웹에서 내보낸 C 결과(JSONL)와 관측 기록. rows 는 (묶음 id, 출력 행) 이거나 그대로 쓸 글이다."""
    export, sidecar = tmp_path / "c.jsonl", tmp_path / "sidecar.json"
    lines = [row if isinstance(row, str) else json.dumps({**row[1], "bundle_id": row[0]}, ensure_ascii=False)
             for row in rows]
    export.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sidecar.write_text(json.dumps({"model_label": "GPT-6 pro", "run_date": "2026-10-14"}), encoding="utf-8")
    return export, sidecar


def import_c(tmp_path, rows):
    export, sidecar = export_c(tmp_path, rows)
    golden("import", "--topic", "numeric", "--plan", "p3", "--id", "c1", "--export", export, "--sidecar", sidecar)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def test_a_b_and_c_run_through_audit_release_and_report(planned, api, tmp_path, capsys):
    golden("run", "--topic", "numeric", "--method", "A", "--plan", "p3", "--id", "l1", *GENERATOR, *LIMITS, *A_ONLY)
    golden("run", "--topic", "numeric", "--method", "B", "--plan", "p3", "--id", "b1", *GENERATOR, *LIMITS)
    golden("audit", "--topic", "numeric", "--method", "B", "--id", "b1", *VALIDATOR, *LIMITS)
    import_c(tmp_path, [(planned["budget"], BUDGET), (planned["bond"], BOND), ("b-unplanned", BOND), "JSON 아님"])
    golden("audit", "--topic", "numeric", "--method", "C", "--id", "c1", *VALIDATOR, *LIMITS)
    golden("release", "--topic", "numeric", "--version", "v1", "--run", "A:l1-r1", "--run", "A:l1-r2", *VALIDATOR, *LIMITS)
    golden("report", "--topic", "numeric", "--id", "cmp", "--a", "l1", "--b", "b1", "--c", "c1")

    # 검증을 통과해도 쓸모 판정에서 빠진 항목(보증금)은 출시되지 않고, 이유와 함께 매니페스트에 남는다.
    released = read_jsonl(storage.OUTPUTS / "goldens/numeric/releases/v1/golden.jsonl")
    assert [item["answer"] for item in released] == [BUDGET["answer"]]
    assert released[0]["state_history"][-1]["reason"] == "자동 검증 · 쓸모 판정 통과"
    screen = json.loads((storage.OUTPUTS / "goldens/numeric/releases/v1/manifest.json").read_text(encoding="utf-8"))["release"]
    assert (screen["screened"], screen["calls"]) == (2, 2)
    assert [(row["question"].endswith(BOND["question"]), row["reason"]) for row in screen["dropped"]] == [(True, "판정 이유")]
    report = json.loads((storage.OUTPUTS / "goldens/numeric/reports/cmp.json").read_text(encoding="utf-8"))
    assert report["runs"] == {"A": ["l1-r1", "l1-r2", "l1-r3"], "B": ["b1"], "C": ["c1"]}
    a, b, c = (report["methods"][method] for method in "ABC")
    # A: round 1 예산 거절 · 보증금 통과 · 표 JSON 아님, round 2 예산 통과 · 표 JSON 아님, round 3 표 JSON 아님.
    assert (a["outputs"], a["validated"], a["pending"]) == (6, 3, 0)
    assert a["valid_rate"] == ratio(2, 6)
    assert (a["source_accuracy"], a["type_compliance"], a["duplicates"]) == (ratio(2, 3), ratio(3, 3), ratio(0, 3))
    assert a["coverage"] == ratio(2, 3) and a["difficulty"]["easy"] == ratio(2, 2)
    assert a["generation"] == {"input_tokens": 60, "output_tokens": 60, "cost_usd": pytest.approx(6 * CALL_USD)}
    assert a["total_cost_usd"] == pytest.approx(9 * CALL_USD)
    assert a["cost_per_valid_item"]["value"] == pytest.approx(9 * CALL_USD / 2)
    # B: 계획의 다섯 묶음을 모두 부르고, 고정 프롬프트라 예산 셋은 끝까지 틀린 값이다. 커버리지는 train 묶음 셋으로 잰다.
    assert (b["outputs"], b["valid_rate"], b["source_accuracy"], b["coverage"]) == (5, ratio(1, 5), ratio(1, 4), ratio(1, 3))
    assert b["total_cost_usd"] == pytest.approx(9 * CALL_USD)
    # C: 계획에 없는 묶음 · JSON 아닌 줄은 항목이 되지 못해 유형 검사까지 가지 못한다.
    assert (c["outputs"], c["valid_rate"], c["type_compliance"], c["coverage"]) == (4, ratio(2, 4), ratio(2, 2), ratio(2, 3))
    # 추론 강도는 역할마다 API 호출에 실리고, loop 시작 기록 · 생성 매니페스트 · 검증 기록에 남는다.
    assert {(effort, user.startswith("{")) for _, effort, user in api.requests} == {("low", False), ("high", True)}
    loop = json.loads((storage.OUTPUTS / "goldens/numeric/loops/l1/start.json").read_text(encoding="utf-8"))["config"]
    assert (loop["generator"]["reasoning_effort"], loop["validator"]["reasoning_effort"]) == ("low", "high")
    run = storage.OUTPUTS / "goldens/numeric/runs/A/l1-r1"
    assert json.loads((run / "manifest.json").read_text(encoding="utf-8"))["generation"]["run_config"]["reasoning_effort"] == "low"
    assert json.loads((run / "validation.json").read_text(encoding="utf-8"))["run_config"]["reasoning_effort"] == "high"
    table = capsys.readouterr().out
    assert "| 유효 문항률 | 2/6 = 33.3% | 1/5 = 20.0% | 2/4 = 50.0% |" in table


def test_c_unobserved_cost_and_tokens_are_reported_as_unobserved_not_zero(planned, api, tmp_path, capsys):
    # 웹에서 만든 C 의 생성 비용을 0 으로 채우면 C 가 공짜처럼 보이고 유효 문항당 비용이 왜곡된다.
    import_c(tmp_path, [(planned["bond"], BOND)])
    golden("audit", "--topic", "numeric", "--method", "C", "--id", "c1", *VALIDATOR, *LIMITS)
    golden("report", "--topic", "numeric", "--id", "c-only", "--c", "c1")

    c = json.loads((storage.OUTPUTS / "goldens/numeric/reports/c-only.json").read_text(encoding="utf-8"))["methods"]["C"]
    assert c["generation"] == {"input_tokens": "unobserved", "output_tokens": "unobserved", "cost_usd": "unobserved"}
    assert c["validation"] == {"input_tokens": 10, "output_tokens": 10, "cost_usd": pytest.approx(CALL_USD)}
    assert c["total_cost_usd"] == "unobserved"
    assert c["cost_per_valid_item"] == {"numerator": "unobserved", "denominator": 1, "value": "unobserved"}
    table = capsys.readouterr().out
    assert "| 생성 토큰 (입력 / 출력) | unobserved / unobserved |" in table
    assert "| 유효 문항당 비용 USD | unobserved/1 = unobserved |" in table


def test_a_report_refuses_runs_made_from_different_plans(planned, api):
    # 다른 근거 묶음 · 목표 분포로 만든 run 을 나란히 놓으면 방식이 아니라 입력을 견주게 된다.
    golden("run", "--topic", "numeric", "--method", "B", "--plan", "p3", "--id", "b1", *GENERATOR, *LIMITS)
    golden("plan", "p1", "ev1", "--count", "numeric", "1", "--max-context-chars", "2000")
    golden("run", "--topic", "numeric", "--method", "B", "--plan", "p1", "--id", "b2", *GENERATOR, *LIMITS)

    with pytest.raises(ValueError, match="같은 계획"):
        golden("report", "--topic", "numeric", "--id", "mixed", "--b", "b1", "b2")


def test_a_report_refuses_a_requested_loop_with_no_generated_round(planned, api):
    # 고른 A 를 말없이 빼고 쓰면 요청한 A · B 비교가 B 만의 보고서로 바뀐다.
    golden("run", "--topic", "numeric", "--method", "B", "--plan", "p3", "--id", "b1", *GENERATOR, *LIMITS)

    with pytest.raises(SystemExit, match="nonexistent"):
        golden("report", "--topic", "numeric", "--id", "cmp", "--a", "nonexistent", "--b", "b1")
    assert not (storage.OUTPUTS / "goldens/numeric/reports").exists()


PAID = {
    "run A": ["run", "--topic", "numeric", "--method", "A", "--plan", "p3", "--id", "l1", *GENERATOR, *LIMITS, *A_ONLY],
    "run B": ["run", "--topic", "numeric", "--method", "B", "--plan", "p3", "--id", "b1", *GENERATOR, *LIMITS],
    "audit": ["audit", "--topic", "numeric", "--method", "B", "--id", "b1", *VALIDATOR, *LIMITS],
}


@pytest.mark.parametrize("command, missing", [
    *[(command, flag) for command in PAID for flag in ("--model", "--reasoning-effort", "--max-calls", "--budget")],
    ("run A", "--validator-reasoning-effort"),
])
def test_paid_commands_refuse_to_start_without_model_effort_call_cap_and_budget(planned, api, command, missing):
    # 값 하나라도 기본값으로 채우면 정하지 않은 모델 · 한도로 유료 호출이 나간다.
    args = PAID[command]
    at = args.index(missing)
    with pytest.raises(SystemExit):
        golden(*args[:at], *args[at + 2:])
    assert api.opened == 0 and not api.requests
    assert not (storage.OUTPUTS / "goldens").exists()


def test_a_resumed_loop_continues_from_its_pinned_config_without_duplicate_ids(planned, api):
    # round 2 의 채택을 재는 v0 검증 호출에서 끊긴다 (round 1 검증 두 번 뒤).
    api.crash_on = 3
    with pytest.raises(ConnectionError):
        golden("run", "--topic", "numeric", "--method", "A", "--plan", "p3", "--id", "l1", *GENERATOR, *LIMITS, *A_ONLY)
    api.crash_on = None

    golden("resume", "--topic", "numeric", "--method", "A", "--id", "l1")

    loop = storage.OUTPUTS / "goldens/numeric/loops/l1"
    assert json.loads((loop / "report.json").read_text(encoding="utf-8"))["stop_reason"] == "max_rounds"
    # 끝난 round 1 과 생성까지 끝난 v0 은 다시 생성하지 않는다:
    # r1 3 + v0 · v2 1 + r2 2 + v3 1 + r3 1 + h-base · h-final 1 번.
    assert sum(not user.startswith("{") for _, _, user in api.requests) == 11
    ids = [entry["candidate_id"] for entry in storage.read_catalog()]
    assert len(ids) == len(set(ids)) == 8
    # 끝난 loop 는 다시 돌지 않는다.
    with pytest.raises(FileExistsError):
        golden("resume", "--topic", "numeric", "--method", "A", "--id", "l1")


def test_a_resumed_audit_judges_only_the_pending_candidates_and_releases(planned, api, tmp_path):
    # 한도에 닿아 남은 후보를 이어서 검증하지 못하면, 그 run 을 다시 생성해 생성 비용을 또 내야 한다.
    reworded = {**BOND, "question": "입찰 보증금은 입찰 금액의 몇 % 이상이어야 하나?"}
    import_c(tmp_path, [(planned["bond"], BOND), (planned["bond"], reworded), (planned["budget"], BUDGET)])
    golden("audit", "--topic", "numeric", "--method", "C", "--id", "c1", *VALIDATOR, "--max-calls", "1", "--budget", "1")
    run_dir = storage.run_path("numeric", "C", "c1")
    first_text = (run_dir / "validation.json").read_text(encoding="utf-8")
    first = json.loads(first_text)
    assert (first["status"], first["pending"], first["counts"]) == (
        "call_cap", ["numeric-C-c1-0003"], {"auto_validated": 1, "rejected": 1},
    )

    golden("resume", "--topic", "numeric", "--method", "C", "--id", "c1", "--max-calls", "10", "--budget", "1")

    second = json.loads((run_dir / "validation-2.json").read_text(encoding="utf-8"))
    assert second["continues"] == {"file": "validation.json", "sha256": storage._sha256(run_dir / "validation.json")}
    assert (second["status"], second["pending"], second["run_config"]["model"]) == ("complete", [], "validator-test")
    judged = [row for name in ("accepted.jsonl", "rejected.jsonl")
              for row in read_jsonl(run_dir / name) if "candidate_id" in row]
    ids = [row["candidate_id"] for row in judged]
    assert len(ids) == len(set(ids)) == 3
    # 중복은 첫 검증에서 무료로 거절되고 재개 때 다시 판정하지 않는다.
    [duplicate] = [row for row in judged if row["state"] == "rejected"]
    assert duplicate["question"].endswith(f"사업에서 {reworded['question']}")
    assert duplicate["state_history"][-1]["reason"].startswith("중복")
    # 앞 기록이 바뀌면 이어 쓴 기록의 continues 와 맞지 않아, 바뀐 비용이 보고서 · 출시본에 들어가지 못한다.
    (run_dir / "validation.json").write_text(json.dumps({**first, "cost_usd": 9.0}), encoding="utf-8")
    for command in (("report", "--topic", "numeric", "--id", "cmp", "--c", "c1"),
                    ("release", "--topic", "numeric", "--version", "v1", "--run", "C:c1", *VALIDATOR, *LIMITS)):
        with pytest.raises(storage.CatalogError, match="validation-2.json"):
            golden(*command)
    (run_dir / "validation.json").write_text(first_text, encoding="utf-8")
    golden("release", "--topic", "numeric", "--version", "v1", "--run", "C:c1", *VALIDATOR, *LIMITS)
    manifest = json.loads((storage.OUTPUTS / "goldens/numeric/releases/v1/manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 1 and "validation-2.json" in manifest["sources"]["C/c1"]
    with pytest.raises(ValueError, match="pending 후보가 없습니다"):
        golden("resume", "--topic", "numeric", "--method", "C", "--id", "c1", "--max-calls", "10", "--budget", "1")


def test_a_resumed_audit_refuses_a_changed_validator_criterion(planned, api, tmp_path):
    # 한 run 의 후보를 서로 다른 기준으로 판정하면 그 run 의 통과율이 한 기준의 결과가 아니게 된다.
    import_c(tmp_path, [(planned["bond"], BOND), (planned["budget"], BUDGET)])
    golden("audit", "--topic", "numeric", "--method", "C", "--id", "c1", *VALIDATOR, "--max-calls", "1", "--budget", "1")
    prompt = storage.PROMPTS / "validator.txt"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\n바뀐 기준", encoding="utf-8")
    asked = len(api.requests)

    with pytest.raises(ValueError, match=r"기준이 다릅니다: \['prompt_sha256'\]"):
        golden("resume", "--topic", "numeric", "--method", "C", "--id", "c1", "--max-calls", "10", "--budget", "1")
    assert len(api.requests) == asked


def test_both_launchers_call_the_one_cli_and_start_nothing_else():
    # 실행기마다 로직을 따로 두면 Windows 와 macOS 의 흐름이 갈라진다. 노트북 · 질문 화면 서버는 이 실행기의 일이 아니다.
    for name in ("golden.cmd", "golden.command"):
        text = (storage.PACKAGE / name).read_text(encoding="utf-8")
        calls = [line for line in text.splitlines() if "python" in line and not line.lstrip().startswith(("rem", "#"))]
        assert calls and all("-m golden_pipeline.cli" in line for line in calls)
        assert not [word for word in ("jupyter", "ipynb", "nbconvert", "uvicorn", "frontend", "npm") if word in text]


def test_the_launcher_for_this_platform_reaches_the_cli_from_another_folder(tmp_path):
    windows = os.name == "nt"
    launcher = storage.PACKAGE / ("golden.cmd" if windows else "golden.command")
    command = ["cmd", "/c", str(launcher), "--help"] if windows else ["bash", str(launcher), "--help"]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, timeout=120)
    assert result.returncode == 0
    assert b"usage: golden" in result.stdout and b"release" in result.stdout


def test_api_client_sends_the_effort_and_returns_the_reported_model_text_and_tokens_and_closes(monkeypatch):
    # 추론 강도가 호출에 실리지 않으면 기록에 남은 강도와 실제로 쓴 강도가 다르다.
    # 응답의 모델 이름 대신 요청한 이름을 남기면 실제로 어떤 모델이 답했는지가 기록에서 사라진다.
    # 본문 없는 응답(거절 · 길이 초과)을 None 으로 넘기면 run 이 예외로 멈춰 이미 낸 호출 기록이 사라진다.
    opened = []

    class OpenAI:
        def __init__(self, max_retries):
            opened.append("open")
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, model, reasoning_effort, messages, response_format):
            # 출력 계약이 JSON 객체 하나라, JSON 모드가 빠지면 형식만 틀린 출력이 거절로 쌓인다.
            assert response_format == {"type": "json_object"}
            opened.append(reasoning_effort)
            return SimpleNamespace(model=f"{model}-2026-10-01", choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
                                   usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            opened.append("closed")

    monkeypatch.setattr(cli.openai, "OpenAI", OpenAI)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: None)
    with cli.api_client() as call:
        response = call(model="gpt-x", reasoning_effort="high", messages=[])

    assert response == {"model": "gpt-x-2026-10-01", "text": "", "input_tokens": 7, "output_tokens": 3}
    assert opened == ["open", "high", "closed"]
