"""H1 단계 3 — 시험 보강 (시험 지도 docs/h1-test-map.md 의 '빠진 것·일부'를 채운 시험). 인터넷·claude·키 없음.

무엇을 채웠나 (지도의 번호 → 시험)
- S1~S4  status·실행 요약의 L 오류 세기 = 보고서(설계 §10.2e 마지막 결정): errors.jsonl ∪ runs.jsonl 종료 코드 2 를
         run_id 로 합침, ④ false_positive 는 빼고 따로, 창 = h1._in_window(+같은 시각의 창 만들기 전 실행 빼기),
         다른 시장 줄 안 셈, 창이 다 차면 S+62 까지(그 뒤는 연장). 같은 장면에서 status·요약·보고서 --final 숫자가 같음
- G1     ②-3: 하루 기록의 env 만 다른 봉(code_hash 는 같음)도 '다른 지문' (돌연변이 M27 이 살아남았던 곳)
- G2     종료 코드 1: 파이썬이 cli 에 닿기 전에 죽음(import 실패) — 실제 `python h1.py` 하위 프로세스
- G3     재시작해도 판정 기록은 그대로, 새 창의 같은 (날짜, 트레이너, 종목)은 그 기록을 다시 씀(LLM 0번, 사전 등록 ⑤·§3.6)
- G4     실행 수준: 판정 기록 가운데 줄이 깨지면 L24·종료 코드 2·장부 그대로, status 는 알리기만
- G5~G7  L 음성 대조 보강: L5(그날그날 보유+매수 대기 ≤ 5), L10(A1 종가 현금 ≥ 1 = 쓸어 담기 누락),
         L19(빈자리 부족 후보가 있는데 빈자리를 다 안 채움) — 돌연변이 M35·M36·M37 이 살아남았던 곳
- G8     시각 경계(정각): 봉 시작 next_open 정각 → late, 묻기 직전 next_open 정각 → late_no_llm, KS200 22:30:00 정각 D7,
         start 가 next_open(S) 정각이면 거절 — 돌연변이 M31~M34
- G9     T-DELIST 국내: 정리 비용에 그 봉 날짜 국내 매도세, 대기 주문 dropped(why delist), corp_actions.jsonl·changes.jsonl
- G10    W 등급: 정상 장면(제때·팀장 ok·정지 없음·종목군 다 받음)에서 W1~W5 가 하나도 없음(거짓 양성 없음)
- G11    ⑩ 고정 값: rule_constants 가 설계 숫자와 같음, start 가 meta.rules 에 그대로 적음, 어느 칸이 달라도 종료 코드 3
- G12    ① 시장별 판정: 다른 시장의 L·멈춤 기록이 이 시장의 보고서·status 숫자에 섞이지 않음
- G13    ⑦ 기록: 정정 확정도 corp_actions.jsonl·changes.jsonl 에 남음(분할은 T-RETRO 가 봄)
"""
import copy
import shutil
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst                # noqa: E402
import h1                     # noqa: E402
import h1_check               # noqa: E402
import h1_fake_source as fs   # noqa: E402
import h1_report as R         # noqa: E402
import h1_repo_guard as rg    # noqa: E402
import h1_synth as hs         # noqa: E402
import main                   # noqa: E402
import markets                # noqa: E402
import team                   # noqa: E402
import test_h1_report as TR   # noqa: E402  (장면 도우미만 씀: _fin_h·_short_with_l_run·_fp_scenario·recommit·jline)
import test_h1_runner as tr   # noqa: E402

KST, ET = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")


class NoNet(BaseException):
    """인터넷에 나가려 하면 시험이 깨진다(받기 실패로 조용히 넘어가지 않게 BaseException)."""


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    """진짜 claude 금지 · 인터넷 금지 · 잠금에서 실제로 기다리지 않음 · 저장소 state/·results/ 를 건드리면 실패."""
    import h1_repo_guard as rg                                   # 저장소 state/·results/ 앞뒤 비교(단계 3 검토 T-3)
    repo_before = rg.snapshot(ROOT)

    def boom(*a, **k):
        raise AssertionError("시험이 진짜 claude 를 부르려 했어요")
    monkeypatch.setattr(analyst, "analyze_logged", boom)
    monkeypatch.setattr(analyst, "analyze", boom)
    monkeypatch.setattr(analyst, "claude_cli_version", boom)

    def no_net(*a, **k):
        raise NoNet("시험이 인터넷에 나가려 했어요")
    monkeypatch.setattr(urllib.request, "urlopen", no_net)
    real_run = subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]).endswith("claude"):
            raise AssertionError("시험이 claude 프로세스를 띄우려 했어요")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guarded)

    def no_wait(s):
        raise AssertionError("잠금이 실제로 기다리려 했어요")
    monkeypatch.setattr(h1, "_lock_sleep", no_wait)
    yield
    moved = rg.changes(repo_before, rg.snapshot(ROOT))
    assert not moved, "시험이 저장소 state/·results/ 를 건드렸어요(이미 있던 맥 장부 포함): " + "; ".join(moved[:5])


# ============================ 도우미 ============================

def status_text(mk, root):
    return "\n".join(h1.status(mk, root))


def same_counts(mk, root):
    """같은 장면에서 status·window_counts·보고서 --final 의 일지 숫자가 같은지 보고, (보고서 숫자, status 글자) 를 돌려준다."""
    d = R.collect(mk, final=True, root=root, online=False)
    ops = d["ops"]
    w = h1.window_counts(mk, root)
    for k in ("l_errors", "l_false_positive", "l_runs_only", "data_stops", "data_kinds", "gate_refused",
              "backlog_fail", "batch_max", "lock_timeouts", "no_end", "outside"):
        assert w[k] == ops[k], (k, w[k], ops[k])
    assert w["late"] == ops["late"] and w["window_bars"] == d["window_bars"]
    if d["complete"]:                                            # 연장 구간 L: 연장 봉이 없어도 보고서에 보임(T-5)
        assert w["ext_l_errors"] == d["ext_l_errors"]
        if d.get("extension"):
            assert d["extension"]["l_errors"] == d["ext_l_errors"]
        if d["ext_l_errors"]:
            ext = R.render(d).split("## 연장 기록")[1]
            k = d["ext_l_errors"]
            assert f"L 오류(errors.jsonl) {k}" in ext or f"L 오류(errors.jsonl·종료 코드 2) {k}건" in ext, ext[:300]
    text = status_text(mk, root)
    wb = d["window_bars"]                                        # status 머리의 창 크기도 meta.rules(T-10)
    head = text.splitlines()[0]
    assert f"판정 창 {min(ops['n_bars'], wb)}/{wb}" in head, head
    line = next(x for x in text.splitlines() if x.startswith("  L 오류 "))
    assert line.startswith(f"  L 오류 {ops['l_errors']}"), line
    assert f"자료 멈춤 {ops['data_stops']}" in line and f"관문 거절 {ops['gate_refused']}" in line
    assert f"늦은 봉 {len(ops['late'])}/{h1.MAX_LATE_TOTAL}" in line and f"최대 {ops['batch_max']}봉" in line
    if ops["l_false_positive"]:
        assert f"④ 거짓 양성으로 뺀 {ops['l_false_positive']}건 따로" in line
    else:
        assert "거짓 양성" not in line
    summary = next(x for x in text.splitlines() if x.startswith("  점검 L "))
    assert summary.startswith(f"  점검 L {ops['l_errors']}"), summary
    lead = d["leader"]                                           # 팀장 수: 보고서 ⑧ 과 같은 분모(이 창이 쓴 판정 기록)
    assert f"팀장 LLM {lead['n'] - lead['fallback']} / 폴백 {lead['fallback']}" in summary, (summary, lead)
    assert (w["leader_n"], w["leader_fallback"]) == (None, None)  # decisions 없이 부르면 팀장 수는 안 셈
    assert f"늦은 봉 {len(ops['late'])} ·" in summary
    return ops, text


