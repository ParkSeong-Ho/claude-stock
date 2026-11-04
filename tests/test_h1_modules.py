"""H1 단계 2a — 작은 모듈 변경 시험 (설계 docs/h1-forward-design.md §3.4, §6). 인터넷·claude·키 없음.

확인하는 것 (설계 시험 ID)
- T-PW   paper_wallet.sell(tax_rate=None) 은 지금과 똑같고, tax_rate 를 주면 그 건만 그 세율(0.0 이면 세금 0)
- T-A1-7 (지갑 부분) 지수 소수 단위 매수·매도, 전 단위 매도 시 보유 삭제, JSON 저장 → 읽기 float.hex 같음,
         정수 주식은 int 로 돌아옴, Holding.shares 표기 float
- T-AN   analyst.analyze_logged: 프롬프트 == _build_prompt, 호출·환경 == analyze, 결과 == analyze 결과, meta 칸
- T-F5c  analyze_logged 상태별: claude 없음·시간 초과·OSError·0 아닌 종료·JSON 깨짐·analysis 키 없음·빈 후보
- T-F5d  normalize_verdict(" VETO"·"Hold" → 정리 값), 운영 analyst.apply 는 " VETO" 를 veto 로 보지 않는 지금 그대로
- T-SCR  screener.scan_frames: asof 로 자른 결과 == 미리 자른 시세 결과, brains·min_bars 인자, scan() 이 scan_frames 를 부름
- T-RSI  2024-06-01 부터 계산한 RSI 와 훨씬 앞에서부터 계산한 RSI 의 2026-06 이후 차 < 1e-9 (합성 시세)

claude CLI 는 절대 부르지 않는다: shutil.which·subprocess.run 을 가짜로 바꿔 끼운다(tests/test_analyst.py 와 같은 방식).
"""
import json
import subprocess
import sys
import typing
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import ta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyst    # noqa: E402
import main       # noqa: E402
import screener   # noqa: E402
import team       # noqa: E402
from paper_wallet import Holding, PaperWallet   # noqa: E402


def synth(seed=1, start="2024-06-03", end="2026-11-03", base=100.0):
    """결정적인 가짜 시세 (tests/test_flow.py 의 synth 와 같은 모양)."""
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = base * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(idx))))
    opn = close * (1 + rng.normal(0, 0.01, len(idx)))
    return pd.DataFrame({
        "Open": opn, "High": np.maximum(opn, close) * 1.01, "Low": np.minimum(opn, close) * 0.99,
        "Close": close, "Volume": rng.integers(1_000_000, 3_000_000, len(idx)).astype(float),
    }, index=idx)


# ======================= T-PW: paper_wallet.sell(tax_rate=…) =======================

def _filled(mk, price=71_234.5, n=37):
    w = main.make_wallet("시험", mk)
    w.deposit(10_000_000.0, "2026-11-02")
    assert w.buy("005930" if mk == "kr" else "AAPL", price, n, "2026-11-02")
    return w


def _net(w, price, shares, tax):
    """PaperWallet.sell 과 같은 계산 순서로 손계산한 매도 수령액."""
    exec_price = price * (1 - w.slippage)
    proceeds = exec_price * shares
    fee = proceeds * w.fee_rate
    return proceeds - fee - proceeds * tax


@pytest.mark.parametrize("mk", ["us", "kr"])
def test_T_PW_tax_rate_None_은_지금과_비트까지_같다(mk):
    code = "005930" if mk == "kr" else "AAPL"
    a, b, c = _filled(mk), _filled(mk), _filled(mk)
    before = a.cash
    assert a.sell(code, 72_001.25, 37, "2026-11-03")                    # 예전 호출 그대로
    assert b.sell(code, 72_001.25, 37, "2026-11-03", tax_rate=None)     # 기본값을 명시
    assert c.sell(code, 72_001.25, 37, "2026-11-03", None)              # 위치 인자로도
    assert a.cash == b.cash == c.cash == before + _net(a, 72_001.25, 37, a.sell_tax_rate)
    assert a.log[-1] == b.log[-1] == c.log[-1]
    assert a.holdings == b.holdings == {}


