"""S0 국내 수정 테스트 (2026-11-04, docs/kr-fix-s0.md) — 네트워크·증권사 키 없음, 합성 DataFrame.

S0-1 벤치마크 기준 맞추기:
- 국내 벤치마크는 KOSPI 200 가격지수 KS200. load_benchmark 경로(allow_index)로만 받는다.
- 미국 티커는 allow_index 를 줘도 국내 종목코드로 거부된다. KS200 도 종목 경로로는 거부된다.
- 국내 비교 줄은 "KOSPI 200" 과 "원"을 찍는다 ("$"·"SPY"·"KODEX" 없음).

S0-2 거래정지일 체결:
- 국내 confirmed_bars 는 Volume == 0 행을 버린다. 미국은 그대로.
- open_price 는 시가가 0·NaN·없음이면 None (종가로 대신하지 않음). fill_pending 은 주문을 살려 둔다.
- 3일 거래정지: 정지일 체결 0건, 정지가 풀린 첫 거래일 시가에 체결 — 두 모양 모두
  (Open=0 / Open>0 이고 Volume=0), team.run_trainer 경로와 main.fill_pending(live·백테스트) 경로 모두.
- kr_halt_check.py: 정지일 체결만 찾아 알려 주고, 파일은 하나도 안 바꾼다.
"""
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main            # noqa: E402
import markets         # noqa: E402
import live            # noqa: E402
import team            # noqa: E402
import kr_halt_check   # noqa: E402
from risk_guard import CircuitBreaker   # noqa: E402

CODE = "005930"


def d(ts):
    return pd.Timestamp(ts).date().isoformat()


def synth(seed=11, start="2026-06-01", end="2026-10-30", base=70_000.0):
    """결정적인 가짜 국내 시세. Open 은 Close 와 일부러 다르게 (시가 체결을 구분하려고)."""
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = np.round(base * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(idx)))))
    opn = np.round(close * (1 + rng.normal(0, 0.01, len(idx))))
    return pd.DataFrame({
        "Open": opn, "High": np.maximum(opn, close) * 1.01, "Low": np.minimum(opn, close) * 0.99,
        "Close": close, "Volume": rng.integers(1_000_000, 3_000_000, len(idx)).astype(float),
    }, index=idx)


def with_halt(df, first, n, form):
    """df 의 first 번째 봉부터 n 개를 거래정지일로 바꾼다 (네이버 실제 모양 두 가지).
    form="zero": Open=High=Low=0, Close=직전 종가, Volume=0   (삼성전자 2018-04-30 등 88행)
    form="flat": OHLC 전부 직전 종가, Volume=0                (삼성바이오로직스 2018-11-15 ~ 12-10, 35행)"""
    df = df.copy()
    prev = float(df["Close"].iloc[first - 1])
    for i in range(first, first + n):
        if form == "zero":
            df.iloc[i, df.columns.get_indexer(["Open", "High", "Low"])] = 0.0
        else:
            df.iloc[i, df.columns.get_indexer(["Open", "High", "Low"])] = prev
        df.iloc[i, df.columns.get_loc("Close")] = prev
        df.iloc[i, df.columns.get_loc("Volume")] = 0.0
    return df


class FakeBrain:
    """정해진 날짜에만 매수 신호를 내는 가짜 두뇌 (지표 없음 → 매일 판단)."""

    def __init__(self, buy_on=()):
        self.buy_on = set(buy_on)

    def add_indicators(self, df):
        return df.copy()

    def decide(self, df, position):
        if position is None and d(df.index[-1]) in self.buy_on:
            return "매수", "가짜 매수 신호"
        return "관망", "가짜 관망"


@pytest.fixture
def halted():
    """3일 거래정지 시나리오: 신호 봉 S → 정지 H1~H3 → 정지 뒤 첫 거래일 R → 그다음 봉 L."""
    base = synth()
    n = len(base)
    s_i = n - 6
    days = [d(x) for x in base.index]
    return {"base": base, "S": days[s_i], "H": days[s_i + 1:s_i + 4], "R": days[s_i + 4], "L": days[s_i + 5],
            "r_open": float(base["Open"].iloc[s_i + 4]), "s_i": s_i}