# ============================ S1~S4 status·요약 = 보고서 (설계 §10.2e) ============================

def test_S1_깨끗한_창은_모두_0_자기_시작_줄을_끝_기록_없는_실행으로_안_셈(tmp_path):
    h = tr.us_h(tmp_path, upto=3)
    ops, text = same_counts("us", h.root)
    assert ops["l_errors"] == 0 and ops["no_end"] == 0
    assert "끝 기록 없는 실행" not in text                      # status 자기 시작 줄(끝 줄 전)은 빼고 셈
    assert "끝 기록 없는 실행" not in status_text("us", h.root)  # 두 번째 status 도(첫 status 는 끝 줄이 있음)


@pytest.mark.parametrize("how", ["ok", "nowrite", "half"])
def test_S2_L_오류는_errors_jsonl_과_종료_코드_2_의_합집합_status_도_같음(tmp_path, how):
    h = TR._short_with_l_run(tmp_path, how)
    ops, text = same_counts("us", h.root)
    assert ops["l_errors"] == 1 and ops["l_runs_only"] == (0 if how == "ok" else 1)
    if how != "ok":
        assert "errors.jsonl 기록 없이 종료 코드 2 만 1건" in text


def test_S2_같은_실행의_errors_줄이_두_번이어도_한_번(tmp_path):
    h = TR._short_with_l_run(tmp_path, "ok")
    err = fs.read_lines(h.root / "errors.jsonl")[-1]
    TR.jline(h.root / "errors.jsonl", err)                       # 같은 run_id 의 줄이 하나 더(옛 status 는 2 로 셈)
    ops, _ = same_counts("us", h.root)
    assert ops["l_errors"] == 1


def test_S3_거짓_양성_판정은_status_와_요약에서도_빼고_따로(tmp_path, capsys):
    h, err, code, _, _ = TR._fp_scenario(tmp_path)
    assert code == 0
    out = capsys.readouterr().out
    assert "점검 L 0 (④ 거짓 양성 1건 뺌)" in out                   # 그 run 의 끝 요약도 같은 규칙
    ops, text = same_counts("us", h.root)
    assert ops["l_errors"] == 0 and ops["l_false_positive"] == 1
    assert "L 오류 0 (④ 거짓 양성으로 뺀 1건 따로)" in text


@pytest.mark.parametrize("which", ["가", "나"])
def test_S3_거짓_양성_조건이_틀리면_status_도_L_1(tmp_path, which):
    h, *_ = TR._fp_scenario(tmp_path, same_fps=(which != "가"), tamper=(which == "나"))
    ops, _ = same_counts("us", h.root)
    assert ops["l_errors"] == 1 and ops["l_false_positive"] == 0


@pytest.mark.parametrize("same_clock", [False, True])
def test_S4_실패한_start_뒤_같은_S_로_다시_시작한_창은_status_도_0(tmp_path, monkeypatch, same_clock):
    """같은 시각(시계가 거침)이어도 status 는 보고서처럼 '창을 만든 start 보다 먼저 시작한 실행'의 줄을 뺀다
    (옛 status 는 시각만 보고 1 로 셈)."""
    h = TR._fin_h(tmp_path, n_days=70)
    TR._pass_now(h.root)
    real = h1.run_bar
    monkeypatch.setattr(h1, "run_bar", lambda *a, **k: (_ for _ in ()).throw(KeyError("코드 버그(시험)")))
    assert h.start(gate=True) == 2
    monkeypatch.setattr(h1, "run_bar", real)
    clock = None if same_clock else fs.run_at("us", hs.S_A, hh=7, mm=40)
    assert h.start(gate=True, clock=clock) == 0
    for k in range(1, 3):
        assert h.run(h.D[k], gate=True) == 0
    ops, text = same_counts("us", h.root)
    assert ops["l_errors"] == 0 and ops["outside"] == 2
    assert "창 밖 기록 2줄" in text


def test_S4_status_창이_다_차면_S62_까지_그_뒤는_연장으로_따로(tmp_path):
    """meta.rules 의 판정 창을 5봉으로 줄인 장면(보고서·status 모두 meta.rules 를 씀): S+4 뒤의 L 은 연장 몫."""
    h = tr.us_h(tmp_path, upto=7)
    TR.recommit(h.root, "us", fn_meta=lambda m: m["rules"].update(window_bars=5))
    end_at = lambda bar: next(r["at"] for r in fs.read_lines(h.root / "runs.jsonl")    # noqa: E731
                              if r.get("event") == "end" and bar in (r.get("bars") or []))
    for i, bar in ((2, h.D[3]), (5, h.D[6]), (6, h.D[7])):
        TR.jline(h.root / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": end_at(h.D[i]), "date": bar,
                                           "run_id": f"가짜{i}", "problems": [{"level": "L", "code": "L7"}]})
    ops, text = same_counts("us", h.root)
    w = h1.window_counts("us", h.root)
    assert w["complete"] and w["s62"] == h.D[4]
    assert ops["l_errors"] == 1 and w["ext_l_errors"] == 2
    assert "연장 구간(S+62 뒤) L 오류 2건(판정에는 안 씀)" in text


def test_S4_자료_멈춤_관문_거절_늦은_봉_한_번에_따라잡은_봉도_같음(tmp_path):
    h = tr.us_h(tmp_path, upto=2)
    assert h.run(h.D[3], gate=True) == 3                         # 재현 통과 기록 없음 → 관문 거절
    h.src.drop = {"BBB": {h.D[3]}}
    assert h.run(h.D[3]) == 4                                    # D3
    h.src.drop = {}
    assert h.run(h.D[5]) == 0                                    # D3·D4 늦은 봉 + D5 (한 번에 3봉)
    ops, text = same_counts("us", h.root)
    assert (ops["gate_refused"], ops["data_stops"], ops["data_kinds"], ops["batch_max"]) == (1, 1, {"D3": 1}, 3)
    assert ops["late"] == [h.D[3], h.D[4]]
    assert "자료 멈춤 1 (D3 1)" in text


