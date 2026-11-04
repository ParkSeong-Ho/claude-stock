"""K4 국내 시장 테스트 (네트워크 없음, 합성 DataFrame). docs/kr-broker-design.md §3·K-D7~K-D11

확인하는 것:
- markets: 호가단위표(2023 개편) 올림/내림, 미국 0.01 단위, 금액 표기(원/$), 시장 값(비용·자금·벤치마크)
- 확정 봉: 국내는 한국 시간 16:00 전 '오늘 봉' 버림, 미국 기준(16:15 ET)은 그대로
- 비용: 국내 지갑 수수료 0.015%·매도세 0.20%·슬리피지 0.05%, 통화 KRW
- 통화 분리: 국내 지갑·로그는 전부 KRW, 국내 시세에 미국 티커 거부, 달러 상태 파일은 국내에서 안 이어 씀
- 상태 파일 경로: 국내 state/kr/team_<트레이너>.json, 미국 state/team_<트레이너>.json
- 스크리너: 국내는 KR_UNIVERSE 만(KRX 전체 목록 조회 안 함)
- 출력: 국내 team/live/main 에 '$'·'nan' 없음, 금액은 '원', KOSPI 200(가격지수) 비교 줄
  (2026-11-04 S0-1: 벤치마크 KODEX 200(069500) → KS200. 거래정지·KS200 세부는 tests/test_kr_fix_s0.py)
"""
import json
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main      # noqa: E402
import markets   # noqa: E402
import live      # noqa: E402
import team      # noqa: E402
import screener  # noqa: E402
import analyst   # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def synth(seed=1, start="2025-01-01", end="2026-11-03", base=70_000.0):
    """결정적인 가짜 국내 시세(원 단위 정수). Open 은 Close 와 일부러 다르게."""
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = np.round(base * np.exp(np.cumsum(rng.normal(0.0005, 0.02, len(idx)))))
    opn = np.round(close * (1 + rng.normal(0, 0.01, len(idx))))
    return pd.DataFrame({
        "Open": opn, "High": np.maximum(opn, close) * 1.01, "Low": np.minimum(opn, close) * 0.99,
        "Close": close, "Volume": rng.integers(1_000_000, 3_000_000, len(idx)).astype(float),
    }, index=idx)


def d(ts):
    return pd.Timestamp(ts).date().isoformat()


# ---------------- markets: 호가단위 ----------------

@pytest.mark.parametrize("price,buy,sell", [
    (1_234.4, 1_235, 1_234),       # 2,000 미만: 1원
    (1_999.5, 2_000, 1_999),
    (4_321, 4_325, 4_320),         # 5,000 미만: 5원
    (12_345, 12_350, 12_340),      # 20,000 미만: 10원
    (51_234, 51_300, 51_200),      # 200,000 미만: 100원  (50,000 이상)
    (49_990, 50_000, 49_950),      # 50,000 미만: 50원 (올리면 경계 50,000 — 그것도 칸 위)
    (199_950, 200_000, 199_900),   # 200,000 미만: 100원
    (234_567, 235_000, 234_500),   # 500,000 미만: 500원
    (712_345, 713_000, 712_000),   # 이상: 1,000원
])
def test_국내_호가단위_매수는_올림_매도는_내림(price, buy, sell):
    assert markets.round_to_tick("kr", price, "buy") == buy
    assert markets.round_to_tick("kr", price, "sell") == sell


def test_국내_호가단위_이미_칸_위면_그대로():
    for px in (1_999, 2_000, 4_995, 5_000, 19_990, 20_000, 49_950, 50_000, 199_900, 200_000, 499_500,
               500_000, 1_234_000):
        assert markets.round_to_tick("kr", px, "buy") == px
        assert markets.round_to_tick("kr", px, "sell") == px


def test_호가단위표_구간():
    assert [markets.kr_tick(p) for p in (1_999, 2_000, 4_999, 5_000, 19_999, 20_000, 49_999, 50_000,
                                         199_999, 200_000, 499_999, 500_000)] == \
        [1, 5, 5, 10, 10, 50, 50, 100, 100, 500, 500, 1_000]


