"""H1 단계 4 — 구현 전체 독립 검토(docs/h1-review-4.md) F-1~F-8 반영 시험. 인터넷·claude 없음.

검토자 장면 P1~P5 가 이제 거절·실패하는지, 그리고 허용되는 길(⑥-i·⑥-ii·④·정리 전 취소)은 그대로 되는지 본다.
- F-1·F-9  P1: 창 중간 코드 변경 — h1_data.py 고침(재현 지문·골든 같음)은 통과, 장부 지문이 다르거나 골든이 다르거나
           h1_data.py 밖(프롬프트·analyst.py)이면 관문 run 이 3, 관문 없이 남은 허용 밖 변경은 --final ⑥ 칸 실패.
           라이브러리 버전만 올림은 허용, 파이썬 버전은 3. 세율 줄 추가(⑥-ii)는 amend-rules 관문 길로 되고 세율 표 밖도
           바뀌면 3. status·보고서 머리에 ⑩·⑥ 줄과 보고서 코드 지문.
- F-2      P5: 사전 등록 파일은 첫 start 때 한 번(그 뒤 그대로), 코드 상수를 바꾸면 restart·start·run 이 3, 확인을
           건너뛴 코드로 만든 10봉 창도 보고서는 사전 등록 숫자(63)로 보고 ⑥·⑩ 칸에서 실패. amend-rules 는 '추가 기록'.
- F-3      P4: --delist 는 --confirm 과 '거래가 정말 없음' 증거가 있어야(아직 거래 중이면 9), 정리 전이면 --cancel-delist,
           정리 뒤·봉 처리 뒤면 취소 9, 취소된 등록은 엔진·L23 이 보지 않음.
- F-4      P3: restart 는 --confirm 시장 + 사유 코드(L·backlog·rule-change) + 일지 근거, 실행 전 확인 화면.
- F-5      P2: 같은 코드에서 사라진 L 은 ④ 로 기록하지 않음(L 그대로).
- F-7      시장별 잠금(한 시장이 잠겨도 다른 시장은 안 기다림)·시장별 판정 기록, 두 시장 프로세스 동시 실행 → 둘 다 0,
           일지 줄 온전, 결과는 차례로 돌린 것과 같음. 일지 한 줄 = os.write 한 번, 반쯤 쓴 마지막 줄은 따로 셈.
- F-8      팀장 호출은 빈 전용 폴더(state/h1/claude_cwd)에서, analyze_logged(cwd=…) 만 subprocess 에 cwd 를 넘김.
"""
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

import analyst                # noqa: E402
import h1                     # noqa: E402
import h1_check               # noqa: E402
import h1_fake_source as fs   # noqa: E402
import h1_report as R         # noqa: E402
import test_h1_report as TR   # noqa: E402  (장면 도우미 _fin_h 만 씀)
import test_h1_runner as tr   # noqa: E402  (H·us_h·kr_h·_restart·allowed_now)

REAL_ANALYZE_LOGGED = analyst.analyze_logged      # 가드가 바꿔 끼우기 전의 진짜 함수(F-8 시험에서 subprocess 를 가짜로)


class NoNet(BaseException):
    """인터넷에 나가려 하면 시험이 깨진다."""


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    """진짜 claude 금지 · 인터넷 금지 · 잠금에서 실제로 기다리지 않음 · 저장소 state/·results/ 를 건드리면 실패."""
    import h1_repo_guard as rg
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
    assert not moved, "시험이 저장소 state/·results/ 를 건드렸어요: " + "; ".join(moved[:5])


def _small(monkeypatch, tmp_path, bars=10, name="h1"):
    """판정 창을 bars 봉으로 사전 등록한 짧은 창(첫 start 전에 코드 상수를 바꿈 = 처음부터 그 숫자로 사전 등록)."""
    monkeypatch.setattr(h1, "WINDOW_BARS", bars)
    return TR._fin_h(tmp_path, name=name)


def _lines(p):
    return fs.read_lines(p)


# ============================ F-1·F-9: ⑥ 코드 동결 (P1) ============================