# ============================ G1 ②-3 env 만 다른 봉 ============================

def test_G1_하루_기록의_env_만_달라도_다른_지문으로_셈(tmp_path):
    h = TR._fin_h(tmp_path, n_days=70)
    TR._pass_now(h.root)
    assert h.start(gate=True) == 0
    for k in (1, 2, 3):
        assert h.run(h.D[k], gate=True) == 0
    _, v = TR._verdict(h.root)
    assert v["c3"]["ok"]

    def other_env(states):                                       # 같은 code_hash, env 만 다름(라이브러리가 바뀐 봉)
        for arm in h1.ARMS:
            for tn in h1.TRAINERS:
                row = states[arm][tn]["days"][2]
                row["env"] = {**row["env"], "pandas": "0.0.0-시험"}
    TR.recommit(h.root, "us", other_env)
    d, v = TR._verdict(h.root)
    assert d["ops"]["other_fp_rows"] == [h.D[2]] and d["ops"]["other_fp_runs"] == []
    assert not v["c3"]["ok"] and v["violated"]


# ============================ G2 종료 코드 1 ============================

def test_G2_파이썬이_cli_전에_죽으면_종료_코드_1(tmp_path):
    fake = tmp_path / "fake"
    (fake / "pandas").mkdir(parents=True)
    (fake / "pandas" / "__init__.py").write_text("raise ImportError('시험용: pandas 설치가 깨짐')\n", encoding="utf-8")
    old = os.environ.get("PYTHONPATH")                           # 덮어쓰지 않고 앞에 붙임(지킴이 sitecustomize 가 남게, T-4)
    env = {**os.environ, "PYTHONPATH": str(fake) + (os.pathsep + old if old else ""), "PYTHONDONTWRITEBYTECODE": "1"}
    work = tmp_path / "cwd"
    work.mkdir()
    repo_before = rg.snapshot(ROOT, hash_files=True)               # h1.py 가 쓰는 곳은 cwd 가 아니라 <저장소>/state/h1 (T-11)
    r = subprocess.run([sys.executable, str(ROOT / "h1.py"), "status", "--market", "us"], capture_output=True, text=True,
                       cwd=str(work), env=env, timeout=120)
    assert r.returncode == 1 and "ImportError" in r.stderr and "시험용: pandas 설치가 깨짐" in r.stderr
    assert r.returncode not in set(h1.EXIT_TEXT) - {1}
    assert list(work.iterdir()) == []                            # 아무 파일도 안 만듦(cwd)
    assert rg.changes(repo_before, rg.snapshot(ROOT, hash_files=True)) == []   # 저장소 state/(H1_DIR)·results/ 도 그대로


# ============================ G3 재시작해도 판정 기록 그대로 ============================

def test_G3_재시작해도_판정_기록은_그대로_같은_열쇠는_다시_씀(tmp_path):
    h = tr.us_h(tmp_path, upto=1)
    dl = h1.decisions_path(h.root, h.mk)
    before = dl.read_bytes()
    keys_s = {r["key"] for r in h1.DecisionLog(dl, read_only=True).records() if r["date"] == hs.S_A}
    assert keys_s
    runs_n, n_calls = len(h.runs()), len(h.ask.calls)
    tr._restart(h, "시험: 판정 기록이 남는지")
    assert dl.read_bytes() == before and len(h.runs()) >= runs_n    # 판정 기록·실행 일지는 시장 폴더 밖이라 그대로
    assert h.start() == 0                                        # 같은 시각 → 같은 S
    assert h.meta()["start_date"] == hs.S_A and h.meta()["restart_no"] == 1
    assert len(h.ask.calls) == n_calls                           # 같은 (날짜, 트레이너, 종목)은 기록을 다시 씀 → LLM 0번
    assert dl.read_bytes() == before
    used = h1.window_decision_keys(h.states(), hs.S_A, hs.S_A)
    assert used == keys_s


# ============================ G4 판정 기록 가운데 줄 깨짐 ============================

def test_G4_판정_기록_가운데_줄이_깨지면_L24_2_장부_그대로(tmp_path):
    h = tr.us_h(tmp_path, upto=2)
    dl = h1.decisions_path(h.root, h.mk)
    lines = dl.read_bytes().split(b"\n")
    assert len(lines) > 3
    lines[1] = lines[1][:-5]                                     # 가운데 줄(마지막이 아님)이 깨짐
    dl.write_bytes(b"\n".join(lines))
    snap = {k: v for k, v in h.snap().items() if k != "analyst_cache.jsonl"}
    assert h.run(h.D[3]) == 2
    assert {k: v for k, v in h.snap().items() if k != "analyst_cache.jsonl"} == snap
    err = h.errors()[-1]
    assert [p["code"] for p in err["problems"] if p["level"] == "L"] == ["L24"]
    text = status_text("us", h.root)
    assert "판정 기록을 읽지 못함: L24" in text and "L 오류 1" in text


# ============================ G5~G7 L 음성 대조 보강 ============================