def fake_fdr(monkeypatch, frames, cut, calls=None):
    """FinanceDataReader 를 가짜로: frames[code] 에서 cut[0] 날짜까지만 돌려준다 (진짜 load_prices·confirmed_bars 를 거침)."""
    def reader(code, start):
        if calls is not None:
            calls.append(code)
        return frames[code].loc[start:cut[0]].copy()
    monkeypatch.setitem(sys.modules, "FinanceDataReader", types.SimpleNamespace(DataReader=reader))


def _buys(log):
    return [e for e in log if e["종류"] == "매수"]


# ================= S0-2 ① 데이터: 국내 confirmed_bars 는 Volume == 0 행을 버린다 =================

@pytest.mark.parametrize("form", ["zero", "flat"])
def test_국내_확정_봉은_거래량_0_행을_버리고_미국은_그대로(halted, form):
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, form)
    raw.iloc[2, raw.columns.get_loc("Volume")] = np.nan          # 거래량 '모름'(NaN) 행은 남긴다
    now = pd.Timestamp("2026-11-04 12:00", tz="Asia/Seoul").to_pydatetime()
    kr = main.confirmed_bars(raw, now=now, market="kr")
    assert len(kr) == len(raw) - 3
    assert not set(halted["H"]) & {d(x) for x in kr.index}
    assert (kr["Volume"] != 0).all() and d(kr.index[2]) == d(raw.index[2])
    us = main.confirmed_bars(raw, now=now)                        # 미국 규칙은 바뀌지 않음
    assert len(us) == len(raw) and us.equals(raw)


def test_국내_확정_봉_거래량_칸이_없으면_그대로():
    df = synth().drop(columns=["Volume"])
    now = pd.Timestamp("2026-11-04 12:00", tz="Asia/Seoul").to_pydatetime()
    assert len(main.confirmed_bars(df, now=now, market="kr")) == len(df)


# ================= S0-2 ② 체결: open_price 는 종가로 대신하지 않는다 =================

@pytest.mark.parametrize("bar", [
    pd.Series({"Open": 0.0, "Close": 53_000.0}),
    pd.Series({"Open": np.nan, "Close": 53_000.0}),
    pd.Series({"Open": -1.0, "Close": 53_000.0}),
    pd.Series({"Open": "빈칸", "Close": 53_000.0}),
    pd.Series({"Close": 53_000.0}),                    # Open 칸 자체가 없음
    {"Open": None, "Close": 53_000.0},
])
def test_open_price_시가_없으면_None(bar):
    assert main.open_price(bar) is None


def test_open_price_정상_시가는_그대로():
    assert main.open_price(pd.Series({"Open": 53_100.0, "Close": 53_000.0})) == 53_100.0


@pytest.mark.parametrize("bad_open", [0.0, np.nan])
def test_fill_pending_시가_없으면_주문이_살아_있다(bad_open):
    st = main.new_state("스프린터", 3_000_000, "2026-10-01", "kr")
    order = {"action": "매수", "signal_date": "2026-10-01", "reason": "신호"}
    st["pending"] = dict(order)
    cash_before, log_before = st["wallet"].cash, list(st["wallet"].log)
    msg = main.fill_pending(st, CODE, pd.Series({"Open": bad_open, "Close": 53_000.0}),
                            "2026-10-02", 3_000_000, 0.2, "kr")
    assert st["pending"] == order                         # 주문이 지워지지 않음
    assert st["position"] is None and st["wallet"].cash == cash_before and st["wallet"].log == log_before
    assert msg and "미룸" in msg and "$" not in msg
    # 다음 거래된 봉에서는 그 봉 시가로 체결
    msg = main.fill_pending(st, CODE, pd.Series({"Open": 53_500.0, "Close": 54_000.0}),
                            "2026-10-05", 3_000_000, 0.2, "kr")
    assert st["pending"] is None and st["position"]["buy_price"] == 53_500.0
    assert st["position"]["buy_date"] == "2026-10-05" and "53,500원" in msg