def test_P1_창_중간_h1_data_고침은_재현_지문과_골든이_같으면_통과(tmp_path, monkeypatch):
    h = _small(monkeypatch, tmp_path)
    fs.record_pass(h.root)                                           # 코드 A(지금)
    assert h.start(gate=True) == 0
    for k in range(1, 5):
        assert h.run(h.D[k], gate=True) == 0
    B = fs.code_variant("받기 고침")                                   # h1_data.py 만 고친 코드(재현 장부 지문·골든 같음)
    fs.record_pass(h.root, B)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "code_hash", lambda *a, **k: B)
        for k in range(5, 10):
            assert h.run(h.D[k], gate=True) == 0, k
        first = [e for e in h.ends() if h.D[5] in (e.get("bars") or [])][0]
        assert first["freeze_change"]["kinds"] == ["⑥-i 자료 받기 고침(h1_data.py)"]
        assert first["freeze_change"]["files"] == ["h1_data.py"]
        d = R.collect("us", final=True, root=h.root, online=False)
    v = d["verdict"]
    assert d["complete"] and d["window_bars"] == 10
    assert v["result"] == "pass" and v["c6"]["ok"], v
    assert [(t["date"], t["ok"], t["kinds"]) for t in d["freeze"]["transitions"]] == [
        (h.D[5], True, ["⑥-i 자료 받기 고침(h1_data.py)"])]
    assert d["report_code"]["same"]                                    # 보고서를 만든 코드 = 창 마지막 봉의 코드(B)


@pytest.mark.parametrize("case", ["장부지문다름", "골든다름", "프롬프트", "analyst"])
def test_P1_창_중간에_허용_밖으로_바꾸면_관문_run_이_3(tmp_path, monkeypatch, case):
    h = tr.us_h(tmp_path)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0
    for k in range(1, 4):
        assert h.run(h.D[k], gate=True) == 0
    code, kw, word = {
        "장부지문다름": (fs.code_variant("새 계산"), {"ledger": {"W1": "새 계산(다름)"}}, "(b)"),   # 검토자 P1
        "골든다름": (fs.code_variant("받기"), {"golden": "0" * 64}, "(c)"),
        "프롬프트": (fs.code_variant("말투", file="prompts/마라토너.md"), {}, "prompts/마라토너.md"),
        "analyst": (fs.code_variant("호출", file="analyst.py"), {}, "analyst.py"),
    }[case]
    fs.record_pass(h.root, code, **kw)                                 # 재현은 통과했어도
    snap = h.snap()
    with monkeypatch.context() as mp:
        mp.setattr(h1, "code_hash", lambda *a, **k: code)
        assert h.run(h.D[4], gate=True) == 3 and h.snap() == snap
        msg = h.ends()[-1]["message"]
        assert "⑥ 코드 동결" in msg and word in msg and "rule-change" in msg
        st = "\n".join(h1.status("us", h.root))
        assert "**⑥ 허용 안 됨** → 다음 run 은 종료 코드 3" in st
    assert h.run(h.D[4], gate=True) == 0                               # 코드를 되돌리면 그대로 이어 감


def _no_freeze_gate(mp):
    """run 관문의 ⑥ 확인을 건너뛴 코드(이번 고침 전 코드·손으로 우회)를 흉내 — 보고서가 두 번째 그물로 잡는지 보려고."""
    mp.setattr(h1, "_check_freeze_now", lambda *a, **k: None)


def test_P1_관문을_건너뛰어_남은_허용_밖_변경은_final_6_칸_실패(tmp_path, monkeypatch):
    """검토자 P1 의 판정: 창 중간(D5~)에 analyst.py 를 바꾼 코드로 처리한 봉이 하루 기록에 남으면(run 의 ⑥ 확인을 건너뜀)
    재현 통과 기록이 있어 ②-3 은 통과해도 ⑥ 칸이 실패 → fail_window (전에는 'pass')."""
    h = _small(monkeypatch, tmp_path)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0
    for k in range(1, 5):
        assert h.run(h.D[k], gate=True) == 0
    C = fs.code_variant("호출", file="analyst.py")
    fs.record_pass(h.root, C)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "code_hash", lambda *a, **k: C)
        _no_freeze_gate(mp)
        for k in range(5, 10):
            assert h.run(h.D[k], gate=True) == 0
    d = R.collect("us", final=True, root=h.root, online=False)
    v = d["verdict"]
    assert d["complete"] and v["c1"]["ok"] and v["c2"]["ok"] and v["c3"]["ok"]
    assert not v["c6"]["ok"] and v["result"] == "fail_window" and "analyst.py" in v["c6"]["detail"]
    rc = d["report_code"]
    assert not rc["same"] and rc["diff_files"] == ["analyst.py"]         # 보고서 코드(A) ≠ 창 마지막 봉 코드(C)
    text = R.render(d)
    assert "| ⑥ 코드 동결 · ⑩ 사전 등록 숫자 | **실패** |" in text and "**⑥·⑩ 위반**" in text
    assert "판정 창 마지막 봉(" in text and "**다름** (바뀐 파일 analyst.py)" in text
    st = "\n".join(h1.status("us", h.root))
    assert "**위반 1**" in st


