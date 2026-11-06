"""
h1_data.py - H1 시세 받기 층 (설계 docs/h1-forward-design.md §2.2 ⑥-i, 단계 4 검토 F-9·F-1)
------------------------------------------------------------------
무엇을 하나 (주식 초보용 설명)
- 인터넷에서 시세를 받아 "다 끝난(확정된) 봉"만 남긴 표로 바꾸는 일만 한다. 장부·판정은 모른다.
    fetch(market, code, now)       종목 시세 → Fetched(확정 시세, 국내 거래정지 날짜) 또는 None
    load_idle(market, now)         대기 자산(SPY / KS200) 확정 시세 또는 None
    fetched_from_raw(market, raw, now)  원본 표 → Fetched (fetch 와 재현·시험의 가짜 자료가 같은 단계를 거치게)
    universe(market, n)            종목군 목록(미국 screener.universe(n), 국내 KR_UNIVERSE) — start 때 한 번
    DataSource / live_source        자료 받는 곳 묶음(운영 = live_source, 재현·시험 = 가짜)
- 왜 따로 두나: 판정 창 동안 코드는 바꾸지 않는다(사전 등록 ⑥). 다만 시세 제공처가 깨지면 받기 코드는 고쳐야 할 수 있다.
  그때 고칠 수 있는 곳은 **이 파일과 라이브러리 버전뿐**이다(⑥-i). 이 파일 밖을 고치면 규칙 변경(⑤-c 재시작)이다.
  고친 뒤에도 자료 받기 골든(tests/golden_data/ — 거래정지 행·거래량 칸 이름 둘·종가 NaN·KS200 22:30·미국 16:15·장중
  미완성 봉)의 결과가 바이트까지 같아야 하고(h1.data_golden_digest), 재현 장부 내용 지문도 같아야 한다.
- 시계(지금 몇 시인지)는 늦은 봉 판단에 쓰이므로 이 파일에 두지 않는다: live_source 는 h1.py 가 넘긴 시계를 그대로 쓴다.
- 확정 봉 규칙 자체(main.confirmed_bars: 종가 NaN 버림, 국내 거래량 0 버림, 확정 시각 전 오늘 봉 버림)는 운영과 같이 쓰는
  main.py 에 있고 여기서 감싸기만 한다(main.py 는 고치지 않음).

import 관계: h1_data → main·markets·screener·team(START). h1 을 import 하지 않는다(h1 이 이 파일을 import 함).
"""
from __future__ import annotations

from dataclasses import dataclass

import main
import markets
import screener
import team


def _say(*args):
    """화면(launchd 로그) 출력. 출력이 막혀도 멈추지 않는다(h1._say 와 같음)."""
    try:
        print(*args, flush=True)
    except (OSError, ValueError):
        pass


def _mkey(market) -> str:
    return main.mkt(market).key


@dataclass
class Fetched:
    """시세 받기 결과. df = main.confirmed_bars 를 거친 확정 시세,
    halt_dates = 국내 원본에서 거래량 0 인 날짜(거래정지일). 미국은 빈 집합."""
    df: object
    halt_dates: frozenset


def normalize_columns(raw):
    """거래량 칸 이름 정리('거래량' → 'Volume'). main.load_prices 와 같은 단계."""
    if raw is not None and "Volume" not in raw.columns and "거래량" in raw.columns:
        return raw.rename(columns={"거래량": "Volume"})
    return raw


def fetched_from_raw(market, raw, now):
    """원본 시세(fdr.DataReader 결과 모양) → Fetched (fetch 와 재현·시험의 가짜 자료가 같은 단계를 거치게 따로 둠).
    단계는 main.load_prices 와 같다: 거래량 칸 이름 정리('거래량' → 'Volume') → main.confirmed_bars(now, 시장).
    halt_dates = 국내 원본에서 거래량(Volume)이 0 인 날짜(그 행은 confirmed_bars 가 버림 = 거래정지일). 미국은 빈 집합.
    원본이 비었거나 확정 봉이 하나도 없으면 None."""
    mk = _mkey(market)
    if raw is None or len(raw) == 0:
        return None
    df = normalize_columns(raw)
    halts = frozenset()
    if mk == "kr" and "Volume" in df.columns:
        halts = frozenset(d.date().isoformat() for d in df.index[df["Volume"] == 0])
    out = main.confirmed_bars(df, now, mk)
    if out is None or len(out) == 0:
        return None
    return Fetched(out, halts)