def test_fill_pending_매도도_시가_없으면_보유와_주문_유지():
    st = main.new_state("스프린터", 3_000_000, "2026-10-01", "kr")
    st["wallet"].buy(CODE, 50_000, 10, "2026-10-01")
    st["position"] = {"buy_price": 50_000, "days_held": 3, "shares": 10, "buy_date": "2026-10-01"}
    st["pending"] = {"action": "매도", "signal_date": "2026-10-06", "reason": "손절"}
    main.fill_pending(st, CODE, pd.Series({"Open": 0.0, "Close": 49_000.0}), "2026-10-07", 3_000_000, 0.2, "kr")
    assert st["pending"]["action"] == "매도" and st["position"]["shares"] == 10
    assert CODE in st["wallet"].holdings and not [e for e in st["wallet"].log if e["종류"] == "매도"]


# ================= S0-2 ③ 3일 거래정지 — team.run_trainer 경로 =================

def _team_days(monkeypatch, tmp_path, halted, frames):
    """S 에 낸 매수 주문을 들고, H1~H3·R 을 하루씩 team.run_trainer 로 처리한다 (매일 새 cache = 매일 새 실행)."""
    monkeypatch.setattr(team, "STATE_DIR", tmp_path / "state")
    cut = [halted["S"]]
    fake_fdr(monkeypatch, frames, cut)
    st = team._new_state("스프린터", 3_000_000, halted["S"], "kr")
    st["pending"] = [{"code": CODE, "action": "매수", "signal_date": halted["S"], "reason": "신호", "note": None}]
    st["last_date"] = halted["S"]
    breaker = CircuitBreaker(0.10, 0.07)
    for day in halted["H"]:
        cut[0] = day
        _, st = team.run_trainer("스프린터", 3_000_000, 0.2, breaker, [], day, st=st, cache={}, mk="kr")
        assert not _buys(st["wallet"].log), f"거래정지일 {day} 에 체결됨"
        assert [o["code"] for o in st["pending"]] == [CODE]          # 주문은 계속 대기
        assert CODE not in st["positions"]
    cut[0] = halted["R"]
    _, st = team.run_trainer("스프린터", 3_000_000, 0.2, breaker, [], halted["R"], st=st, cache={}, mk="kr")
    return st


@pytest.mark.parametrize("form", ["zero", "flat"])
def test_3일_거래정지_team_은_정지_뒤_첫_거래일_시가에_체결(monkeypatch, tmp_path, halted, form):
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, form)
    st = _team_days(monkeypatch, tmp_path, halted, {CODE: raw})
    buys = _buys(st["wallet"].log)
    assert len(buys) == 1 and buys[0]["시각"] == halted["R"] and buys[0]["통화"] == "KRW"
    n = buys[0]["수량"]
    assert buys[0]["금액"] == pytest.approx(halted["r_open"] * 1.0005 * n * 1.00015, abs=0.01)
    assert st["positions"][CODE]["buy_price"] == halted["r_open"]
    assert st["positions"][CODE]["buy_date"] == halted["R"]
    assert all(o["action"] != "매수" for o in st["pending"])        # 매수 주문은 체결돼서 빠짐
    saved = json.loads((tmp_path / "state" / "kr" / "team_스프린터.json").read_text(encoding="utf-8"))
    assert [e["시각"] for e in saved["wallet"]["log"] if e["종류"] == "매수"] == [halted["R"]]


def test_team_시가_없는_봉은_데이터에_남아_있어도_건너뛴다(monkeypatch, tmp_path, halted):
    """② 체결 층만 따로: 정지 행(Open=0)이 걸러지지 않은 시세가 cache 로 들어와도 정지일에는 안 산다."""
    monkeypatch.setattr(team, "STATE_DIR", tmp_path / "state")
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, "zero")
    st = team._new_state("스프린터", 3_000_000, halted["S"], "kr")
    st["pending"] = [{"code": CODE, "action": "매수", "signal_date": halted["S"], "reason": "신호"}]
    st["last_date"] = halted["S"]
    breaker = CircuitBreaker(0.10, 0.07)
    for day in halted["H"]:
        cache = {CODE: raw[[x <= day for x in (d(i) for i in raw.index)]]}
        _, st = team.run_trainer("스프린터", 3_000_000, 0.2, breaker, [], day, st=st, cache=cache, mk="kr")
        assert not _buys(st["wallet"].log) and len(st["pending"]) == 1
    # 며칠 밀려서 한 번에 처리해도(정지 3일 + R 이 한 실행 안에) 첫 '시가 있는' 봉 R 에 체결
    st2 = team._new_state("스프린터", 3_000_000, halted["S"], "kr")
    st2["pending"] = [{"code": CODE, "action": "매수", "signal_date": halted["S"], "reason": "신호"}]
    st2["last_date"] = halted["S"]
    for s, bar_date in ((st, halted["R"]), (st2, halted["L"])):
        _, s = team.run_trainer("스프린터", 3_000_000, 0.2, breaker, [], bar_date, st=s,
                                cache={CODE: raw}, mk="kr")
        buys = _buys(s["wallet"].log)
        assert len(buys) == 1 and buys[0]["시각"] == halted["R"]
        assert s["positions"][CODE]["buy_price"] == halted["r_open"]