def test_P1_끝나지_않은_창도_6_위반이면_바로_fail_window(tmp_path, monkeypatch):
    h = tr.us_h(tmp_path)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0
    C = fs.code_variant("호출", file="analyst.py")
    fs.record_pass(h.root, C)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "code_hash", lambda *a, **k: C)
        _no_freeze_gate(mp)
        assert h.run(h.D[1], gate=True) == 0
    v = R.collect("us", final=True, root=h.root, online=False)["verdict"]
    assert not v["complete"] and v["result"] == "fail_window" and "⑥ 코드 동결" in v["why"]
    assert "**판정 창 실패**" in R.build("us", final=True, root=h.root, online=False)


def test_F1_라이브러리_버전만_올림은_허용_파이썬은_3(tmp_path, monkeypatch):
    h = tr.us_h(tmp_path)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0 and h.run(h.D[1], gate=True) == 0
    env2 = {**h1.env_info(), "FinanceDataReader": "9.9.9"}
    fs.record_pass(h.root, None, env2)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "env_info", lambda: env2)
        assert h.run(h.D[2], gate=True) == 0
        assert h.ends()[-1]["freeze_change"]["kinds"] == ["⑥-i 라이브러리 버전"]
    env3 = {**env2, "python": "3.99.0"}
    fs.record_pass(h.root, None, env3)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "env_info", lambda: env3)
        assert h.run(h.D[3], gate=True) == 3 and "python" in h.ends()[-1]["message"]
    with monkeypatch.context() as mp:
        mp.setattr(h1, "env_info", lambda: env2)
        assert h.run(h.D[3], gate=True) == 0


def test_F1_세율_줄_추가는_amend_rules_관문_길로_세율_표_밖도_바뀌면_3(tmp_path, monkeypatch):
    h = tr.kr_h(tmp_path)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0 and h.run(h.D[1], gate=True) == 0
    base = tuple(h1.KR_SELL_TAX)
    added = base + (("2027-01-01", 0.0015),)
    BAD = fs.code_variant("세율 + 다른 곳", file="h1.py")
    fs.record_pass(h.root, BAD, tax_free="x" * 64)                     # 세율 표 밖도 바뀐 h1.py
    pre_blob = h1.prereg_path("kr", h.root).read_bytes()
    with monkeypatch.context() as mp:
        mp.setattr(h1, "KR_SELL_TAX", added)
        mp.setattr(h1, "code_hash", lambda *a, **k: BAD)
        assert h1.amend_rules("kr", "https://law.example/세율", h.root, gate=True) == 3
        assert "세율 표(KR_SELL_TAX) 밖에서도" in h.ends()[-1]["message"]
    assert h1.prereg_path("kr", h.root).read_bytes() == pre_blob and h.meta()["rules"]["stock_sell_tax"][-1][0] == "2026-01-01"
    TAX = fs.code_variant("세율 줄", file="h1.py")                      # 세율 표 값만 바뀐 h1.py(세율 표만 뺀 지문 같음)
    fs.record_pass(h.root, TAX)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "KR_SELL_TAX", added)
        mp.setattr(h1, "code_hash", lambda *a, **k: TAX)
        assert h.run(h.D[2], gate=True) == 3                          # amend 전: 규칙 다름
        assert h1.amend_rules("kr", "https://law.example/세율", h.root, gate=True) == 0
        assert h.run(h.D[2], gate=True) == 0                          # ⑥-ii
        assert h.ends()[-1]["freeze_change"]["kinds"] == ["⑥-ii 세율 줄 추가"]
        pre = json.loads(h1.prereg_path("kr", h.root).read_text(encoding="utf-8"))
        assert pre["rules"]["stock_sell_tax"] == [list(x) for x in base]           # 처음 값 그대로
        assert [a["added_rows"] for a in pre["amendments"]] == [[["2027-01-01", 0.0015]]]   # 추가 기록
        assert h1.prereg_rules(pre)["stock_sell_tax"] == [list(x) for x in added]
        d = R.collect("kr", root=h.root, online=False)
        assert d["freeze"]["ok"] and d["freeze"]["transitions"][0]["kinds"] == ["⑥-ii 세율 줄 추가"]