def test_미국_호가단위_1센트():
    assert markets.round_to_tick("us", 123.451, "buy") == 123.46
    assert markets.round_to_tick("us", 123.459, "sell") == 123.45
    assert markets.round_to_tick("us", 1.10, "buy") == 1.10       # 부동소수점 오차로 한 칸 더 안 올림
    with pytest.raises(ValueError):
        markets.round_to_tick("kr", 1_000, "hold")
    with pytest.raises(ValueError):
        markets.round_to_tick("kr", float("nan"), "buy")


# ---------------- markets: 금액 표기·값 ----------------

def test_money_통화별_표기():
    assert markets.money("kr", 1_234_567) == "+1,234,567원"
    assert markets.money("kr", -56_000.4) == "-56,000원"
    assert markets.money("kr", 10_000_000, sign=False) == "10,000,000원"
    assert markets.money("us", 1_234.56, sign=False) == "$1,234.56"
    assert markets.money("us", -5) == "-$5.00"
    assert markets.money("kr", float("nan")) == "계산 불가"
    assert "$" not in markets.money("kr", 1) and "원" not in markets.money("us", 1)


def test_시장_값():
    kr, us = markets.get_market("kr"), markets.get_market("US")
    assert (kr.currency, kr.fee_rate, kr.sell_tax_rate, kr.slippage) == ("KRW", 0.00015, 0.0020, 0.0005)
    assert (kr.benchmark, kr.tz, kr.close_cutoff, kr.total_cash) == ("KS200", "Asia/Seoul", "16:00", 10_000_000)
    assert markets.BENCH_NAMES == {"us": "SPY", "kr": "KOSPI 200(가격지수)"}
    assert (us.currency, us.fee_rate, us.sell_tax_rate, us.benchmark, us.close_cutoff) == \
        ("USD", 0.001, 0.0, "SPY", "16:15")
    with pytest.raises(ValueError):
        markets.get_market("jp")
    with pytest.raises(Exception):
        kr.fee_rate = 0.1          # frozen — 실수로 바꿀 수 없음


def test_KR_UNIVERSE_는_6자리_코드_약_30개_중복_없음():
    codes = list(markets.KR_UNIVERSE.values())
    assert 25 <= len(codes) <= 35
    assert len(set(codes)) == len(codes)
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert markets.KR_UNIVERSE["삼성전자"] == "005930"
    assert all(markets.code_ok("kr", c) for c in main.KR_STOCKS.values())
    assert not markets.code_ok("kr", "AAPL") and markets.code_ok("us", "AAPL")


# ---------------- 확정 봉 (K-D9) ----------------

def _bars(last="2026-11-04"):
    idx = pd.bdate_range(end=last, periods=4)
    return pd.DataFrame({"Open": [1.0, 2, 3, 4], "Close": [1.0, 2, 3, 4], "Volume": [1.0] * 4}, index=idx)


def test_국내_확정_봉은_한국시간_16시_기준():
    df = _bars("2026-11-04")
    before = main.confirmed_bars(df, now=datetime(2026, 11, 4, 15, 59, tzinfo=KST), market="kr")
    after = main.confirmed_bars(df, now=datetime(2026, 11, 4, 16, 0, tzinfo=KST), market="kr")
    assert d(before.index[-1]) == "2026-11-03"
    assert d(after.index[-1]) == "2026-11-04"
    # 같은 순간을 뉴욕 시간으로 줘도 한국 시간으로 바꿔 판단 (뉴욕 11-04 02:30 = 한국 11-04 16:30)
    ny = datetime(2026, 11, 4, 2, 30, tzinfo=ET)
    assert d(main.confirmed_bars(df, now=ny, market="kr").index[-1]) == "2026-11-04"
    # 미국 기준이면 같은 순간에도 그대로(11-04 은 뉴욕에서 아직 장 전 → 버림)
    assert d(main.confirmed_bars(df, now=ny).index[-1]) == "2026-11-03"


def test_국내_확정_봉도_종가_NaN_행은_버린다():
    df = _bars()
    df.iloc[-1, df.columns.get_loc("Close")] = np.nan
    out = main.confirmed_bars(df, now=datetime(2026, 11, 10, 12, tzinfo=KST), market="kr")
    assert len(out) == 3 and out["Close"].notna().all()