def test_T_PW_tax_rate_0_이면_세금_0_지갑_세율은_그대로():
    w = _filled("kr")
    before = w.cash
    assert w.sell("005930", 72_000.0, 37, "2026-11-03", tax_rate=0.0)
    assert w.cash == before + _net(w, 72_000.0, 37, 0.0)
    exec_price = 72_000.0 * (1 - w.slippage)
    assert w.cash == before + (exec_price * 37 - exec_price * 37 * w.fee_rate)   # 세금 칸이 정확히 0
    assert w.sell_tax_rate == 0.0020                                                # 지갑 값은 안 바뀜


def test_T_PW_tax_rate_를_주면_그_건만_그_세율():
    w, base = _filled("kr"), _filled("kr")
    before = w.cash
    assert w.sell("005930", 72_000.0, 20, "2026-11-03", tax_rate=0.0018)
    assert w.cash == before + _net(w, 72_000.0, 20, 0.0018)
    assert w.sell("005930", 72_000.0, 17, "2026-11-04")                 # 다음 건은 다시 지갑 세율
    assert base.sell("005930", 72_000.0, 20, "2026-11-03")
    assert base.sell("005930", 72_000.0, 17, "2026-11-04")
    assert w.cash > base.cash                                             # 0.18% < 0.20% 만큼 더 받음
    diff = 72_000.0 * (1 - w.slippage) * 20 * (0.0020 - 0.0018)
    assert w.cash - base.cash == pytest.approx(diff, rel=1e-9)


# ======================= T-A1-7: 소수 단위 (지갑 부분) =======================

def test_T_A1_7_Holding_표기는_float():
    assert typing.get_type_hints(Holding)["shares"] is float


def _index_units(cash, q, w):
    """설계 §2.3 e 의 쓸어 담기 식(줄임 1e-12): u = cash / (Q·(1+slip)·(1+fee)) · (1−1e-12)."""
    return cash / (q * (1 + w.slippage) * (1 + w.fee_rate)) * (1 - 1e-12)


def test_T_A1_7_소수_단위_매수_매도_전_단위_매도면_보유_삭제():
    w = PaperWallet(name="A1")
    w.deposit(100_000.0, "2026-11-05")
    q = 668.43
    u = _index_units(w.cash, q, w)
    assert u != int(u)                                    # 정말 소수 단위
    assert w.buy("SPY", q, u, "2026-11-06")
    h = w.holdings["SPY"]
    assert isinstance(h.shares, float) and h.shares == u  # 반올림 없이 그대로
    assert 0 <= w.cash < 1                                # 거의 전부 지수로
    part = u / 3
    assert w.sell("SPY", 670.0, part, "2026-11-07", tax_rate=0.0)
    assert w.holdings["SPY"].shares == u - part           # 남은 단위도 그대로
    rest = w.holdings["SPY"].shares
    assert not w.sell("SPY", 671.0, rest * (1 + 1e-12), "2026-11-08", tax_rate=0.0)   # 가진 것보다 많이는 못 팜
    assert w.sell("SPY", 671.0, rest, "2026-11-08", tax_rate=0.0)
    assert "SPY" not in w.holdings                        # 전 단위 매도 → 보유 삭제
    assert [e["종류"] for e in w.log] == ["입금", "매수", "매도", "매도"]


def test_T_A1_7_JSON_저장_읽기_float_hex_같고_정수_주식은_int(tmp_path):
    w = PaperWallet(name="A1")
    w.deposit(100_000.0, "2026-11-05")
    assert w.buy("AAPL", 271.26, 21, "2026-11-06")
    u = _index_units(w.cash, 755.737, w)
    assert w.buy("SPY", 755.737, u, "2026-11-06")
    assert w.sell("SPY", 756.0, u / 7, "2026-11-07", tax_rate=0.0)
    path = tmp_path / "wallet.json"
    main.save_json_atomic(path, {"wallet": asdict(w)})    # H1 도 쓸 원자적 저장(임시 파일 → 교체)
    back = team._wallet_from_dict(json.loads(path.read_text(encoding="utf-8"))["wallet"])
    assert back.cash.hex() == w.cash.hex()
    assert back.holdings["SPY"].shares.hex() == w.holdings["SPY"].shares.hex()
    assert back.holdings["SPY"].avg_price.hex() == w.holdings["SPY"].avg_price.hex()
    assert type(back.holdings["AAPL"].shares) is int and back.holdings["AAPL"].shares == 21
    # 읽어 온 지갑으로 계속 매매해도 원래 지갑과 비트까지 같은 결과
    rest = w.holdings["SPY"].shares
    assert w.sell("SPY", 760.0, rest, "2026-11-08", tax_rate=0.0)
    assert back.sell("SPY", 760.0, rest, "2026-11-08", tax_rate=0.0)
    assert back.cash.hex() == w.cash.hex() and "SPY" not in back.holdings