def test_KR_데이터_층이_필요한_이유_정지_모양_flat_은_시가가_있다(halted):
    """Open>0 이고 Volume=0 인 모양(삼성바이오로직스)은 open_price 만으로는 못 막는다 → confirmed_bars 가 버린다."""
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, "flat")
    h1 = raw.loc[halted["H"][0]]
    assert main.open_price(h1) == float(raw["Close"].iloc[halted["s_i"]])     # 시가는 '있어' 보인다
    kr = main.confirmed_bars(raw, now=pd.Timestamp("2026-11-04 12:00", tz="Asia/Seoul").to_pydatetime(),
                             market="kr")
    assert halted["H"][0] not in {d(x) for x in kr.index}


# ================= S0-2 ③ 3일 거래정지 — main.fill_pending 경로 (live·백테스트) =================

@pytest.mark.parametrize("form", ["zero", "flat"])
def test_3일_거래정지_live_는_정지_뒤_첫_거래일_시가에_체결(monkeypatch, tmp_path, halted, form):
    monkeypatch.setattr(live, "STATE_DIR", tmp_path / "state")
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, form)
    cut = [halted["S"]]
    fake_fdr(monkeypatch, {CODE: raw}, cut)
    brain = FakeBrain(buy_on=[halted["S"]])
    args = ("스프린터", brain, 0.2, CODE, "삼성전자", 3_000_000, CircuitBreaker(0.10, 0.07))
    _, st = live.step_one(*args, mk="kr")                               # S: 매수 신호 → pending
    assert st["pending"]["action"] == "매수" and st["last_date"] == halted["S"]
    for day in halted["H"]:
        cut[0] = day
        line, st = live.step_one(*args, mk="kr")
        assert "새 확정 봉 없음" in line                                  # 정지일은 이 종목에 '없던 날'
        assert not _buys(st["wallet"].log) and st["pending"]["action"] == "매수"
    cut[0] = halted["R"]
    _, st = live.step_one(*args, mk="kr")
    buys = _buys(st["wallet"].log)
    assert len(buys) == 1 and buys[0]["시각"] == halted["R"]
    n = buys[0]["수량"]
    assert buys[0]["금액"] == pytest.approx(halted["r_open"] * 1.0005 * n * 1.00015, abs=0.01)
    eq = (tmp_path / "state" / "kr" / "삼성전자_스프린터_평가금액.csv").read_text(encoding="utf-8-sig")
    assert not any(h in eq for h in halted["H"])                        # 정지일 평가금액 줄도 없음


@pytest.mark.parametrize("form", ["zero", "flat"])
def test_3일_거래정지_백테스트도_정지_뒤_첫_거래일_시가에_체결(halted, form):
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, form)
    df = main.confirmed_bars(raw, now=pd.Timestamp("2026-11-04 12:00", tz="Asia/Seoul").to_pydatetime(),
                             market="kr")
    r = main.run_one_trainer("스프린터", FakeBrain(buy_on=[halted["S"]]), df, 3_000_000, 0.2, CODE, mk="kr")
    buys = _buys(r["log"])
    assert len(buys) == 1 and buys[0]["시각"] == halted["R"]