def test_국내_load_prices_는_확정_봉_적용_미국_티커는_거부(monkeypatch):
    df = _bars("2026-11-04")
    fake = types.SimpleNamespace(DataReader=lambda code, start: df.copy())
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fake)
    out = main.load_prices("005930", "2026-01-01", now=datetime(2026, 11, 4, 10, tzinfo=KST), market="kr")
    assert d(out.index[-1]) == "2026-11-03"
    with pytest.raises(ValueError):
        main.load_prices("AAPL", "2026-01-01", market="kr")      # 달러 종목이 원화 지갑에 섞이지 않게


# ---------------- 비용·통화 (K-D8) ----------------

def test_국내_지갑_비용과_통화():
    w = main.make_wallet("테스트", "kr")
    assert (w.currency, w.fee_rate, w.sell_tax_rate, w.slippage) == ("KRW", 0.00015, 0.0020, 0.0005)
    w.deposit(10_000_000, "2026-11-02")
    assert w.buy("005930", 70_000, 100, "2026-11-02")
    assert w.sell("005930", 70_000, 100, "2026-11-03")
    notional = 70_000 * 100
    pct = (10_000_000 - w.cash) / notional * 100
    # 기대 왕복 비용 ≈ 슬리피지 0.05%×2 + 수수료 0.015%×2 + 매도세 0.20% ≈ 0.33%
    assert 0.32 < pct < 0.34, pct
    assert all(e["통화"] == "KRW" for e in w.log)
    # 미국 지갑 기본값은 그대로
    u = main.make_wallet("미국")
    assert (u.currency, u.fee_rate, u.sell_tax_rate) == ("USD", 0.001, 0.0)


def test_국내_백테스트_상한_안에서만_사고_로그는_전부_KRW():
    from marathoner_brain import MarathonerBrain
    from sprinter_brain import SprinterBrain
    from pioneer_brain import PioneerBrain
    from risk_guard import CircuitBreaker
    cfg = main.market_config("kr")
    assert cfg["총_가상자금"] == 10_000_000 and cfg["벤치마크"] == "KS200"
    for seed, base in ((1, 70_000), (2, 400_000)):
        df = synth(seed, start="2023-01-01", base=base)
        for name, cls in (("마라토너", MarathonerBrain), ("스프린터", SprinterBrain), ("파이오니어", PioneerBrain)):
            cash = cfg["총_가상자금"] * cfg["배분비율"][name]
            cap = cfg["종목상한"][name]
            r = main.run_one_trainer(name, cls(), df, cash, cap, "005930", CircuitBreaker(0.10, 0.07), mk="kr")
            assert all(e["통화"] == "KRW" for e in r["log"])
            for e in r["log"]:
                if e["종류"] == "매수":
                    assert e["금액"] <= cash * cap + 1e-6
                if e["종류"] == "보류":
                    assert "원" in e["사유"] and "$" not in e["사유"]
            assert r["profit"] == r["profit"]


def test_국내_buy_and_hold_는_매도세까지_뺀다():
    df = synth(3, start="2026-01-01", end="2026-06-30")
    kr = markets.get_market("kr")
    bh = main._buy_and_hold(df, 1_000_000, kr)
    import metrics
    raw = metrics.buy_and_hold(df, 1_000_000, fee_rate=kr.fee_rate, slippage=kr.slippage)
    tax = raw["shares"] * float(df["Close"].iloc[-1]) * (1 - kr.slippage) * kr.sell_tax_rate
    assert bh["profit"] == pytest.approx(raw["profit"] - tax)


def test_국내_compare_줄은_원과_KOSPI_200():
    df = synth(4, start="2026-10-01", end="2026-10-20")
    bench = synth(8, start="2026-10-01", end="2026-10-20", base=40_000)
    days = [d(x) for x in df.index]
    line = main.compare("마라토너", 12_345.0, df, 1_800_000, bench, days[0], days[-1], mk="kr")
    assert "KOSPI 200" in line and "원" in line and "$" not in line and "SPY" not in line
    assert "KODEX" not in line
    assert "nan" not in line.lower() and "계산 불가" not in line
    first = main.compare("마라토너", 0.0, df, 1_800_000, bench, days[0], days[0], mk="kr")
    assert "다음 확정 봉부터" in first and "$" not in first


# ---------------- 가짜 국내 시장 (team·live·main) ----------------