def test_F1_status_와_보고서_머리에_사전_등록과_코드_지문(tmp_path):
    h = tr.us_h(tmp_path, upto=2)
    st = "\n".join(h1.status("us", h.root))
    assert "⑩ 사전 등록(prereg_us.json" in st and "창 63봉" in st and "이 창 meta.rules 와 맞음" in st
    assert "⑥ 코드 동결: 창 안 코드·환경 지문 변경 0번 · 지금 코드·환경 = 마지막 봉과 같음" in st
    rep = R.build("us", final=True, root=h.root, online=False)
    assert f"이 보고서를 만든 코드: code_hash {h1.code_hash()[0][:12]}…" in rep
    assert "처리한 코드·환경과 같음" in rep and "⑩ 사전 등록(prereg_us.json" in rep


# ============================ F-2: 사전 등록 숫자 고정 (P5) ============================

def test_P5_사전_등록은_첫_start_때_한_번_코드_상수를_바꾸면_restart_start_run_이_3(tmp_path, monkeypatch):
    h = tr.us_h(tmp_path)
    assert h.start() == 0
    p = h1.prereg_path("us", h.root)
    pre = json.loads(p.read_text(encoding="utf-8"))
    assert pre["rules"] == json.loads(json.dumps(h1.rule_constants("us"))) and pre["amendments"] == []
    assert pre["design_doc_sha256"] == h1._design_sha() and pre["first_start_run_id"] and pre["written_at"]
    blob = p.read_bytes()
    tr._restart(h, "1")
    assert h.start() == 0
    tr._restart(h, "2")
    assert h.start() == 0
    assert p.read_bytes() == blob                                     # 재시작·새 start 가 다시 쓰지 않음
    with pytest.raises(h1.H1Refused) as e:
        tr._restart(h, "3")
    assert e.value.code == 8
    snap = h.snap()
    with monkeypatch.context() as mp:                                 # 검토자 P5: 상한 3·창 10 으로 코드를 바꿈
        mp.setattr(h1, "MAX_RESTARTS", 3)
        mp.setattr(h1, "WINDOW_BARS", 10)
        with pytest.raises(h1.H1Refused) as e:
            tr._restart(h, "3")
        assert e.value.code == 3 and "max_restarts" in str(e.value) and "window_bars" in str(e.value)
        assert h.run(h.D[1]) == 3
    assert h.mdir.is_dir() and h.snap() == snap and h1.restart_info("us", h.root, h.meta())["used"] == 2
    assert p.read_bytes() == blob


def test_P5_확인을_건너뛰어_만든_10봉_창도_보고서는_사전_등록_숫자로_실패(tmp_path, monkeypatch):
    h = TR._fin_h(tmp_path)
    assert h.start() == 0                                             # 사전 등록: 창 63·재시작 2
    tr._restart(h, "1")
    with monkeypatch.context() as mp:                                 # 확인을 건너뛴 코드 + 바꾼 상수로 새 창
        mp.setattr(h1, "MAX_RESTARTS", 3)
        mp.setattr(h1, "WINDOW_BARS", 10)
        mp.setattr(h1, "prereg_problems", lambda pre, rules: [])
        mp.setattr(h1, "_check_code_vs_prereg", lambda mk, root, what: h1.read_prereg(mk, root))
        mp.setattr(h1, "_rules_diff", lambda a, b: [])
        assert h.start() == 0
        for k in range(1, 10):
            assert h.run(h.D[k]) == 0
        assert h.meta()["rules"]["window_bars"] == 10
    d = R.collect("us", final=True, root=h.root, online=False)
    v = d["verdict"]
    assert d["window_bars"] == 63 and not d["complete"]                 # 판정 숫자는 사전 등록 파일에서
    assert v["result"] == "fail_window" and not v["c6"]["ok"]
    assert "window_bars" in v["c6"]["detail"] and "max_restarts" in v["c6"]["detail"]
    assert h.run(h.D[10]) == 3 and "사전 등록" in h.ends()[-1]["message"]


def test_F2_사전_등록_파일이_없으면_run_은_3_start_는_8(tmp_path):
    h = tr.us_h(tmp_path, upto=1)
    p = h1.prereg_path("us", h.root)
    blob = p.read_bytes()
    p.unlink()
    assert h.run(h.D[2]) == 3 and "사전 등록 파일" in h.ends()[-1]["message"]
    p.write_bytes(blob)
    tr._restart(h, "보관")
    p.unlink()
    assert h.start() == 8 and "prereg_us.json" in h.ends()[-1]["message"]