def test_T_A1_7_운영_저장_경로도_소수_단위를_그대로_돌려준다(tmp_path, monkeypatch):
    """team._save → team._load (운영 상태 파일 경로)도 소수 단위를 비트까지 보존한다."""
    monkeypatch.setattr(team, "STATE_DIR", tmp_path / "state")
    st = team._new_state("마라토너", 60_000.0, "2026-11-05")
    w = st["wallet"]
    u = _index_units(w.cash, 755.737, w)
    assert w.buy("SPY", 755.737, u, "2026-11-06")
    team._save("마라토너", st)
    back = team._load("마라토너")
    assert back["wallet"].holdings["SPY"].shares.hex() == u.hex()
    assert back["wallet"].cash.hex() == w.cash.hex()


# ======================= T-AN · T-F5c: analyst.analyze_logged =======================

CANDS = [{"code": "AAPL", "reason": "RSI 반등", "rsi": 28.0, "price": 190.0, "date": "2026-11-03"},
         {"code": "MSFT", "reason": "골든크로스", "rsi": 61.2, "price": 501.5, "date": "2026-11-03"}]
GOOD = ('분석: {"analysis": [{"code": "AAPL", "verdict": "buy", "conviction": 0.7, "note": "괜찮음"}, '
        '{"code": "MSFT", "verdict": " VETO", "conviction": "0.9"}, "잡음", {"verdict": "hold"}]} 끝')