def test_백테스트_정지_행이_남아_있어도_trade_day_는_정지일에_안_산다(halted):
    """② 체결 층만 따로 (Open=0 모양, 데이터 층을 거치지 않음)."""
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, "zero")
    r = main.run_one_trainer("스프린터", FakeBrain(buy_on=[halted["S"]]), raw, 3_000_000, 0.2, CODE, mk="kr")
    buys = _buys(r["log"])
    assert len(buys) == 1 and buys[0]["시각"] == halted["R"]
    n = buys[0]["수량"]
    assert buys[0]["금액"] == pytest.approx(halted["r_open"] * 1.0005 * n * 1.00015, abs=0.01)


# ================= S0-1 벤치마크 KS200 =================

def test_국내_벤치마크는_KS200_을_벤치마크_경로로_받는다(monkeypatch, halted):
    ks = synth(seed=3, base=900.0)
    calls = []
    fake_fdr(monkeypatch, {"KS200": ks, CODE: halted["base"]}, [ks.index[-1]], calls)
    assert markets.get_market("kr").benchmark == "KS200"
    out = main.load_benchmark("2026-06-01", "kr")
    assert calls == ["KS200"] and out is not None and len(out) == len(ks)
    # 종목 경로로는 지수 기호를 받지 않는다 (allow_index 없이)
    with pytest.raises(ValueError):
        main.load_prices("KS200", "2026-06-01", market="kr")
    with pytest.raises(ValueError):
        main.prices_for("kr", "KS200", "2026-06-01")
    # allow_index 를 줘도 '벤치마크 기호 하나'만 — 미국 티커는 여전히 국내 종목코드가 아님
    with pytest.raises(ValueError):
        main.load_prices("AAPL", "2026-06-01", market="kr", allow_index=True)
    with pytest.raises(ValueError):
        main.load_prices("AAPL", "2026-06-01", market="kr")
    assert calls == ["KS200"]                                  # 거부된 값은 인터넷 조회도 안 함
    assert not markets.code_ok("kr", "KS200") and not markets.code_ok("kr", "AAPL")
    assert len(main.load_prices(CODE, "2026-06-01", market="kr")) > 0     # 6자리 종목은 그대로


def test_국내_벤치마크_받기_실패하면_None_과_KOSPI_200_안내(monkeypatch, capsys):
    def boom(code, start):
        raise ConnectionError("인터넷 없음")
    monkeypatch.setitem(sys.modules, "FinanceDataReader", types.SimpleNamespace(DataReader=boom))
    assert main.load_benchmark("2026-06-01", "kr") is None
    out = capsys.readouterr().out
    assert "KOSPI 200(가격지수)" in out and "KS200" in out and "KODEX" not in out


def test_국내_비교_줄은_KOSPI_200_과_원(halted):
    df = halted["base"]
    ks = synth(seed=3, base=900.0)
    days = [d(x) for x in df.index]
    line = main.compare("마라토너", 12_345.0, df, 1_800_000, ks, days[0], days[-1], mk="kr")
    assert "KOSPI 200(가격지수)" in line and "원" in line
    assert "$" not in line and "SPY" not in line and "KODEX" not in line and "nan" not in line.lower()
    # 미국 비교 줄은 그대로 SPY·$
    us = main.compare("마라토너", 12.0, df / 500, 1_800, ks, days[0], days[-1])
    assert "SPY" in us and "$" in us and "KOSPI" not in us


def test_team_국내_요약_줄도_KOSPI_200(capsys, halted):
    ks = synth(seed=3, base=900.0)
    days = [d(x) for x in ks.index]
    st = team._new_state("마라토너", 6_000_000, days[0], "kr")
    st["last_date"], st["prev_value"] = days[-1], 6_100_000.0
    team._summary({"마라토너": st}, ks, "kr")
    out = capsys.readouterr().out
    assert "KOSPI 200(가격지수)" in out and "원" in out and "$" not in out and "SPY" not in out


# ================= kr_halt_check.py (읽기만 하는 점검 스크립트) =================