# ============================ F-3: 상장폐지 오타 방지 (P4) ============================

def _held(h):
    st = h.states()
    return sorted({c for arm in h1.ARMS for tn in h1.TRAINERS for c in st[arm][tn]["positions"]})


def test_P4_거래_중인_보유_종목_delist_는_9_시세가_없을_때만_받고_정리_전이면_취소(tmp_path):
    h = tr.us_h(tmp_path, upto=4)
    code = _held(h)[0]
    snap = h.snap()
    assert h.corp(code, delist=True, last_date=h.D[4]) == 9           # 검토자 P4 그대로: 그날 저녁, 마지막 처리 봉으로
    assert "거래일이 아직 없어요" in h.ends()[-1]["message"]          # (모든 종목의 마지막 봉이 그날이라 확인 불가)
    assert h.corp(code, delist=True, last_date=h.D[2], confirm=None) == 9
    assert "--confirm" in h.ends()[-1]["message"]
    assert h.corp(code, delist=True, last_date=h.D[2], confirm="AAB") == 9
    assert h.corp(code, delist=True, last_date=h.D[2]) == 9           # 검토자 P4: 시세는 D4 까지 정상
    assert "아직 거래 중" in h.ends()[-1]["message"] and h.snap() == snap
    h.src.missing.add(code)                                           # 정말 거래가 멈춤: 시세를 받을 수 없음(D2)
    assert h.corp(code, delist=True, last_date=h.D[2]) == 0
    ca = h.states()["A0"]["마라토너"]["corp_actions"][-1]
    assert ca["kind"] == "delist" and ca["registered_after"] == h.D[4] and "D2" in ca["evidence"]
    assert h.corp(code, cancel_delist=True, confirm=None) == 9
    assert h.corp(code, cancel_delist=True) == 0                     # 정리 전 → 취소
    assert h1.delist_registrations(h.states()) == {}
    kinds = [r["kind"] for r in _lines(h.mdir / "corp_actions.jsonl")]
    assert kinds == ["delist", "delist_cancel"]
    assert [r["kind"] for r in _lines(h.root / "changes.jsonl")] == ["corp-action:delist", "corp-action:delist_cancel"]
    h.src.missing.discard(code)
    assert h.run(h.D[5]) == 0
    st = h.states()
    assert not [f for arm in h1.ARMS for tn in h1.TRAINERS for f in st[arm][tn]["fills"] if f["purpose"] == "delist"]
    assert code in _held(h)                                           # 정리되지 않음
    assert h1_check.errors(h.recheck(tr.allowed_now())) == []         # L23 은 취소된 등록을 보지 않음
    ops = R.collect("us", root=h.root, online=False)["ops"]
    assert len(ops["corp"]["delist"]) == 1 and len(ops["corp"]["delist_cancel"]) == 1
    assert "(그중 취소 1건)" in R.build("us", root=h.root, online=False)
    # 다시 등록(마지막 거래일 = 마지막 처리 봉 D5, 다음 거래일 D6 에 그 종목만 행이 없음) → 다음 봉 정리 → 취소 불가
    h.at(h.D[6]).src.drop = {code: {h.D[6]}}
    assert h.corp(code, delist=True, last_date=h.D[5]) == 0
    ev = h.states()["A0"]["마라토너"]["corp_actions"][-1]["evidence"]
    assert f"시장은 그 뒤 1거래일({h.D[6]}~{h.D[6]}) 거래함" in ev and f"마지막 거래일 {h.D[5]}" in ev
    h.src.drop = {}
    h.src.missing.add(code)
    assert h.run(h.D[6]) == 0
    st = h.states()
    assert [f for arm in h1.ARMS for tn in h1.TRAINERS for f in st[arm][tn]["fills"] if f["purpose"] == "delist"]
    assert h.corp(code, cancel_delist=True) == 9 and "정리 체결" in h.ends()[-1]["message"]
    assert h1_check.errors(h.recheck(tr.allowed_now())) == []


def test_F3_보유하지_않은_종목도_봉을_처리한_뒤면_취소_9(tmp_path):
    h = tr.us_h(tmp_path, upto=3)
    code = next(c for c in ("JJJ", "III", "HHH", "FFF") if c not in _held(h))
    h.at(h.D[4]).src.missing.add(code)
    assert h.corp(code, delist=True, last_date=h.D[3], last_close=50.0) == 0
    assert h.run(h.D[4]) == 0
    assert h.corp(code, cancel_delist=True) == 9 and "이미 처리" in h.ends()[-1]["message"]
    assert h.corp("AAPL", cancel_delist=True) == 9                    # 등록 안 된 종목