@pytest.fixture
def kr_market(monkeypatch, tmp_path):
    """가짜 국내 시장: cut[0] 날짜까지의 데이터만 '확정'된 것처럼. 국내 코드만 받는다.
    예외 하나: 벤치마크 KS200 은 allow_index=True(=main.load_benchmark 경로)로 올 때만 받는다."""
    full = synth(5)
    bench = synth(9, base=40_000)
    cut = [full.index[-2]]
    seen = []

    def fake_load(code, start, now=None, market="us", allow_index=False):
        seen.append((code, market))
        assert market == "kr", "국내 실행에서 미국 시장으로 시세를 받음"
        if code == "KS200":
            assert allow_index, "KS200 은 벤치마크 경로(allow_index=True)로만 받아야 함"
        else:
            assert markets.code_ok("kr", code) and not allow_index, code
        src = bench if code == "KS200" else full
        return src.loc[start:cut[0]]

    monkeypatch.setattr(main, "load_prices", fake_load)
    monkeypatch.setattr(live, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(team, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(main, "KR_STOCKS", {"삼성전자": "005930"})
    monkeypatch.setattr(main, "RESULTS_DIR", tmp_path / "results")
    return {"full": full, "cut": cut, "dir": tmp_path / "state", "seen": seen}


def _cands(days):
    return [{"code": c, "price": 70_000.0, "rsi": 30.0, "reason": "신호", "date": days[-2]}
            for c in ("005930", "000660")]


def test_team_국내_상태_파일_경로와_체결_통화(kr_market, monkeypatch, capsys):
    """국내 team: state/kr/ 에 원화 상태, 다음 봉 시가 체결, 같은 봉 재실행은 멱등."""
    full, cut, sd = kr_market["full"], kr_market["cut"], kr_market["dir"]
    days = [d(x) for x in full.index]
    calls = []

    def fake_scan(n, market="us"):
        calls.append(market)
        return {"마라토너": _cands(days), "스프린터": [], "파이오니어": []}, 2

    monkeypatch.setattr(screener, "scan", fake_scan)
    monkeypatch.setattr(analyst, "analyze", lambda *a, **k: None)     # 팀장 부재 → 규칙 폴백
    team.run(3, market="kr")
    assert calls == ["kr"]
    f = sd / "kr" / "team_마라토너.json"
    assert f.exists() and not (sd / "team_마라토너.json").exists()    # 미국 경로는 안 건드림
    st = json.loads(f.read_text(encoding="utf-8"))
    assert st["schema"] == main.STATE_SCHEMA_KR and st["wallet"]["currency"] == "KRW"
    assert st["wallet"]["cash"] == 10_000_000 * 0.6
    assert st["wallet"]["fee_rate"] == 0.00015 and st["wallet"]["sell_tax_rate"] == 0.0020
    assert sorted(o["code"] for o in st["pending"]) == ["000660", "005930"]

    cut[0] = full.index[-1]                                              # 다음 거래일 봉 확정
    monkeypatch.setattr(screener, "scan", lambda n, market="us": ({t: [] for t in team.BRAINS}, 0))
    team.run(3, market="kr")
    st = json.loads(f.read_text(encoding="utf-8"))
    buys = [e for e in st["wallet"]["log"] if e["종류"] == "매수"]
    assert buys and all(e["시각"] == days[-1] and e["통화"] == "KRW" for e in buys)
    assert all(e["금액"] <= 10_000_000 * 0.6 * 0.3 + 1e-6 for e in buys)

    # 같은 봉으로 한 번 더 → 마라토너는 '이미 처리됨', 파일은 바이트까지 그대로(멱등)
    snap = f.read_bytes()
    team.run(3, market="kr")
    assert f.read_bytes() == snap
    out = capsys.readouterr().out
    assert "이미 처리됨" in out
    assert "nan" not in out.lower() and "$" not in out and "SPY" not in out
    assert "KOSPI 200" in out and "원" in out and "KODEX" not in out
    assert all(m == "kr" for _, m in kr_market["seen"])
    assert ("KS200", "kr") in kr_market["seen"]                       # 기준 날짜·비교는 KS200


def test_team_국내_세_트레이너_다_처리됐으면_스캔_생략(kr_market, monkeypatch, capsys):
    bar = d(kr_market["cut"][0])
    for t in team.BRAINS:
        st = team._new_state(t, 1_000_000, bar, "kr")
        st["last_date"] = bar; st["prev_value"] = 1_000_000
        team._save(t, st, "kr")
    monkeypatch.setattr(screener, "scan", lambda *a, **k: pytest.fail("이미 처리됐는데 스캔함"))
    team.run(3, market="kr")
    out = capsys.readouterr().out
    assert "스캔 생략" in out and "$" not in out and "nan" not in out.lower()


def test_team_국내에_달러_상태_파일이_있으면_보관하고_새로_시작(kr_market):
    sd = kr_market["dir"] / "kr"; sd.mkdir(parents=True)
    usd_state = team._new_state("마라토너", 6_000, "2026-11-02")            # 미국(달러) 상태
    data = {k: v for k, v in usd_state.items() if k != "wallet"}
    from dataclasses import asdict
    data["wallet"] = asdict(usd_state["wallet"]); data["schema"] = main.STATE_SCHEMA_KR  # 형식은 맞지만 달러
    (sd / "team_마라토너.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert team._load("마라토너", "kr") is None
    assert list(sd.glob("team_마라토너.old-*.json"))
    # 저장 단계에서도 달러 지갑을 국내 경로에 쓰지 않는다
    with pytest.raises(ValueError):
        team._save("마라토너", usd_state, "kr")


def test_경로는_시장별():
    assert team._path("스프린터") == team.STATE_DIR / "team_스프린터.json"
    assert team._path("스프린터", "kr") == team.STATE_DIR / "kr" / "team_스프린터.json"
    assert live._state_file("삼성전자", "스프린터", "kr") == live.STATE_DIR / "kr" / "삼성전자_스프린터.json"
    assert live._state_file("가짜", "스프린터") == live.STATE_DIR / "가짜_스프린터.json"


def test_live_국내_두번_실행_멱등_원화(kr_market, capsys):
    live.run("kr")
    live.run("kr")
    out = capsys.readouterr().out
    sd = kr_market["dir"] / "kr"
    files = sorted(p.name for p in sd.glob("*.json"))
    assert files == ["삼성전자_마라토너.json", "삼성전자_스프린터.json", "삼성전자_파이오니어.json"]
    assert not list(kr_market["dir"].glob("*.json"))                   # 미국 폴더엔 없음
    for f in sd.glob("*.json"):
        st = json.loads(f.read_text(encoding="utf-8"))
        assert st["wallet"]["currency"] == "KRW" and st["schema"] == main.STATE_SCHEMA_KR
    assert out.count("새 확정 봉 없음") == 3
    assert "nan" not in out.lower() and "$" not in out and "KOSPI 200" in out and "원" in out


def test_main_국내_출력은_원과_KOSPI_200(kr_market, capsys):
    main.main("kr")
    out = capsys.readouterr().out
    assert "nan" not in out.lower() and "$" not in out and "SPY" not in out
    assert "KOSPI 200" in out and "원" in out and "진짜 돈 0원" in out and "KODEX" not in out


def test_스크리너_국내는_KR_UNIVERSE_만_KRX_목록_조회_안_함(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("KRX/S&P 전체 목록 조회 금지")
    monkeypatch.setitem(sys.modules, "FinanceDataReader", types.SimpleNamespace(StockListing=boom))
    codes = screener.universe(40, "kr")
    assert codes == list(markets.KR_UNIVERSE.values())
    assert screener.universe(5, "kr") == list(markets.KR_UNIVERSE.values())[:5]
    seen = []
    df = synth(2, start="2024-06-01")
    monkeypatch.setattr(main, "load_prices", lambda code, start, now=None, market="us":
                        (seen.append((code, market)), df)[1])
    found, used = screener.scan(3, market="kr")
    assert used == 3 and [c for c, _ in seen] == list(markets.KR_UNIVERSE.values())[:3]
    assert all(m == "kr" for _, m in seen)
    assert set(found) == set(screener.BRAINS)


def test_parse_market_기본은_us():
    assert main.parse_market([]) == ("us", [])
    assert main.parse_market(["40", "--market", "kr"]) == ("kr", ["40"])
    assert main.parse_market(["check"]) == ("us", ["check"])
    with pytest.raises(SystemExit):
        main.parse_market(["--market", "jp"])