def fetch(market, code, now):
    """종목 시세 받기(설계 §3.3): 원본 fdr.DataReader(code, team.START) → 이름 정리 → main.confirmed_bars →
    Fetched(확정 시세, 국내 거래량 0 날짜). 받기 실패·빈 자료면 None(부르는 쪽이 D2·W4·W5 로 판단)."""
    mk = _mkey(market)
    if mk == "kr" and not markets.code_ok("kr", code):
        raise ValueError(f"'{code}' 는 국내 6자리 종목코드가 아니에요 (국내 시장에는 국내 종목만).")
    try:
        import FinanceDataReader as fdr
        raw = fdr.DataReader(code, team.START)
    except (Exception, SystemExit) as e:
        _say(f"    ({code} 시세 받기 실패: {type(e).__name__})")
        return None
    return fetched_from_raw(mk, raw, now)


def load_idle(market, now):
    """대기 자산(SPY/KS200) 확정 시세 — main.load_benchmark 와 같은 길(국내는 allow_index 문, KS200 22:30 KST 규칙).
    다른 점은 now(이번 실행의 시각)를 넘기는 것뿐. 실패하면 None (→ D1)."""
    m = markets.MARKETS[_mkey(market)]
    try:
        if m.key == "us":
            return main.load_prices(m.benchmark, team.START, now=now)
        return main.load_prices(m.benchmark, team.START, now=now, market=m.key, allow_index=True)
    except (Exception, SystemExit) as e:
        _say(f"    (대기 자산 {m.benchmark} 시세 받기 실패: {type(e).__name__})")
        return None


def universe(market, n):
    """종목군 목록: 미국 screener.universe(n)(S&P500 고정 seed 섞기), 국내 markets.KR_UNIVERSE 전부."""
    if _mkey(market) == "us":
        return list(screener.universe(n))
    return list(markets.KR_UNIVERSE.values())


def universe_names(market) -> dict:
    """종목 코드 → 이름(H1 팀장 프롬프트 표시용, 설계 Q4 2026-11-06). start 때 종목군과 함께 한 번 받아 종목군 파일에 적는다.
    미국: FinanceDataReader S&P500 표의 Symbol·Name(screener.universe 가 읽는 것과 같은 표), 국내: markets.KR_UNIVERSE 를 뒤집은 것.
    이름은 표시용이라 받지 못해도 멈추지 않는다 → 빈 dict(그때 프롬프트는 코드만)."""
    if _mkey(market) == "kr":
        return {code: name for name, code in markets.KR_UNIVERSE.items()}
    try:
        import FinanceDataReader as fdr
        t = fdr.StockListing("S&P500")
        return {s: n for s, n in zip(t["Symbol"].tolist(), t["Name"].tolist())
                if isinstance(s, str) and isinstance(n, str) and n.strip()}
    except Exception as e:                       # noqa: BLE001 — 표시용 정보라 실패해도 start 는 이어 간다
        _say(f"    (종목 이름 목록 받기 실패: {type(e).__name__} → 팀장 프롬프트는 코드만)")
        return {}


@dataclass
class DataSource:
    """자료 받는 곳 (운영 = live_source, 재현·시험 = 가짜). 모든 시각은 시간대 있는 datetime.
    benchmark(now) → 대기 자산 확정 시세 DataFrame 또는 None
    fetch(code, now) → Fetched 또는 None
    universe() → 종목 목록 (start 때 종목군 파일이 없을 때만 한 번 부름)
    now() → 지금 시각
    names() → {코드: 이름} (start 때 종목군과 함께 한 번, 없으면 None = 이름 없음. 설계 Q4)"""
    benchmark: object
    fetch: object
    universe: object
    now: object
    names: object = None


def live_source(market, n_universe, clock) -> DataSource:
    """운영 자료: load_idle·fetch·universe(n_universe), 시계는 부르는 쪽(h1.py)이 넘긴 것."""
    mk = _mkey(market)
    return DataSource(benchmark=lambda now: load_idle(mk, now), fetch=lambda code, now: fetch(mk, code, now),
                      universe=lambda: universe(mk, n_universe), now=clock, names=lambda: universe_names(mk))