def test_F3_국내_거래량_0_정지_행은_거래가_아님(tmp_path):
    """국내 원본에 마지막 거래일 뒤 거래량 0(거래정지) 행만 있으면 확정 시세에서 빠지므로 '거래 없음'으로 보고 받는다."""
    base = tr.kr_world()
    D = [base.at("2026-02-02", k) for k in range(8)]
    h = tr.kr_h(tmp_path, world=tr.kr_world(halts={"000660": [D[3], D[4]]}), upto=4)
    assert "000660" in _held(h)
    assert h.corp("000660", delist=True, last_date=D[1]) == 9          # D2 는 거래함 → 아직 거래 중
    assert h.corp("000660", delist=True, last_date=D[2]) == 0          # D3·D4 는 정지 행(거래량 0)뿐
    assert f"마지막 거래일 {D[2]}" in h.states()["A0"]["마라토너"]["corp_actions"][-1]["evidence"]


# ============================ F-4: restart 확인 (P3) ============================

def test_P3_restart_는_confirm_사유_코드_근거가_있어야(tmp_path, monkeypatch, capsys):
    h = tr.us_h(tmp_path, upto=4)
    snap = h.snap()
    for confirm, reason in ((None, "L"), ("kr", "L"), ("us", "실수")):           # 검토자 P3: h1.restart("us", "실수")
        with pytest.raises(h1.H1Refused) as e:
            h1.restart("us", reason, h.root, confirm=confirm)
        assert e.value.code == 9
    for reason in ("L", "backlog", "rule-change"):
        with pytest.raises(h1.H1Refused) as e:
            h1.restart("us", reason, h.root, confirm="us")
        assert e.value.code == 9 and "근거" in str(e.value)
    assert h.mdir.is_dir() and h.snap() == snap and h1.restart_info("us", h.root, h.meta())["used"] == 0
    assert not (h.root / "restarts.jsonl").exists()
    real = h1_check.check_day

    def flaky(mk, t, *a, **k):
        p = real(mk, t, *a, **k)
        return p + [h1_check.Problem("L", "L7", mk, "A0", "마라토너", t, "시험 L")] if t == h.D[5] else p
    with monkeypatch.context() as mp:
        mp.setattr(h1_check, "check_day", flaky)
        assert h.run(h.D[5]) == 2
    capsys.readouterr()
    dest = h1.restart("us", "L", h.root, confirm="us", note="D5 점검 L7 — 원인 확인 중")
    out = capsys.readouterr().out
    assert (f"재시작 전 확인: 창 S {h.S} · 마지막 처리 봉 {h.D[4]} · 처리한 봉 5/63 · 재시작 0/2 → 이번이 1번째"
            f"(뒤에 남는 재시작 1번) · 마감 2027-06-30") in out
    assert "사유 L(" in out and "L 오류 1건" in out and "설명: D5 점검 L7" in out
    rs = _lines(h.root / "restarts.jsonl")
    assert rs[0]["reason"] == "L" and rs[0]["note"].startswith("D5 점검") and rs[0]["bars"] == 5
    assert any("L 오류 1건" in x for x in rs[0]["evidence"]) and dest.is_dir()


def test_F4_backlog_근거는_종료_코드_6(tmp_path):
    h = tr.us_h(tmp_path, upto=1)
    with pytest.raises(h1.H1Refused):
        h1.restart("us", "backlog", h.root, confirm="us")
    assert h.run(h.D[8]) == 6                                         # 7봉 밀림 > 5
    with pytest.raises(h1.H1Refused):
        h1.restart("us", "L", h.root, confirm="us")                   # 사유 코드가 근거와 다름
    h1.restart("us", "backlog", h.root, confirm="us")
    assert "종료 코드 6" in _lines(h.root / "restarts.jsonl")[0]["evidence"][0]