def _ledger(tmp_path, halted):
    """team·live·main 세 형식의 국내 장부를 만든다. 정지일 체결 2건(team·main) + 정상 체결."""
    sd = tmp_path / "state" / "kr"; sd.mkdir(parents=True)
    rd = tmp_path / "results"; rd.mkdir()
    h1, r = halted["H"][0], halted["R"]

    def wallet(name, log):
        w = main.make_wallet(name, "kr")
        from dataclasses import asdict
        data = asdict(w); data["log"] = log
        return data

    buy_h = {"시각": h1, "종류": "매수", "종목": CODE, "수량": 10, "금액": 534_000.0, "통화": "KRW"}
    buy_r = {"시각": r, "종류": "매수", "종목": CODE, "수량": 10, "금액": 700_000.0, "통화": "KRW"}
    skip_h = {"시각": h1, "종류": "보류", "종목": CODE, "수량": 0, "금액": 0.0, "통화": "KRW", "사유": "x"}
    dep = {"시각": halted["S"], "종류": "입금", "종목": None, "수량": 0, "금액": 6_000_000, "통화": "KRW"}
    team_st = {"schema": main.STATE_SCHEMA_KR, "wallet": wallet("마라토너", [dep, buy_h, skip_h]), "pending": []}
    live_st = {"schema": main.STATE_SCHEMA_KR, "wallet": wallet("스프린터", [dep, buy_r]), "pending": None}
    (sd / "team_마라토너.json").write_text(json.dumps(team_st, ensure_ascii=False), encoding="utf-8")
    (sd / "삼성전자_스프린터.json").write_text(json.dumps(live_st, ensure_ascii=False), encoding="utf-8")
    (sd / "삼성전자_스프린터_평가금액.csv").write_text("날짜,평가금액\n", encoding="utf-8-sig")
    with open(rd / "kr_삼성전자_파이오니어_거래내역.csv", "w", newline="", encoding="utf-8-sig") as f:
        f.write("시각,종류,종목,수량,금액,통화,사유\n")
        f.write(f"{halted['H'][2]},매도,{CODE},3,150000.0,KRW,\n")
        f.write(f"{r},매수,{CODE},3,150000.0,KRW,\n")
    return sd, rd


def _snapshot(*dirs):
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for root in dirs for p in sorted(root.rglob("*"))
            if p.is_file()}


@pytest.mark.parametrize("form", ["zero", "flat"])
def test_kr_halt_check_는_정지일_체결만_알리고_파일은_안_바꾼다(tmp_path, halted, form):
    sd, rd = _ledger(tmp_path, halted)
    raw = with_halt(halted["base"], halted["s_i"] + 1, 3, form)
    before = _snapshot(tmp_path)
    lines, asked = [], []
    rc = kr_halt_check.main(["--state", str(sd), "--results", str(rd)],
                            loader=lambda code, start: (asked.append(code), raw.loc[start:])[1],
                            out=lines.append)
    text = "\n".join(lines)
    assert rc == 1 and asked == [CODE]
    assert "거래정지일 체결 2건" in text
    assert f"team_마라토너.json | 마라토너 | 매수 {CODE} {halted['H'][0]}" in text
    assert f"kr_삼성전자_파이오니어_거래내역.csv | 파이오니어 | 매도 {CODE} {halted['H'][2]}" in text
    assert "Volume=0" in text and ("Open<=0" in text) == (form == "zero")
    assert f"매수 {CODE} {halted['R']}" not in text                   # 정상 거래일 체결은 문제 아님
    assert _snapshot(tmp_path) == before                               # 읽기만: 바이트·수정시각 그대로


def test_kr_halt_check_정지일_체결이_없으면_0(tmp_path, halted):
    sd, rd = _ledger(tmp_path, halted)
    lines = []
    rc = kr_halt_check.main(["--state", str(sd), "--results", str(rd)],
                            loader=lambda code, start: halted["base"].loc[start:], out=lines.append)
    assert rc == 0 and any("거래정지일 체결 없음" in x for x in lines)


def test_kr_halt_check_시세를_못_받으면_2_장부가_없으면_0(tmp_path, halted):
    sd, rd = _ledger(tmp_path, halted)

    def boom(code, start):
        raise SystemExit("라이브러리 없음")
    lines = []
    assert kr_halt_check.main(["--state", str(sd), "--results", str(rd)], loader=boom, out=lines.append) == 2
    assert any("확인 못 함" in x for x in lines)
    empty = tmp_path / "없음"
    assert kr_halt_check.main(["--state", str(empty), "--results", str(empty)],
                              loader=boom, out=lambda *_: None) == 0
