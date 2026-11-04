"""S4 흐름 테스트 (네트워크 없음). main.load_prices 를 합성 데이터로 바꿔 끼운다.

확인하는 것:
- confirmed_bars: 종가 NaN 행·장중(16:15 ET 전) 오늘 봉을 버린다 (D1)
- 백테스트: 봉 t 신호 → 봉 t+1 시가 체결, 마지막 봉 신호는 미체결 (D3)
- 상한 초과 매수 0건, 1주도 못 사면 '보류' + 사유 로그 (D5)
- live: 같은 봉으로 두 번 돌려도 그대로(멱등), 새 봉에서 pending 이 시가로 체결 (D2·D3)
- team: 후보·보유가 없으면 날짜 저장 안 함, 다 처리됐으면 스캔 생략(N5), 팀장 hold/문자열 확신도
- 상태 파일: 예전 형식은 보관 후 새로 시작, 저장은 임시파일 → 교체
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 저장소 루트를 import 경로에

import main      # noqa: E402
import live      # noqa: E402
import team      # noqa: E402
import screener  # noqa: E402
import analyst   # noqa: E402
from risk_guard import CircuitBreaker      # noqa: E402
from pioneer_brain import PioneerBrain     # noqa: E402
from sprinter_brain import SprinterBrain   # noqa: E402
from marathoner_brain import MarathonerBrain  # noqa: E402

ET = ZoneInfo("America/New_York")


def synth(seed=1, start="2025-01-01", end="2026-11-03", base=100.0):
    """결정적인 가짜 시세. Open 은 Close 와 일부러 다르게 (시가 체결을 구분하려고)."""
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = base * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(idx))))
    opn = close * (1 + rng.normal(0, 0.01, len(idx)))
    return pd.DataFrame({
        "Open": opn, "High": np.maximum(opn, close) * 1.01, "Low": np.minimum(opn, close) * 0.99,
        "Close": close, "Volume": rng.integers(1_000_000, 3_000_000, len(idx)).astype(float),
    }, index=idx)


class FakeBrain:
    """정해진 날짜에만 매수/매도 신호를 내는 가짜 두뇌. 지표 칼럼이 없으니 매일 판단한다."""

    def __init__(self, buy_on=(), sell_on=()):
        self.buy_on, self.sell_on = set(buy_on), set(sell_on)

    def add_indicators(self, df):
        return df.copy()

    def decide(self, df, position):
        d = df.index[-1].date().isoformat()
        if position is None and d in self.buy_on:
            return "매수", "가짜 매수 신호"
        if position is not None and d in self.sell_on:
            return "매도", "가짜 매도 신호"
        return "관망", "가짜 관망"


def d(ts):
    return pd.Timestamp(ts).date().isoformat()


# ---------------- D1: confirmed_bars ----------------

def _bars(last="2026-11-04"):
    idx = pd.bdate_range(end=last, periods=4)
    return pd.DataFrame({"Open": [1.0, 2, 3, 4], "Close": [1.0, 2, 3, 4], "Volume": [1.0] * 4}, index=idx)


def test_confirmed_bars_NaN_종가_행을_버린다():
    df = _bars()
    df.iloc[1, df.columns.get_loc("Close")] = np.nan
    df.iloc[-1, df.columns.get_loc("Close")] = np.nan     # yahoo: 거래량만 있고 종가 없는 마지막 봉
    out = main.confirmed_bars(df, now=datetime(2026, 11, 10, 12, tzinfo=ET))
    assert len(out) == 2 and out["Close"].notna().all()


def test_confirmed_bars_장중_오늘_봉은_버리고_마감_뒤엔_남긴다():
    df = _bars("2026-11-04")
    before = main.confirmed_bars(df, now=datetime(2026, 11, 4, 16, 14, tzinfo=ET))
    after = main.confirmed_bars(df, now=datetime(2026, 11, 4, 16, 15, tzinfo=ET))
    assert d(before.index[-1]) == "2026-11-03"
    assert d(after.index[-1]) == "2026-11-04"
    # 한국 시간 2026-11-05 05:00 = 뉴욕 11-04 15:00 → 아직 장중
    kst = datetime(2026, 11, 5, 5, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    assert d(main.confirmed_bars(df, now=kst).index[-1]) == "2026-11-03"
    # 다음날(주말 등)이면 마지막 봉은 이미 확정
    assert len(main.confirmed_bars(df, now=datetime(2026, 11, 7, 9, tzinfo=ET))) == 4


def test_load_prices_가_confirmed_bars_를_적용한다(monkeypatch):
    import types
    df = _bars("2026-11-04")
    df.iloc[0, df.columns.get_loc("Close")] = np.nan
    fake = types.SimpleNamespace(DataReader=lambda code, start: df.copy())
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fake)
    out = main.load_prices("AAPL", "2026-01-01", now=datetime(2026, 11, 4, 10, tzinfo=ET))
    assert len(out) == 2 and d(out.index[-1]) == "2026-11-03"


# ---------------- D3·D5: 백테스트 ----------------

def test_백테스트는_다음날_시가로_체결하고_마지막_신호는_미체결():
    df = synth()
    days = [d(x) for x in df.index]
    buy_sig, sell_sig = days[30], days[40]
    brain = FakeBrain(buy_on=[buy_sig, days[-1]], sell_on=[sell_sig])
    r = main.run_one_trainer("스프린터", brain, df, 3_000, 0.2, "X")
    trades = [e for e in r["log"] if e["종류"] in ("매수", "매도")]
    assert trades[0]["종류"] == "매수" and trades[0]["시각"] == days[31]      # t+1 에 체결
    assert trades[1]["종류"] == "매도" and trades[1]["시각"] == days[41]
    # 체결가는 t+1 의 시가 (종가 아님)
    n = trades[0]["수량"]
    open_next = float(df["Open"].iloc[31])
    assert trades[0]["금액"] == pytest.approx(open_next * 1.0005 * n * 1.001, abs=0.01)
    assert n * open_next * 1.0005 * 1.001 <= 3_000 * 0.2
    # 마지막 봉 신호는 체결 안 되고 남는다
    assert r["pending"] and r["pending"]["action"] == "매수" and r["pending"]["signal_date"] == days[-1]
    assert r["buys"] == 1 and r["closed"] == 1 and not r["still_holding"]


def test_상한_초과_매수_0건_실제_두뇌():
    for seed, base in ((1, 100), (2, 400), (3, 900)):
        df = synth(seed, start="2023-01-01", base=base)
        for name, cls in (("마라토너", MarathonerBrain), ("스프린터", SprinterBrain), ("파이오니어", PioneerBrain)):
            cash = main.CONFIG["총_가상자금"] * main.CONFIG["배분비율"][name]
            cap = main.CONFIG["종목상한"][name]
            r = main.run_one_trainer(name, cls(), df, cash, cap, "X", CircuitBreaker(0.10, 0.07))
            for e in r["log"]:
                if e["종류"] == "매수":
                    assert e["금액"] <= cash * cap + 1e-6, (name, seed, e)
                    assert e["통화"] == "USD"
            assert r["profit"] == r["profit"]   # NaN 아님


def test_1주도_못_사면_보류_사유_로그():
    df = synth(base=2_000)                   # 1주 ~$2,000, 파이오니어 상한 $1,000×0.15=$150
    days = [d(x) for x in df.index]
    r = main.run_one_trainer("파이오니어", FakeBrain(buy_on=[days[25]]), df, 1_000, 0.15, "BIG")
    skips = [e for e in r["log"] if e["종류"] == "보류"]
    assert len(skips) == 1 and r["skips"] == 1 and r["buys"] == 0
    assert skips[0]["시각"] == days[26] and "1주도 못 삼" in skips[0]["사유"]
    assert not any(e["종류"] == "매수" for e in r["log"])


def test_서킷_브레이커_정리도_다음날_시가():
    idx = pd.bdate_range("2026-01-01", periods=40)
    close = np.full(40, 100.0); close[30:] = 50.0     # 30번째 봉에서 -50% 급락
    opn = close.copy(); opn[31] = 47.0
    df = pd.DataFrame({"Open": opn, "Close": close, "Volume": 1.0}, index=idx)
    days = [d(x) for x in idx]
    r = main.run_one_trainer("스프린터", FakeBrain(buy_on=[days[22]]), df, 3_000, 0.9, "X",
                             CircuitBreaker(0.10, 0.07))
    assert r["stopped"]
    sells = [e for e in r["log"] if e["종류"] == "매도"]
    assert len(sells) == 1 and sells[0]["시각"] == days[31]
    assert sells[0]["금액"] == pytest.approx(47.0 * 0.9995 * 0.999 * sells[0]["수량"], abs=0.01)


# ---------------- live ----------------

@pytest.fixture
def market(monkeypatch, tmp_path):
    """가짜 시장: cut[0] 날짜까지의 데이터만 '확정'된 것처럼 돌려준다."""
    full = synth(5, start="2025-01-01", end="2026-11-03")
    spy = synth(9, start="2025-01-01", end="2026-11-03", base=500)
    cut = [full.index[-2]]

    def fake_load(code, start, now=None):
        src = spy if code == "SPY" else full
        return src.loc[start:cut[0]]

    monkeypatch.setattr(main, "load_prices", fake_load)
    monkeypatch.setattr(live, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(team, "STATE_DIR", tmp_path / "state")
    monkeypatch.setitem(main.CONFIG, "종목목록", {"가짜": "FAKE"})
    return {"full": full, "cut": cut, "dir": tmp_path / "state"}


def test_live_두번_실행_멱등_그리고_pending_체결(market):
    full, cut = market["full"], market["cut"]
    days = [d(x) for x in full.index]
    brain = FakeBrain(buy_on=[days[-2]])
    args = ("스프린터", brain, 0.2, "FAKE", "가짜", 3_000, CircuitBreaker(0.10, 0.07))

    line1, st = live.step_one(*args)
    f = market["dir"] / "가짜_스프린터.json"
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved["schema"] == main.STATE_SCHEMA and saved["last_date"] == days[-2]
    assert saved["pending"]["action"] == "매수" and not saved["wallet"]["holdings"]
    snap = f.read_bytes()

    line2, _ = live.step_one(*args)                       # 같은 봉으로 또 실행
    assert "새 확정 봉 없음" in line2
    assert f.read_bytes() == snap                         # 바이트까지 그대로

    cut[0] = full.index[-1]                               # 다음 거래일 봉이 확정됨
    line3, st = live.step_one(*args)
    saved = json.loads(f.read_text(encoding="utf-8"))
    buys = [e for e in saved["wallet"]["log"] if e["종류"] == "매수"]
    assert len(buys) == 1 and buys[0]["시각"] == days[-1]
    n = buys[0]["수량"]
    assert buys[0]["금액"] == pytest.approx(float(full["Open"].iloc[-1]) * 1.0005 * n * 1.001, abs=0.01)
    assert saved["pending"] is None and saved["last_date"] == days[-1]
    eq = (market["dir"] / "가짜_스프린터_평가금액.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(eq) == 3                                   # 머리줄 + 봉 2개 (중복 없음)


def test_live_예전_원화_상태파일은_보관하고_새로_시작(market):
    sd = market["dir"]; sd.mkdir(parents=True)
    old = {"wallet": {"name": "스프린터", "cash": 300000, "fee_rate": 0.00015, "holdings": {}, "log": []},
           "position": None, "prev_value": 300000, "stopped": False, "last_date": "2026-11-03"}
    (sd / "가짜_스프린터.json").write_text(json.dumps(old), encoding="utf-8")
    line, st = live.step_one("스프린터", FakeBrain(), 0.2, "FAKE", "가짜", 3_000, CircuitBreaker())
    assert list(sd.glob("가짜_스프린터.old-*.json"))
    saved = json.loads((sd / "가짜_스프린터.json").read_text(encoding="utf-8"))
    assert saved["schema"] == main.STATE_SCHEMA and saved["wallet"]["cash"] == 3_000
    assert saved["wallet"]["fee_rate"] == 0.001
    assert not list(sd.glob("*.tmp"))                     # 임시파일 남지 않음


def test_live_run_전체_출력에_nan_없음(market, capsys):
    live.run()
    live.run()
    out = capsys.readouterr().out
    assert "nan" not in out.lower()
    assert "SPY" in out and "$" in out and "원" not in out.replace("원칙", "")
    assert out.count("새 확정 봉 없음") == 3              # 두 번째 실행은 세 트레이너 모두 건너뜀


def test_save_json_atomic_은_os_replace_사용(tmp_path, monkeypatch):
    calls = []
    real = main.os.replace
    monkeypatch.setattr(main.os, "replace", lambda a, b: (calls.append((a, b)), real(a, b)))
    main.save_json_atomic(tmp_path / "s.json", {"a": 1})
    assert calls and str(calls[0][0]).endswith(".tmp")
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8")) == {"a": 1}


# ---------------- team ----------------

def test_team_후보_0개면_날짜_저장_안_함(market, monkeypatch):
    monkeypatch.setattr(screener, "scan", lambda n: ({t: [] for t in team.BRAINS}, 3))
    monkeypatch.setattr(analyst, "analyze", lambda *a, **k: pytest.fail("후보 없으면 팀장 호출 안 함"))
    team.run(3)
    assert not market["dir"].exists() or not list(market["dir"].glob("team_*.json"))


def test_team_다_처리됐으면_스캔_생략(market, monkeypatch, capsys):
    bar = d(market["cut"][0])
    for t in team.BRAINS:
        st = team._new_state(t, 1_000, bar)
        st["last_date"] = bar; st["prev_value"] = 1_000
        team._save(t, st)
    monkeypatch.setattr(screener, "scan", lambda n: pytest.fail("이미 처리됐는데 스캔함"))
    team.run(3)
    assert "스캔 생략" in capsys.readouterr().out


def test_team_hold_보류_문자열_확신도_그리고_다음날_시가_체결(market, monkeypatch):
    full, cut = market["full"], market["cut"]
    days = [d(x) for x in full.index]
    cands = [{"code": c, "price": 100.0, "rsi": 30.0, "reason": "신호", "date": days[-2]}
             for c in ("AAA", "BBB", "CCC", "DDD")]
    monkeypatch.setattr(screener, "scan", lambda n: ({"마라토너": cands, "스프린터": [], "파이오니어": []}, 4))
    monkeypatch.setattr(analyst, "analyze", lambda t, c, **k: {
        "AAA": {"code": "AAA", "verdict": "buy", "conviction": "0.9", "note": "좋음"},
        "BBB": {"code": "BBB", "verdict": "hold", "conviction": 0.8},
        "CCC": {"code": "CCC", "verdict": "buy", "conviction": "0.3"},
        "DDD": {"code": "DDD", "verdict": "buy", "conviction": "모름"},
    })
    team.run(4)
    st = json.loads((market["dir"] / "team_마라토너.json").read_text(encoding="utf-8"))
    assert st["last_date"] == days[-2] and not st["wallet"]["holdings"]
    assert sorted(o["code"] for o in st["pending"]) == ["AAA", "DDD"]   # 문자열 '모름' → None → 통과
    skips = {e["종목"]: e["사유"] for e in st["wallet"]["log"] if e["종류"] == "보류"}
    assert skips["BBB"] == "팀장 hold" and "확신도" in skips["CCC"]
    assert not (market["dir"] / "team_스프린터.json").exists()           # 후보 0개 → 저장 안 함

    cut[0] = full.index[-1]                                              # 다음 거래일
    monkeypatch.setattr(screener, "scan", lambda n: ({t: [] for t in team.BRAINS}, 4))
    team.run(4)
    st = json.loads((market["dir"] / "team_마라토너.json").read_text(encoding="utf-8"))
    buys = [e for e in st["wallet"]["log"] if e["종류"] == "매수"]
    assert {e["종목"] for e in buys} == {"AAA", "DDD"}
    assert all(e["시각"] == days[-1] for e in buys)
    cap = main.CONFIG["총_가상자금"] * 0.6 * 0.3
    assert all(e["금액"] <= cap + 1e-6 for e in buys)
    assert st["pending"] == [] and st["last_date"] == days[-1]


def test_compare_시작_봉_다음부터_비교():
    df = synth(4, start="2026-10-01", end="2026-10-20")
    spy = synth(8, start="2026-10-01", end="2026-10-20", base=500)
    days = [d(x) for x in df.index]
    first = main.compare("마라토너", 0.0, df, 1_800, spy, days[0], days[0])
    assert "다음 확정 봉부터" in first and "승" not in first   # 첫 봉엔 판정하지 않음
    line = main.compare("마라토너", 10.0, df, 1_800, spy, days[0], days[-1])
    assert "SPY" in line and "계산 불가" not in line and "nan" not in line.lower()