def test_F4_rule_change_근거는_허용_밖_코드_또는_7_3_자료_멈춤(tmp_path, monkeypatch):
    h = tr.us_h(tmp_path)
    fs.record_pass(h.root)
    assert h.start(gate=True) == 0 and h.run(h.D[1], gate=True) == 0
    with pytest.raises(h1.H1Refused):
        h1.restart("us", "rule-change", h.root, confirm="us")
    C = fs.code_variant("호출", file="analyst.py")
    fs.record_pass(h.root, C)                                         # 허용 밖 코드가 재현을 통과함(커밋된 규칙 변경)
    h1.restart("us", "rule-change", h.root, confirm="us")
    ev = _lines(h.root / "restarts.jsonl")[0]["evidence"]
    assert any("⑥ 허용 밖" in x and "analyst.py" in x for x in ev)
    h2 = tr.us_h(tmp_path, upto=4, name="h2")                          # ⑦-3: 공식으로 못 잇는 기업 행위(D6 멈춤)
    h2.src.transform[_held(h2)[0]] = fs.split_after(h2.D[5], 3.3, tr.ET)
    assert h2.run(h2.D[5]) == 4
    h1.restart("us", "rule-change", h2.root, confirm="us")
    assert any("D6" in x for x in _lines(h2.root / "restarts.jsonl")[0]["evidence"])


# ============================ F-5: 같은 코드의 L (P2) ============================

def test_P2_같은_코드에서_사라진_L_은_거짓_양성으로_기록하지_않음(tmp_path, monkeypatch, capsys):
    h = TR._fin_h(tmp_path)
    TR._pass_now(h.root)
    assert h.start(gate=True) == 0
    for k in (1, 2):
        assert h.run(h.D[k], gate=True) == 0
    real = h1_check.check_day

    def once(mk, t, *a, **k):
        p = real(mk, t, *a, **k)
        return p + [h1_check.Problem("L", "L7", mk, "A0", "마라토너", t, "일시적 L(검토 장면)")] if t == h.D[3] else p
    with monkeypatch.context() as mp:
        mp.setattr(h1_check, "check_day", once)
        assert h.run(h.D[3], gate=True) == 2
    capsys.readouterr()
    assert h.run(h.D[3], gate=True) == 0                               # 같은 코드로 다시 → L 이 사라짐
    assert not [r for r in _lines(h.root / "changes.jsonl") if r.get("kind") == "false_positive"]
    assert "같은 코드에서 결과가 달라짐(비결정) → L 그대로" in capsys.readouterr().out
    ops = R.collect("us", final=True, root=h.root, online=False)["ops"]
    assert ops["l_errors"] == 1 and ops["l_false_positive"] == 0


# ============================ F-7: 시장별 잠금·판정 기록·일지 한 번 쓰기 ============================