def _done(stdout, returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


class FakeCLI:
    """claude 가 '설치돼 있다'고 속이고 subprocess.run 호출을 기록한다.
    reply: `claude -p` 의 결과(또는 던질 예외), version: `claude --version` 의 결과(또는 예외)."""

    def __init__(self, monkeypatch):
        self.calls, self.which_calls = [], []
        self.installed = True
        self.reply = _done(GOOD)
        self.version = _done("2.1.7 (Claude Code)\n둘째 줄\n")
        monkeypatch.setattr(analyst.shutil, "which", self._which)
        monkeypatch.setattr(analyst.subprocess, "run", self._run)

    def _which(self, name):
        self.which_calls.append(name)
        return "/usr/bin/claude" if self.installed else None

    def _run(self, cmd, **kw):
        self.calls.append((cmd, kw))
        res = self.version if cmd[1:] == ["--version"] else self.reply
        if isinstance(res, BaseException):
            raise res
        return res

    def ask_calls(self):
        return [(c, k) for c, k in self.calls if c[:2] == ["claude", "-p"]]


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-가짜")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    return FakeCLI(monkeypatch)


def test_T_AN_정상_답은_analyze_와_같은_결과_같은_프롬프트_같은_호출(cli):
    want = analyst.analyze("마라토너", CANDS)
    got, meta = analyst.analyze_logged("마라토너", CANDS)
    assert got == want
    assert set(got) == {"AAPL", "MSFT"} and got["MSFT"]["verdict"] == " VETO"   # 결과는 원래 글자 그대로
    (c1, k1), (c2, k2) = cli.ask_calls()
    assert c2 == c1 == ["claude", "-p", analyst._build_prompt("마라토너", CANDS)]
    assert sorted(k2) == sorted(k1) == ["capture_output", "env", "text", "timeout"]
    assert k2["timeout"] == k1["timeout"] == analyst.TIMEOUT
    assert k2["capture_output"] is True and k2["text"] is True
    assert k2["env"] == k1["env"] and "ANTHROPIC_API_KEY" not in k2["env"]       # 구독 강제
    assert meta["status"] == "ok" and meta["returncode"] == 0
    assert meta["cli_version"] == "2.1.7 (Claude Code)" and meta["model"] is None
    assert isinstance(meta["elapsed_s"], float) and meta["elapsed_s"] >= 0
    assert datetime.fromisoformat(meta["asked_at"]).tzinfo is not None
    assert set(meta) == {"status", "asked_at", "elapsed_s", "returncode", "model", "cli_version"}


def test_T_AN_timeout_인자를_그대로_넘긴다(cli):
    analyst.analyze_logged("스프린터", CANDS, timeout=7)
    assert cli.ask_calls()[0][1]["timeout"] == 7


@pytest.mark.parametrize("value,want", [("claude-opus-x", "claude-opus-x"), ("", None)])
def test_T_AN_model_은_ANTHROPIC_MODEL(cli, monkeypatch, value, want):
    monkeypatch.setenv("ANTHROPIC_MODEL", value)
    _, meta = analyst.analyze_logged("마라토너", CANDS)
    assert meta["model"] == want


@pytest.mark.parametrize("version,want", [
    (OSError("없음"), None),
    (subprocess.TimeoutExpired(["claude", "--version"], 20), None),
    (_done("2.0.0", returncode=1), None),
    (_done(""), None),
    (_done("  3.0.1 (Claude Code)  \n"), "3.0.1 (Claude Code)"),
])
def test_T_AN_cli_version_이_실패해도_판정_결과는_같다(cli, version, want):
    cli.version = version
    want_result = analyst.analyze("마라토너", CANDS)
    got, meta = analyst.analyze_logged("마라토너", CANDS)
    assert got == want_result and meta["status"] == "ok"
    assert meta["cli_version"] == want


@pytest.mark.parametrize("reply,status,rc", [
    (subprocess.TimeoutExpired(["claude", "-p"], 150), "timeout", None),
    (OSError("실행 실패"), "os_error", None),
    (_done(GOOD, returncode=2), "nonzero_exit", 2),
    (_done("설명만 있고 JSON 없음"), "bad_json", 0),
    (_done('{"analysis": [}'), "bad_json", 0),
    (_done('{"result": []}'), "bad_json", 0),            # analysis 키 없음
    (_done('[{"code": "AAPL"}]'), "bad_json", 0),         # 객체가 아님(목록) → _extract_json 이 못 읽음
])
def test_T_F5c_상태별_결과는_analyze_와_같다(cli, reply, status, rc):
    cli.reply = reply
    want = analyst.analyze("파이오니어", CANDS)
    got, meta = analyst.analyze_logged("파이오니어", CANDS)
    assert want is None and got is None                   # 규칙 폴백
    assert meta["status"] == status and meta["returncode"] == rc
    assert meta["cli_version"] == "2.1.7 (Claude Code)"   # claude 는 있으니 버전은 기록
    assert len(cli.ask_calls()) == 2                       # analyze 1번 + analyze_logged 1번


def test_T_F5c_claude_없음은_부르지_않고_no_claude(cli):
    cli.installed = False
    assert analyst.analyze("마라토너", CANDS) is None
    got, meta = analyst.analyze_logged("마라토너", CANDS)
    assert got is None and meta["status"] == "no_claude"
    assert cli.calls == []                                 # claude -p 도 --version 도 안 부름
    assert meta["cli_version"] is None and meta["returncode"] is None and meta["elapsed_s"] == 0.0


def test_T_F5c_빈_후보는_claude_를_부르지_않고_empty(cli):
    assert analyst.analyze("마라토너", []) is None
    got, meta = analyst.analyze_logged("마라토너", [])
    assert got is None and meta["status"] == "empty"
    assert cli.calls == [] and cli.which_calls == []
    assert datetime.fromisoformat(meta["asked_at"]).tzinfo is not None


def test_T_F5c_analysis_가_목록이_아니면_bad_json_폴백(cli):
    """analyze() 는 이 경우 TypeError 로 멈춘다(지금 동작, 고치지 않음). analyze_logged 는 폴백으로 기록한다."""
    cli.reply = _done('{"analysis": 3}')
    with pytest.raises(TypeError):
        analyst.analyze("마라토너", CANDS)
    got, meta = analyst.analyze_logged("마라토너", CANDS)
    assert got is None and meta["status"] == "bad_json" and meta["returncode"] == 0


def test_T_F5c_analysis_항목이_없으면_빈_dict_도_analyze_와_같다(cli):
    cli.reply = _done('{"analysis": []}')
    assert analyst.analyze("마라토너", CANDS) == {}
    got, meta = analyst.analyze_logged("마라토너", CANDS)
    assert got == {} and meta["status"] == "ok"


# ======================= T-F5d: 판정 글자 정리 =======================

@pytest.mark.parametrize("raw,want", [
    (" VETO", "veto"), ("Hold", "hold"), ("BUY\n", "buy"), ("\thold ", "hold"),
    ("buy", "buy"), ("hold", "hold"), ("veto", "veto"),
    ("maybe", None), ("", None), ("   ", None), ("ve to", None), ("buy!", None),
    (None, None), (1, None), (0.5, None), (["veto"], None), ({"verdict": "veto"}, None),
])
def test_T_F5d_normalize_verdict(raw, want):
    assert analyst.normalize_verdict(raw) == want


def test_T_F5d_운영_apply_는_지금_그대로():
    """운영 analyst.apply 는 정확히 "veto" 만 뺀다. " VETO"·"Veto" 는 빼지 않는다(지금 동작 그대로, 설계 §1.1 표).
    H1 은 normalize_verdict 로 정리한 값을 쓴다(다음 단계 h1.Leader)."""
    cands = [{"code": c} for c in ("A", "B", "C", "D")]
    analysis = {"A": {"verdict": " VETO", "conviction": 0.9}, "B": {"verdict": "veto"},
                "C": {"verdict": "Hold", "conviction": 0.7}, "D": {"verdict": "Veto"}}
    kept = analyst.apply(cands, analysis)
    assert [c["code"] for c in kept] == ["A", "C", "D"]
    assert kept[0]["conviction"] == 0.9 and kept[1]["conviction"] == 0.7
    assert [analyst.normalize_verdict(analysis[c]["verdict"]) for c in "ABCD"] == ["veto", "veto", "hold", "veto"]


# ======================= T-SCR: screener.scan_frames =======================

ORDER = ["A", "X", "B", "S", "C", "T", "D", "E"]     # X = 받기 실패(frames 에 없음)


def _frames():
    fr = {c: synth(seed=i + 1) for i, c in enumerate("ABCDE")}
    fr["S"] = synth(seed=11, start="2026-08-10")                       # 짧은 이력(70봉 미만)
    fr["T"] = synth(seed=12, end="2026-10-20")                          # 자료가 일찍 끝남(오래된 봉)
    return fr


ASOFS = [d.date().isoformat() for d in pd.bdate_range("2026-08-03", "2026-11-03")] + ["2026-10-24", "2026-11-08"]


def test_T_SCR_asof_로_자른_결과는_미리_자른_시세의_결과와_같다():
    fr = _frames()
    n_cands = 0
    for asof in ASOFS:
        cut = {c: df[df.index <= pd.Timestamp(asof)] for c, df in fr.items()}
        got = screener.scan_frames(fr, ORDER, asof=asof)
        assert got == screener.scan_frames(cut, ORDER), asof
        assert all(c["date"] <= asof for cs in got[0].values() for c in cs)    # 미래 봉 신호 없음
        n_cands += sum(len(cs) for cs in got[0].values())
    assert n_cands > 0                                     # 후보가 실제로 나온 날이 있어야 의미 있음


def test_T_SCR_세는_종목과_후보_모양():
    fr = _frames()
    found, used = screener.scan_frames(fr, ORDER)
    assert used == 6                                       # A~E·T (X 없음, S 는 70봉 미만)
    assert list(found) == list(screener.BRAINS)
    for cs in found.values():
        for c in cs:
            assert set(c) == {"code", "price", "date", "rsi", "reason"}
            assert c["price"] == round(c["price"], 2) and c["rsi"] == round(c["rsi"], 1)
            assert c["code"] != "T" and c["date"] == "2026-11-03"   # 오래된 봉 종목은 빠짐
    assert screener.scan_frames(fr, ORDER, min_bars=50)[1] == 7      # S(약 60봉)도 셈
    assert screener.scan_frames(fr, ORDER, asof="2026-10-20")[1] == 6
    assert screener.scan_frames({}, ORDER) == ({t: [] for t in screener.BRAINS}, 0)


def _fake_brain(buy_on):
    class FakeBrain:
        def add_indicators(self, df):
            return df.copy()

        def decide(self, df, position):
            day = df.index[-1].date().isoformat()
            return ("매수", f"가짜 매수 {day}") if day in buy_on else ("관망", "가짜 관망")
    return FakeBrain


def test_T_SCR_brains_인자와_기본값(monkeypatch):
    fr = _frames()
    fake = {"가짜": _fake_brain({"2026-10-07"})}
    assert int((fr["S"].index <= pd.Timestamp("2026-10-07")).sum()) < 70     # 이날 S 는 70봉 미만
    found, used = screener.scan_frames(fr, ORDER, asof="2026-10-07", brains=fake)
    assert list(found) == ["가짜"] and used == 6
    assert [c["code"] for c in found["가짜"]] == ["A", "B", "C", "T", "D", "E"]   # order 순서, X·S 없음
    # 오래된 봉: T 는 10-20 에 자료가 끝남 → 10-21 스캔에서 T 의 10-20 신호는 빠진다
    late = {"가짜": _fake_brain({"2026-10-20", "2026-10-21"})}
    found_l, used_l = screener.scan_frames(fr, ORDER, asof="2026-10-21", brains=late)
    assert used_l == 6 and [c["code"] for c in found_l["가짜"]] == ["A", "B", "C", "D", "E"]
    assert [c["code"] for c in screener.scan_frames(fr, ORDER, asof="2026-10-20", brains=late)[0]["가짜"]] == \
        ["A", "B", "C", "T", "D", "E"]
    assert all(c["rsi"] is None and c["reason"] == "가짜 매수 2026-10-07" for c in found["가짜"])   # RSI 칸 없음 → None
    assert set(screener.BRAINS) == {"마라토너", "스프린터", "파이오니어"}    # 모듈 값은 그대로
    # brains=None 이면 '부를 때의' screener.BRAINS 를 쓴다(재현 W3 가 바꿔 끼울 수 있게)
    monkeypatch.setattr(screener, "BRAINS", {"가짜2": _fake_brain({"2026-10-07"})})
    found2, _ = screener.scan_frames(fr, ORDER, asof="2026-10-07")
    assert list(found2) == ["가짜2"]


def test_T_SCR_scan_은_시세를_받아_scan_frames_를_한_번_부른다(monkeypatch):
    fr = {c: synth(seed=20 + i) for i, c in enumerate(screener.universe(6, "kr"))}
    failing = screener.universe(6, "kr")[2]

    def fake_load(code, start, now=None, market="us"):
        assert market == "kr" and start == screener.START
        if code == failing:
            raise ConnectionError("가짜 네트워크 오류")
        return fr[code]

    monkeypatch.setattr(main, "load_prices", fake_load)
    seen = []
    real = screener.scan_frames

    def spy(frames, order, *a, **k):
        seen.append((dict(frames), list(order), a, k))
        return real(frames, order, *a, **k)

    monkeypatch.setattr(screener, "scan_frames", spy)
    got = screener.scan(6, market="kr")
    assert len(seen) == 1
    frames, order, a, k = seen[0]
    assert order == screener.universe(6, "kr") and a == () and k == {}
    assert list(frames) == [c for c in order if c != failing]          # 받기 실패 종목은 빠짐
    assert all(frames[c] is fr[c] for c in frames)
    assert got == real(frames, order) and got[1] == 5


# ======================= T-RSI: 지표 길이 =======================

@pytest.mark.parametrize("seed", [3, 4, 5])
def test_T_RSI_2024_06_01_부터_계산해도_2026_06_이후는_같다(seed):
    df = synth(seed=seed, start="2015-01-02", end="2026-11-03")
    short = df.loc[team.START:]                                          # 운영 지표 시작 2024-06-01
    after = df.index >= pd.Timestamp("2026-06-01")
    full_rsi = ta.momentum.rsi(df["Close"], window=14)
    short_rsi = ta.momentum.rsi(short["Close"], window=14).reindex(df.index)
    assert after.sum() > 100
    assert float((full_rsi[after] - short_rsi[after]).abs().max()) < 1e-9
    # 브레인이 실제로 쓰는 지표 전부(이동평균은 창이 짧아 정확히 같고, RSI 는 거의 같음)
    for cls in screener.BRAINS.values():
        a = cls().add_indicators(df)
        b = cls().add_indicators(short).reindex(df.index)
        for col in a.columns:
            diff = float((a.loc[after, col] - b.loc[after, col]).abs().max())
            assert diff < 1e-9, (cls.__name__, col, diff)