@pytest.fixture(scope="module")
def scenes(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        a4 = hs.scenario_a(tmp_path_factory.mktemp("a4") / "log.jsonl", upto=4)

        def plan(D):
            return {"스프린터": {"buy": [(c, D[0]) for c in ("AAA", "BBB", "CCC", "DDD", "EEE", "GGG", "HHH")]}}
        full = hs.scenario(hs.world_a(), hs.S_A, plan, tmp_path_factory.mktemp("f") / "log.jsonl", upto=0,
                           leader_mode="replay")
    return {"a4": a4, "full": full}


def as_json(sc):
    st = {a: {t: h1.ledger_to_json(s, sc.world.market) for t, s in by.items()} for a, by in sc.states.items()}
    return json.loads(json.dumps(st, ensure_ascii=False))


def l_codes(sc, states, arm=None):
    log = sc.runner.log
    cal = sc.world.calendar(sc.runner.S, states["A0"][h1.TRAINERS[0]]["last_date"])
    probs = []
    for a in ([arm] if arm else h1.ARMS):
        probs += h1_check.check_ledger(sc.world.market, a, states[a], cal, log, sc.runner.allowed)
    if arm is None:
        probs += h1_check.check_pair(sc.world.market, states["A0"], states["A1"], log)
    return {p.code for p in h1_check.errors(probs)}, probs


def test_G5_L5_그날그날_보유와_매수_대기가_5를_넘으면(scenes):
    sc = scenes["a4"]
    s = as_json(sc)
    assert l_codes(sc, s)[0] == set()
    st = s["A0"]["파이오니어"]
    d, nxt = sc.D[1], sc.D[2]
    for i in range(6):                                           # 그날 생겨 다음 봉에 버려진 매수 주문 6개(끝 상태는 그대로)
        st["orders"].append({"id": f"{d}|Z{i}|매수", "signal_date": d, "code": f"Z{i}", "action": "매수",
                             "reason": "시험", "origin": "sell_signal", "created_on": d, "status": "dropped",
                             "done_date": nxt, "why": "이미 보유"})
    got, probs = l_codes(sc, s)
    assert got == {"L5"}, [(p.code, p.detail) for p in h1_check.errors(probs)]
    assert any("그날 보유 + 매수 대기 > MAX_POSITIONS" in p.detail and p.date == d for p in probs)


def test_G6_L10_A1_종가_현금이_1_이상이면_쓸어_담기_누락(scenes):
    sc = scenes["a4"]
    s = as_json(sc)
    t = sc.D[4]
    st = s["A1"]["마라토너"]
    sweep = [f for f in st["fills"] if f["date"] == t and f["purpose"] == "sweep"]
    assert len(sweep) == 1 and st["fills"][-1] is sweep[0]       # D4: AAA 매도 대금을 쓸어 담은 날(마지막 날)
    f = st["fills"].pop()
    row = st["days"][-1]
    row["cash"], row["idle_units"] = f["cash_before"], f["units_before"]
    row["idle_value"] = row["idle_units"] * row["idle_close"]
    row["value"] = row["cash"] + row["stock_value"] + row["idle_value"]
    st["wallet"]["cash"] = f["cash_before"]
    st["wallet"]["holdings"]["SPY"]["shares"] = f["units_before"]
    assert row["cash"] >= h1.SWEEP_MIN
    got, probs = l_codes(sc, s, "A1")
    assert got == {"L10"}, [(p.code, p.detail) for p in h1_check.errors(probs)]


def test_G7_L19_빈자리_부족_후보가_있는데_빈자리를_다_안_채움(scenes):
    sc = scenes["full"]
    s = as_json(sc)
    assert l_codes(sc, s)[0] == set()
    st = s["A0"]["스프린터"]
    row = st["days"][0]
    ordered = [e for e in row["leader"] if e["effect"] == "ordered"]
    assert len(ordered) == 5 and row["over_slots"] == 2
    last = ordered[-1]                                           # 마지막(가장 낮은 순위) 주문을 '빈자리 부족'으로 바꿈
    last["effect"] = "over_slots"
    row["over_slots"] = 3
    st["orders"] = [o for o in st["orders"] if o["code"] != last["code"]]
    st["pending"] = [o for o in st["pending"] if o["code"] != last["code"]]
    got, probs = l_codes(sc, s, "A0")
    assert got == {"L19"}, [(p.code, p.detail) for p in h1_check.errors(probs)]
    assert any("빈자리 부족 후보가 있는데" in p.detail for p in probs)


# ============================ G8 시각 경계(정각) ============================

@pytest.mark.parametrize("market", ["us", "kr"])
@pytest.mark.parametrize("delta,mode", [(timedelta(microseconds=-1), "llm"), (timedelta(0), "late")])
def test_G8_봉_시작이_next_open_정각이면_late(tmp_path, market, delta, mode):
    codes = ("005930", "000660") if market == "kr" else ("AAA", "BBB")
    w = hs.World(market, codes)
    S = "2026-02-04"
    now = h1.next_open(market, S) + delta
    ask = hs.FakeAsk()
    brains = hs.fake_brains({"마라토너": {"buy": [(codes[0], S)]}})
    r = hs.Runner(w, S, tmp_path / "log.jsonl", leader_mode="llm", ask=ask, clock=lambda: now, brains=brains)
    with hs.brains_patched(brains):
        res = r.step(S)
    assert res.mode == mode and res.late is (mode == "late")
    assert (len(ask.calls), r.log.records()[0]["status"]) == ((1, "ok") if mode == "llm" else (0, "late_no_llm"))


def test_G8_묻기_직전_시각이_next_open_정각이면_묻지_않음(tmp_path):
    date = "2026-02-02"
    edge = h1.next_open("us", date)
    clock = {"t": edge - timedelta(minutes=5)}
    ask = hs.FakeAsk()
    log = h1.DecisionLog(tmp_path / "log.jsonl")
    ld = h1.Leader("us", date, log, "llm", now=lambda: clock["t"], ask=ask, cli_version="9.9.9")
    c = [{"code": x, "price": 1.0, "rsi": None, "date": date, "reason": "신호"} for x in ("X", "Y")]
    ld("마라토너", c[:1])
    clock["t"] = edge                                            # 정각
    ld("스프린터", c)
    assert ask.calls == [("마라토너", ["X"])]
    assert [r["status"] for r in log.records()] == ["ok", "late_no_llm", "late_no_llm"] and ld.late_calls == 1


def test_G8_KS200_확정_시각_22시30분_정각(tmp_path):
    """main.confirmed_bars 는 22:30:00 정각에 그 봉을 확정으로 친다(< 가 아니면 확정) → D7 도 정각부터(≥)."""
    h = tr.kr_h(tmp_path, upto=3)
    t = h.D[4]
    h.src.idle_until = h.D[3]                                    # KS200 에 t 봉이 아직 없음, 종목에는 있음
    assert h.run(t, hh=22, mm=30) == 7 and h.last() == h.D[3]
    h.src.idle_until = None
    assert h.run(t, hh=22, mm=30) == 0 and h.last() == t          # 정각에 KS200 t 봉도 확정 → 처리


@pytest.mark.parametrize("delta,code", [(timedelta(seconds=-1), 0), (timedelta(0), 8)])
def test_G8_start_는_next_open_S_정각부터_거절(tmp_path, delta, code):
    h = tr.us_h(tmp_path)
    clock = h1.next_open("us", h.D[0]) + delta                   # 확정 봉 = D0(S) — 그 다음 장 시작 정각
    assert h.start(clock=clock) == code
    if code:
        assert "늦은 봉" in h.ends()[-1]["message"] and not h.mdir.exists()
    else:
        assert h.meta()["start_date"] == h.D[0]


# ============================ G9 T-DELIST 국내 (매도세·dropped·기록) ============================

def test_G9_국내_상장폐지_정리_비용은_그_봉_날짜_매도세(tmp_path):
    """등록 마지막 거래일 2025-12-30(세율 0.15%)과 정리 봉 2026-01-02(0.20%)가 세율 구간이 다른 장면 — 정리 비용은
    **정리 봉 날짜** 세율(T-8: 같은 구간 두 날짜로는 어느 날짜 세율인지 가를 수 없었음). KRX 휴장 12-25·12-31·01-01 은 뺀 달력."""
    w = fs.drop_days(tr.kr_world(start="2025-06-02", end="2026-03-31"), ["2025-12-25", "2025-12-31", "2026-01-01"])
    S = "2025-12-24"

    def plan(D):
        return {"마라토너": {"buy": [("005930", D[0]), ("000660", D[0])], "sell": [("000660", D[3])]},
                "스프린터": {"buy": [("005380", D[0])]}}
    h = tr.kr_h(tmp_path, world=w, S=S, plan=plan, upto=3)       # D3(12-30) 끝: 000660 매도 대기 주문
    D = h.D
    assert (D[3], D[4]) == ("2025-12-30", "2026-01-02")
    assert h1.kr_sell_tax(D[3]) == 0.0015 and h1.kr_sell_tax(D[4]) == 0.0020
    st0 = h.states()
    assert any(o["code"] == "000660" and o["action"] == "매도" for o in st0["A0"]["마라토너"]["pending"])
    t = D[4]
    P = 123456.0
    h.src.missing = {"000660"}
    assert h.run(t) == 4                                         # D2
    assert h.corp("000660", delist=True, last_date=D[3], last_close=P) == 0
    assert h.run(t) == 0 and h.last() == t
    st = h.states()
    m = markets.MARKETS["kr"]
    for arm in h1.ARMS:
        x = st[arm]["마라토너"]
        f = [y for y in x["fills"] if y["purpose"] == "delist"]
        q = st0[arm]["마라토너"]["positions"]["000660"]["shares"]
        E = P * (1 - m.slippage)
        tax = h1.kr_sell_tax(t)                                  # 정리 봉 날짜(2026-01-02) 세율 0.20%
        assert len(f) == 1 and f[0]["date"] == t and f[0]["qty"] == q and f[0]["tax"] == E * q * tax
        assert f[0]["tax"] != E * q * h1.kr_sell_tax(D[3])        # 등록 마지막 거래일 세율(0.15%)이 아님
        assert f[0]["cash_delta"] == E * q - E * q * m.fee_rate - E * q * tax
        o = next(o for o in x["orders"] if o["code"] == "000660" and o["action"] == "매도")
        assert (o["status"], o["why"], o["done_date"]) == ("dropped", "delist", t)
    assert h1_check.errors(h.recheck(tr.allowed_now())) == []
    ca = fs.read_lines(h.mdir / "corp_actions.jsonl")[-1]
    ch = fs.read_lines(h.root / "changes.jsonl")[-1]
    assert ca["kind"] == "delist" and ca["code"] == "000660" and ca["last_close"] == P and ca["source"]
    assert ch["kind"] == "corp-action:delist" and ch.get("at")


# ============================ G10 W 등급 거짓 양성 ============================

def test_G10_정상_장면에서는_W_가_하나도_없음(tmp_path):
    h = tr.us_h(tmp_path, upto=4)
    for r in h.ends():
        assert r["exit_code"] == 0
        assert [p for p in r["problems"] if p["level"] in ("W", "D")] == [], r["problems"]
        assert r.get("d7_checked") is True and r.get("late_bars") == []


# ============================ G11 ⑩ 고정 값 ============================

DESIGN_RULES = {   # 설계 §2.2 ⑩ 의 숫자(사전 등록) — 코드 상수가 바뀌면 여기와 설계를 같이 고쳐야 한다
    "total": {"us": 100_000, "kr": 100_000_000},
    "ratios": {"마라토너": 0.6, "스프린터": 0.3, "파이오니어": 0.1},
    "caps": {"마라토너": 0.30, "스프린터": 0.20, "파이오니어": 0.15},
    "max_positions": 5, "conv_min": 0.5, "idle_sell_tax": 0.0, "ledger_breaker": "off",
    "shadow_breaker": [0.10, 0.07], "sweep_min": 1.0, "short_margin": 1e-9, "sweep_shrink": [1e-12, 1e-9, 1e-6],
    "idle_code": {"us": "SPY", "kr": "KS200"}, "n_universe": 40, "max_late_batch": 5, "max_late_total": 10,
    "window_bars": 63, "max_restarts": 2, "deadline": "2027-06-30", "fallback_flag": 0.20, "retro_tol": 1e-6,
    "retro_days": 5, "cal_probe": {"us": ["AAPL", "MSFT"], "kr": ["005930", "000660"]}, "cal_hole_ratio": 0.5,
    "next_open": {"us": ["09:30", "America/New_York"], "kr": ["09:00", "Asia/Seoul"]},
    "eps_cash": 1e-6, "eps_rel": 1e-9, "fingerprint_version": 1,
}


@pytest.mark.parametrize("mk", ["us", "kr"])
def test_G11_규칙_상수는_설계_숫자와_같다(mk):
    r = h1.rule_constants(mk)
    for k, want in DESIGN_RULES.items():
        if isinstance(want, dict) and mk in want:
            want = want[mk]
        assert r[k] == want, (k, r[k], want)
    m = markets.MARKETS[mk]
    assert (r["fee_rate"], r["slippage"]) == (m.fee_rate, m.slippage)
    if mk == "kr":
        assert r["stock_sell_tax"] == [list(x) for x in h1.KR_SELL_TAX] and r["stock_sell_tax"][-1] == ["2026-01-01", 0.002]
    else:
        assert r["stock_sell_tax"] == [["0000-01-01", 0.0]]
    assert set(r) == set(DESIGN_RULES) | {"market", "fee_rate", "slippage", "stock_sell_tax"}


def test_G11_start_는_meta_rules_에_그대로_적고_어느_칸이_달라도_3(tmp_path):
    h = tr.us_h(tmp_path, upto=1)
    meta = h.meta()
    assert meta["rules"] == json.loads(json.dumps(h1.rule_constants("us")))
    for k in meta["rules"]:
        bad = copy.deepcopy(meta)
        v = bad["rules"][k]
        bad["rules"][k] = (v + "x") if isinstance(v, str) else ([v, 0] if isinstance(v, list) else
                                                                ({**v, "x": 1} if isinstance(v, dict) else v * 2 + 1))
        with pytest.raises(h1.H1Refused) as e:
            h1._check_rules(bad, "us", h.root)
        assert e.value.code == 3 and k in str(e.value)
    h1._check_rules(meta, "us", h.root)                          # 그대로면 통과


# ============================ G12 시장별 판정 ============================

def test_G12_다른_시장의_L_과_멈춤은_이_시장_숫자에_안_섞임(tmp_path):
    h = tr.us_h(tmp_path, upto=3)
    at = h.ends()[-1]["at"]
    TR.jline(h.root / "errors.jsonl", {"market": "kr", "start_date": hs.S_A, "at": at, "date": h.D[3], "run_id": "kr실행",
                                       "problems": [{"level": "L", "code": "L7"}]})
    TR.jline(h.root / "runs.jsonl", {"event": "end", "run_id": "kr실행", "command": "run", "market": "kr",
                                     "start_date": hs.S_A, "at": at, "exit_code": 2, "bars": []})
    TR.jline(h.root / "runs.jsonl", {"event": "end", "run_id": "kr멈춤", "command": "run", "market": "kr",
                                     "start_date": "unknown", "at": at, "exit_code": 4, "bars": [],
                                     "problems": [{"level": "D", "code": "D1"}]})
    ops, _ = same_counts("us", h.root)
    assert ops["l_errors"] == 0 and ops["data_stops"] == 0


# ============================ G13 ⑦ 정정 확정 기록 ============================

def test_G13_정정_확정도_corp_actions_jsonl_과_changes_jsonl_에_남음(tmp_path):
    h = tr.us_h(tmp_path, upto=4)
    bump = h.D[3]
    old = float(h.w.raw["BBB"].loc[pd.Timestamp(bump), "Close"])

    def f(df, now):
        df.loc[pd.Timestamp(bump), "Close"] = old * 1.002
        return df
    h.src.transform["BBB"] = f
    assert h.run(h.D[5]) == 4
    h.src.at(h.D[5])
    assert h.corp("BBB", accept_correction=True, source_data=h.src, source="https://example.com/정정") == 0
    ca = fs.read_lines(h.mdir / "corp_actions.jsonl")[-1]
    ch = fs.read_lines(h.root / "changes.jsonl")[-1]
    assert ca["kind"] == "correction" and ca["code"] == "BBB" and ca["source"] == "https://example.com/정정"
    assert {"date": bump, "field": "close", "old": old, "new": old * 1.002} in ca["items"]
    assert ch["kind"] == "corp-action:correction" and ch.get("at")
    assert h.states()["A0"]["마라토너"]["corp_actions"][-1]["items"] == ca["items"]


# ============================ 단계 3 독립 검토(docs/h1-review-3.md T-1 ~ T-14) 반영 ============================

def test_T1_백업이_있어도_HEAD_와_안_맞으면_되살리지_않고_L24(tmp_path, monkeypatch):
    """커밋 도중 꺼져 장부가 HEAD 와 다르고, backup/<HEAD.run_id>/ 도 (한 글자) HEAD 와 다르면 되살리지 말고 L24·종료 코드 2.
    load_market 의 '백업도 HEAD 와 맞는지' 확인을 지우면 맞지 않는 백업으로 조용히 되살린다(검토 돌연변이 H-HEADrestore)."""
    h = tr.us_h(tmp_path, upto=3)
    head0 = h.head()
    with monkeypatch.context() as mp:
        tr._crash_on(mp, lambda dst, seen: tr._is_ledger(dst) and sum(map(tr._is_ledger, seen)) == 3)
        with pytest.raises(tr.Crash):
            h.run(h.D[4])
    b = h.mdir / "backup" / head0["run_id"] / "A1" / "team_스프린터.json"
    good = b.read_bytes()
    b.write_bytes(good.replace(b'"days"', b'"days" ', 1))         # 백업이 HEAD 와 한 글자 다름
    before = fs.tree_sha(h.mdir)
    assert h.run(h.D[4]) == 2
    last = h.errors()[-1]["problems"][-1]
    assert last["code"] == "L24" and f"backup/{head0['run_id']}/ 도 HEAD 와 맞지 않음" in last["detail"]
    assert fs.tree_sha(h.mdir) == before                         # 장부·백업 그대로(맞지 않는 백업으로 덮지 않음)
    assert "restored_from_backup" not in h.ends()[-1]
    b.write_bytes(good)                                          # 대조: 백업이 HEAD 와 맞으면 되살려 이어감
    assert h.run(h.D[4]) == 0 and h.ends()[-1]["restored_from_backup"] == head0["run_id"]


def test_T2_산_날_장_마감_뒤_분할_적용_경계는_L_없음(tmp_path):
    """마라토너가 D4 시가에 BBB 를 산 날 장 마감 뒤 2:1 분할을 적용(효력 D5, applied_after = D4 = 매수일).
    L15 의 분할 반영 매수가(applied_after ≥ 매수일)와 L3 의 '분할 전 체결은 새 시세와 안 견줌'(같은 경계)이 둘 다 지켜져야
    거짓 L(→ 재시작)이 안 난다(검토 돌연변이 K-L15split)."""
    def plan(D):
        return {"마라토너": {"buy": [("BBB", D[3])]}}
    h = tr.H(tmp_path, tr.us_world(), hs.S_A, plan, hs.FakeAsk(hs.ASK_A))
    assert h.start() == 0
    h.run_to(4)
    pos0 = h.states()["A0"]["마라토너"]["positions"]["BBB"]
    assert pos0["buy_date"] == h.D[4]
    h.src.transform["BBB"] = fs.split_after(h.D[5], 2, tr.ET)
    assert h.run(h.D[5]) == 4
    assert h.corp("BBB", split=2, date=h.D[5]) == 0
    st = h.states()
    sp = st["A0"]["마라토너"]["corp_actions"][-1]
    assert sp["kind"] == "split" and sp["applied_after"] == pos0["buy_date"]           # 같은 날 경계
    assert st["A0"]["마라토너"]["positions"]["BBB"]["buy_price"] == pos0["buy_price"] / 2
    assert h.run(h.D[5]) == 0 and h.run(h.D[6]) == 0
    assert h1_check.errors(h.recheck(tr.allowed_now())) == []
    now = h.src.clock                                            # 분할로 소급 수정된 지금 시세를 frames 로 주고 다시 점검(L3·L6)
    frames = {c: f.df for c in tr.US_CODES if (f := h.src.fetch(c, now)) is not None}
    cal = h1._last_ok_calendar_line(h.root, "us")["dates"]
    dec = h1.DecisionLog(h1.decisions_path(h.root, h.mk), read_only=True)
    st = h.states()
    for arm in h1.ARMS:
        probs = h1_check.check_ledger("us", arm, st[arm], cal, dec, tr.allowed_now(), frames=frames)
        assert h1_check.errors(probs) == [], [(p.code, p.detail) for p in h1_check.errors(probs)]


def test_T3_저장소_도우미는_이미_있던_state_안의_변화를_잡음(tmp_path):
    root = tmp_path / "repo"
    (root / "state" / "h1" / "us").mkdir(parents=True)
    f = root / "state" / "h1" / "us" / "HEAD.json"
    f.write_text('{"last_date": "2026-11-04"}', encoding="utf-8")
    (root / "state" / "team_마라토너.json").write_text("{}", encoding="utf-8")
    base = rg.snapshot(root, hash_files=True)
    assert base["results"] is None and "state/h1/us/HEAD.json" in base
    assert rg.changes(base, rg.snapshot(root, hash_files=True)) == []
    st = f.stat()
    f.write_text('{"last_date": "2026-11-05"}', encoding="utf-8")   # 같은 크기, 수정 시각만 되돌림
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert rg.changes(base, rg.snapshot(root, hash_files=True)) == ["state/h1/us/HEAD.json: " + str(base[
        "state/h1/us/HEAD.json"]) + " → " + str(rg.snapshot(root, hash_files=True)["state/h1/us/HEAD.json"])]
    quick = rg.snapshot(root)                                    # 해시 없이는 이런 바꿈은 못 봄(시험마다 쓰는 가벼운 비교의 한계)
    (root / "state" / "h1" / "runs.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "results").mkdir()
    got = rg.changes(quick, rg.snapshot(root))
    assert got == ["results: None → ('dir',)", "state/h1/runs.jsonl: 없음 → " + str(rg.snapshot(root)["state/h1/runs.jsonl"])]


def _fake_repo(tmp_path, test_src):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy(ROOT / "tools" / "h1_test_guard.py", repo / "tools" / "h1_test_guard.py")
    (repo / "state" / "h1" / "us").mkdir(parents=True)               # 맥처럼 진짜 장부가 이미 있는 저장소
    (repo / "state" / "h1" / "us" / "HEAD.json").write_text('{"last_date": "2026-11-04"}', encoding="utf-8")
    (repo / "state" / "h1" / "runs.jsonl").write_text('{"event": "start"}\n', encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text(test_src, encoding="utf-8")
    return repo


TOUCH = '''from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_x():
    p = ROOT / "state" / "h1" / "runs.jsonl"
    p.write_text(p.read_text() + "{}\\n")
'''


@pytest.mark.parametrize("touch", [False, True])
def test_T3_지킴이는_맥처럼_state_h1_이_이미_있어도_그_안의_변화를_잡음(tmp_path, touch):
    repo = _fake_repo(tmp_path, TOUCH if touch else "def test_x():\n    assert True\n")
    before = rg.snapshot(repo, hash_files=True)
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    r = subprocess.run([sys.executable, str(repo / "tools" / "h1_test_guard.py"), "--quick", "-j", "3", "--",
                        "tests/test_x.py"], cwd=str(repo), env=env, capture_output=True, text=True, timeout=600)
    if touch:
        assert r.returncode == 1 and "state/h1/runs.jsonl" in r.stdout and "state/·results/ 그대로: False" in r.stdout
    else:
        assert r.returncode == 0 and "모두 통과" in r.stdout, r.stdout + r.stderr
        assert rg.changes(before, rg.snapshot(repo, hash_files=True)) == []
    assert not list(tmp_path.glob("h1-test-guard-*"))           # 임시 폴더는 지움


def test_T5_S62_다음_봉에서_난_L_은_연장_봉이_없어도_보고서에_보임(tmp_path):
    """창이 다 찼고(S+62 저장) 연장 봉은 아직 하나도 못 저장 → S+63 처리 중 L(종료 코드 2). status 의 '연장 구간 L' 과
    보고서 --final 의 연장 절이 같은 수를 보이고, 판정에는 안 쓴다."""
    h = tr.us_h(tmp_path, upto=4)
    TR.recommit(h.root, "us", fn_meta=lambda m: m["rules"].update(window_bars=5))
    at = next(r["at"] for r in fs.read_lines(h.root / "runs.jsonl") if r.get("event") == "end"
              and h.D[4] in (r.get("bars") or []))
    TR.jline(h.root / "errors.jsonl", {"market": "us", "start_date": hs.S_A, "at": at, "date": h.D[5],
                                       "run_id": "S63버그", "problems": [{"level": "L", "code": "L7"}]})
    TR.jline(h.root / "runs.jsonl", {"event": "end", "run_id": "S63버그", "command": "run", "market": "us",
                                     "start_date": hs.S_A, "at": at, "exit_code": 2, "bars": []})
    ops, text = same_counts("us", h.root)
    d = R.collect("us", final=True, root=h.root, online=False)
    assert d["complete"] and d["last"] == d["s62"] and d["extension"] is None and d["ext_l_errors"] == 1
    assert ops["l_errors"] == 0 and d["verdict"]["c1"]["ok"]                 # 판정에는 안 씀
    assert "그 뒤 봉을 처리하다 난 L 오류(errors.jsonl·종료 코드 2) 1건" in R.render(d)
    assert "연장 구간(S+62 뒤) L 오류 1건" in text


def test_T6_D7_로_끝난_실행의_끝_요약도_status_와_같은_숫자(tmp_path, capsys):
    h = tr.us_h(tmp_path, upto=3)
    h.src.idle_until = h.D[4]                                    # D4 처리 + D5 는 SPY 늦음(D7)
    capsys.readouterr()
    assert h.run(h.D[5]) == 7
    run_summary = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("  점검 L "))
    text = status_text("us", h.root)
    st_summary = next(x for x in text.splitlines() if x.startswith("  점검 L "))
    assert "자료 멈춤 1" in run_summary and run_summary == st_summary
    assert "자료 멈춤 1 (D7 1)" in text


def test_T7_status_늦은_봉과_팀장_수는_S62_에서_끊김(tmp_path):
    """meta.rules 의 판정 창을 3봉으로(S+2 = D2) 줄이고, 연장 구간 D3~D7 을 모두 늦은 봉으로 다시 커밋한 장면.
    연장 구간에는 팀장 판정 기록도 있다(D4 GGG). status·요약의 늦은 봉·팀장 수는 보고서처럼 S+62(D2)까지만."""
    h = tr.us_h(tmp_path, upto=7)

    def late_ext(states):
        for arm in h1.ARMS:
            for tn in h1.TRAINERS:
                for r in states[arm][tn]["days"]:
                    if r["date"] > h.D[2]:
                        r["late"] = True
    TR.recommit(h.root, "us", late_ext, lambda m: m["rules"].update(window_bars=3))
    st = h.states()
    assert h1.window_decision_keys(st, hs.S_A, h.D[7]) > h1.window_decision_keys(st, hs.S_A, h.D[2])
    assert sum(1 for r in st["A0"]["마라토너"]["days"] if r["late"]) == 5
    ops, text = same_counts("us", h.root)                        # 늦은 봉·팀장 LLM/폴백 수까지 보고서와 같음
    assert ops["late"] == [] and "늦은 봉 0/10" in text and "판정 창 3/3 (연장 5봉)" in text


@pytest.mark.parametrize("which", ["L11하한", "L4신호일", "L17짝판정"])
def test_T9_규칙마다_음성_대조(scenes, which):
    """검토 T-9: 다른 규칙과 겹쳐 결과가 같이 잡히던 세 규칙도 따로 음성 대조."""
    sc = scenes["a4"]
    s = as_json(sc)
    if which == "L11하한":                                       # 지수 자금 매도를 메운 금액보다 적게(수량만 줄임)
        f = next(f for f in s["A1"]["마라토너"]["fills"] if f["purpose"].startswith("fund:"))
        f["qty"] *= 0.999
        got, probs = l_codes(sc, s)
        assert any(p.code == "L11" and "메운 금액" in p.detail for p in probs), sorted(got)
    elif which == "L4신호일":                                    # 신호일 = 체결일(주문이 생긴 날은 그 전날 그대로)
        st = s["A0"]["스프린터"]
        f = next(f for f in st["fills"] if f["kind"] == "stock" and f["side"] == "buy")
        o = next(o for o in st["orders"] if o["id"] == f["order_id"])
        assert o["created_on"] < f["date"]
        o["signal_date"] = f["date"]
        o["id"] = f"{f['date']}|{o['code']}|{o['action']}"
        f["order_id"] = o["id"]
        got, probs = l_codes(sc, s)
        assert got == {"L4"} and any("신호일" in p.detail for p in probs), sorted(got)
    else:                                                        # A1 의 팀장 판정만 다름(같은 열쇠) — 판정 기록 없이 짝 점검만
        row = next(r for r in s["A1"]["마라토너"]["days"] if r["leader"])
        e = row["leader"][0]
        assert e["effect"] == "ordered"
        e["verdict"] = None if e["verdict"] is not None else "buy"   # 효과(ordered)와는 어긋나지 않는 값
        probs = h1_check.check_pair("us", s["A0"], s["A1"], None)
        assert [p.code for p in h1_check.errors(probs)] == ["L17"]
        assert h1_check.errors(h1_check.check_ledger("us", "A1", s["A1"], None, None)) == []   # 장부 하나 점검은 못 봄


def test_T14a_국내_23시05분_D7_뒤_다음날_07시40분_보조_실행은_그_봉을_제때_처리(tmp_path):
    h = tr.kr_h(tmp_path, upto=3)
    t = h.D[4]
    h.src.idle_until = h.D[3]                                    # 23:05 에 KS200 오늘 봉이 아직 없음
    assert h.run(t) == 7 and h.last() == h.D[3]
    h.src.idle_until = None
    nxt = pd.Timestamp(t) + pd.Timedelta(days=1)
    n = len(h.ask.calls)
    assert h.run(clock=datetime(nxt.year, nxt.month, nxt.day, 7, 40, tzinfo=KST)) == 0 and h.last() == t
    for arm in h1.ARMS:
        row = h.states()[arm]["마라토너"]["days"][-1]
        assert row["date"] == t and row["mode"] == "llm" and row["late"] is False
    assert h.ends()[-1]["late_bars"] == [] and len(h.ask.calls) >= n
    ops, text = same_counts("kr", h.root)
    assert ops["data_stops"] == 1 and ops["data_kinds"] == {"D7": 1} and ops["late"] == []


def test_T14b_늦은_봉과_D7_이_한_실행에(tmp_path):
    h = tr.us_h(tmp_path, upto=3)
    h.src.idle_until = h.D[4]                                    # D5 시각에 D4 처리(이미 늦음) + D5 는 SPY 늦음(D7)
    assert h.run(h.D[5]) == 7
    end = h.ends()[-1]
    assert end["bars"] == [h.D[4]] and end["late_bars"] == [h.D[4]]
    ops, text = same_counts("us", h.root)
    assert ops["late"] == [h.D[4]] and ops["data_kinds"] == {"D7": 1} and ops["batch_max"] == 1
    assert "자료 멈춤 1 (D7 1)" in text and "늦은 봉 1/10" in text


def test_T14c_재시작_뒤_새_창이_옛_창의_late_no_llm_기록을_다시_씀(tmp_path):
    """옛 창이 D1 을 늦게 처리해 late_no_llm 으로 남긴 판정 기록을, 재시작 뒤 새 창(S = D1, 제때)이 그대로 다시 쓴다
    (설계 §3.6 '재시작해도 지우지 않는다. 새 창의 같은 (날짜, 트레이너, 종목)은 이 기록을 다시 쓴다'). LLM 0번,
    그 기록은 새 창 ⑧ 폴백 비율에 들어간다."""
    h = tr.us_h(tmp_path)
    assert h.start() == 0
    assert h.run(clock=h1.next_open("us", h.D[1]) + timedelta(minutes=1)) == 0 and h.last() == h.D[1]
    dl = h1.decisions_path(h.root, h.mk)
    old = [r for r in h1.DecisionLog(dl, read_only=True).records() if r["date"] == h.D[1]]
    assert old and {r["status"] for r in old} == {"late_no_llm"}
    before, n_calls = dl.read_bytes(), len(h.ask.calls)
    tr._restart(h, "시험: 새 창이 옛 기록을 다시 쓰는지")
    assert h.start(clock=fs.run_at("us", h.D[1])) == 0              # 장 시작 전 → 새 S = D1, 제때(llm)
    assert h.meta()["start_date"] == h.D[1] and h.meta()["restart_no"] == 1
    assert len(h.ask.calls) == n_calls and dl.read_bytes() == before   # LLM 0번, 기록 그대로
    st = h.states()
    used = h1.window_decision_keys(st, h.D[1], h.D[1])
    assert used and used == {r["key"] for r in old}
    row = st["A0"]["마라토너"]["days"][0]
    assert row["mode"] == "llm" and row["late"] is False
    d = R.collect("us", final=True, root=h.root, online=False)
    assert d["leader"]["by_status"] == {"late_no_llm": len(used)} and d["leader"]["fallback"] == len(used)


def test_재시작_수는_status_restart_보고서가_같은_규칙(tmp_path):
    """재시작 수 = meta.restart_no·restarts.jsonl(done 또는 보관 폴더 있음)·보관 폴더 수 중 큰 값(보고서 R-7).
    status 머리·restart 상한 확인·보고서가 h1.restart_info 하나를 쓴다. restarts.jsonl 이 지워진 경우를 흉내 낸다."""
    h = tr.us_h(tmp_path, upto=1)
    TR.jline(h.root / "restarts.jsonl", {"status": "moving", "restart_id": "꺼진재시작", "market": "us",
                                         "at": "2026-02-04T08:00:00+09:00", "archive": "archive/us-20260204-080000"})
    info = h1.restart_info("us", h.root, h.meta())
    assert info["used"] == 0 and len(info["pending"]) == 1
    assert "끝나지 않은 restart 기록 1개" in status_text("us", h.root)
    (h.root / "restarts.jsonl").unlink()
    for n in ("us-20251101-000000", "us-20251201-000000"):        # 일지 줄 없이 보관 폴더만 2개
        (h.root / "archive" / n).mkdir(parents=True)
    info = h1.restart_info("us", h.root, h.meta())
    assert info["used"] == 2 and info["mismatch"] and info["sources"]["archive 폴더"] == 2
    text = status_text("us", h.root)
    assert "재시작 2/2 (남은 0)" in text and "재시작 수의 출처가 서로 다름" in text
    assert R.collect("us", final=True, root=h.root, online=False)["ops"]["restarts_used"] == 2
    with pytest.raises(h1.H1Refused) as e:                       # 옛 규칙(restarts.jsonl 만)이면 0 이라 받아 줬음
        tr._restart(h, "세 번째")
    assert e.value.code == 8 and h.mdir.is_dir()