def test_F7_한_시장이_잠겨도_다른_시장은_기다리지_않고_판정_기록은_시장별(tmp_path):
    us, kr = tr.us_h(tmp_path), tr.kr_h(tmp_path)
    assert us.root == kr.root
    assert us.start() == 0 and kr.start() == 0
    fd = os.open(us.root / "h1-us.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)                                    # 미국 명령이 오래 잡고 있는 상황
    try:
        assert kr.run(kr.D[1]) == 0                                    # 가드: 기다리려 하면 실패 → 안 기다림
        assert h1.status("kr", kr.root)
    finally:
        os.close(fd)
    assert us.run(us.D[1]) == 0
    root = us.root
    assert sorted(p.name for p in root.glob("*.lock")) == ["h1-kr.lock", "h1-us.lock"]
    assert not (root / "analyst_cache.jsonl").exists()
    for h in (us, kr):
        dl = h1.decisions_path(root, h.mk)
        assert dl.name == f"analyst_cache_{h.mk}.jsonl"
        recs = h1.DecisionLog(dl, read_only=True).records()
        assert recs and {r["market"] for r in recs} == {h.mk}
        assert h.head()["decision_log"]["lines"] == len(recs)


CHILD = r"""
import sys, time, socket, urllib.request
from pathlib import Path
root, market, go, tests, repo = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4], sys.argv[5]
sys.path.insert(0, repo)
sys.path.insert(0, tests)
def _no(*a, **k):
    raise RuntimeError("인터넷 금지(시험)")
socket.socket.connect = _no
urllib.request.urlopen = _no
import analyst, h1
import test_h1_runner as tr
def _boom(*a, **k):
    raise AssertionError("claude 금지(시험)")
analyst.analyze = analyst.analyze_logged = analyst.claude_cli_version = _boom
h1._lock_sleep = lambda s: time.sleep(0.01)
h = (tr.us_h if market == "us" else tr.kr_h)(root.parent, root=root)
deadline = time.time() + 60
while not go.exists() and time.time() < deadline:
    time.sleep(0.005)
codes = [h.run(h.D[k]) for k in range(1, 9)]
print("CODES", market, codes, flush=True)
sys.exit(0 if all(c == 0 for c in codes) else 1)
"""


def test_F7_두_시장_프로세스를_같이_돌려도_둘_다_0_일지_줄_온전_결과는_차례로와_같음(tmp_path):
    root = tmp_path / "h1"
    us, kr = tr.us_h(tmp_path), tr.kr_h(tmp_path)
    assert us.start() == 0 and kr.start() == 0
    go = tmp_path / "go"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    procs = [subprocess.Popen([sys.executable, "-B", "-c", CHILD, str(root), mk, str(go), str(TESTS), str(ROOT)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=str(tmp_path))
             for mk in ("us", "kr")]
    time.sleep(0.5)
    go.write_text("go")
    outs = [p.communicate(timeout=240) for p in procs]
    for p, (out, err) in zip(procs, outs):
        assert p.returncode == 0, (out[-2000:], err[-3000:])
    for name in ("runs.jsonl", "changes.jsonl"):
        p = root / name
        if p.exists():
            recs, bad, tail = R._read_counted(p, with_tail=True)
            assert bad == 0 and tail == 0 and p.read_bytes().endswith(b"\n")
    runs = _lines(root / "runs.jsonl")
    for mk in ("us", "kr"):
        ends = [r for r in runs if r.get("event") == "end" and r["market"] == mk and r["command"] == "run"]
        assert len(ends) == 8 and {r["exit_code"] for r in ends} == {0}
    tw_us, tw_kr = tr.us_h(tmp_path, name="twin"), tr.kr_h(tmp_path, name="twin")   # 차례로 돌린 쌍둥이
    assert tw_us.start() == 0 and tw_kr.start() == 0
    for k in range(1, 9):
        assert tw_us.run(tw_us.D[k]) == 0 and tw_kr.run(tw_kr.D[k]) == 0
    assert us.fp() == tw_us.fp() and kr.fp() == tw_kr.fp()


def test_F7_일지_한_줄은_os_write_한_번_반쯤_쓴_마지막_줄은_따로(tmp_path, monkeypatch):
    p = tmp_path / "x.jsonl"
    sizes = []
    real = os.write
    monkeypatch.setattr(h1.os, "write", lambda fd, b: (sizes.append(len(b)), real(fd, b))[1])
    h1._append_line(p, {"a": 1})
    h1._append_line(p, {"b": "가" * 3000})
    assert len(sizes) == 2 and p.read_bytes().count(b"\n") == 2
    with open(p, "ab") as f:
        f.write(b'{"half":')                                            # 다른 명령이 쓰는 중(또는 꺼짐)
    recs, bad, tail = R._read_counted(p, with_tail=True)
    assert len(recs) == 2 and bad == 0 and tail == 1                    # 마지막 줄은 깨진 줄이 아니라 '쓰는 중일 수 있음'
    assert h1.read_jsonl(p) == recs                                     # 읽는 쪽은 건너뜀(자르지 않음)
    h1._append_line(p, {"c": 3})                                       # 새 줄에서 시작
    assert len(sizes) == 3
    recs, bad, tail = R._read_counted(p, with_tail=True)
    assert [list(r)[0] for r in recs] == ["a", "b", "c"] and bad == 1 and tail == 0
    monkeypatch.setattr(h1.os, "write", lambda fd, b: real(fd, b[:3]))  # 한 번에 다 못 씀 → 환경 문제
    with pytest.raises(OSError):
        h1._append_line(p, {"d": 4})


# ============================ F-8: 팀장 작업 폴더 ============================

def test_F8_팀장은_빈_전용_폴더에서(tmp_path, monkeypatch):
    h = tr.us_h(tmp_path, upto=3)
    cwd = h.root / "claude_cwd"
    assert h.ask.calls and set(map(str, h.ask.cwds)) == {str(cwd)}
    assert cwd.is_dir() and not any(cwd.iterdir())
    calls = []
    monkeypatch.setattr(analyst.shutil, "which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(analyst.subprocess, "run",
                        lambda cmd, **kw: (calls.append(kw), SimpleNamespace(returncode=0, stdout='{"analysis": []}',
                                                                             stderr=""))[1])
    cands = [{"code": "AAA", "reason": "x", "rsi": 30, "price": 10}]
    assert REAL_ANALYZE_LOGGED("마라토너", cands, cwd=cwd)[1]["status"] == "ok"
    assert REAL_ANALYZE_LOGGED("마라토너", cands)[1]["status"] == "ok"
    assert calls[0]["cwd"] == str(cwd) and "cwd" not in calls[1]          # 안 주면 지금과 같은 호출
