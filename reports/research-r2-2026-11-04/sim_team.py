"""
R2 팀 단위 시뮬레이터 (research-r2-2026-11-04)
==============================================
사전 등록(`research-oss-2026-11-04` 브랜치 REPORT.md §7)과 보완(STAGE0.md §6 A1~A9)을 그대로 코드로 옮긴 것.
저장소 코드(.py)는 한 줄도 고치지 않고 import 만 한다.

  - 판단: marathoner_brain / sprinter_brain / pioneer_brain 의 add_indicators()·decide() 를 그대로 호출
  - 돈:   paper_wallet.PaperWallet(buy/sell/skip/value) + shares_within_cap  (비용 계산을 새로 만들지 않음)
  - 팀:   team.py 의 run_trainer 순서를 따른다
          ① 어제 낸 주문을 오늘(그 종목의 다음 봉) 시가로 체결  ② 보유 종목 매도 판단
          ③ 서킷 브레이커  ④ 신규 후보(MAX_POSITIONS=5, 매수 대기 주문 포함) → 다음 시가 주문
  - 체결가: main.open_price (시가). 국내는 Volume=0 행을 미리 빼므로 시가가 0인 봉이 없다(A5, S0-2 재현 안 함)
  - 서킷: risk_guard.CircuitBreaker 그대로 (H3 '지금 서킷' / H3 단계적 서킷의 하루 -7% 규칙)
  - 팀장 LLM: 끔. analyst.apply(후보, None) → 규칙 그대로, 확신도 None → team.keep_candidate 통과

진입점: run(Config(...)) -> dict
  Config.market : "us"(R0 20종목) | "us_pit"(2014말 시총 상위 20, 생존편향 확인) | "kr"(KR_UNIVERSE 32종목)
  Config.period : REGIMES 의 이름(예 "2018 조정") 또는 ("YYYY-MM-DD", "YYYY-MM-DD")
  Config.arm    : "A0"  세 트레이너, 쉬는 돈 = 현금(이자)
                  "A1"  세 트레이너, 쉬는 돈 = 지수(SPY/KS200) 소수 단위            (= H1)
                  "A1T" A1 + 월말 10개월선 필터로 대기 자산(지수/현금) 선택          (= H2)
                  "A2"  지수 70%(첫 시가에 사서 보유) + 30% 를 세 트레이너가 A0 방식으로
                  "G11" 참고선: 지수 10개월선 추세추종(트레이너 없음)
                  "IDX" 점검용: 지수 소수 단위 B&H(트레이너 없음)
  Config.cb     : "none" | "current"(risk_guard 그대로, 영구 정지) | "staged"(H3)   — A0·A1 에서만
  Config.realloc: True 면 H4(느린 성과 기반 재배분) — A1 에서만

속도를 위한 처리(결과는 같음, R0 sim.py 와 같은 방식):
  - 지표는 종목·트레이너마다 전체 기간에 한 번만 계산한다(셋 다 과거만 보는 지표).
  - decide() 에는 최근 80봉(WINDOW)만 넘긴다(R0 check_sim.py 가 원래 방식과 같음을 확인).
  - '보유 없을 때'의 판단은 (트레이너, 종목, 봉)마다 한 번만 계산해 둔다(어느 비교 대상이든 같은 값).
  - '보유 중'의 판단은 (트레이너, 종목, 진입 봉)이 같으면 같다(decide 는 buy_price·days_held 만 본다).
    그래서 진입 봉마다 '첫 매도 신호 봉'을 봉 하나씩 차례로 계산해 기억한다(미래를 미리 보지 않음).
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                 # 저장소 루트 (저장소 자체 모듈만 import 하려고 경로에 넣는다)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main          # noqa: E402  open_price, make_wallet, fmt, px_txt, CONFIG
import markets       # noqa: E402  MARKETS(비용), KR_UNIVERSE(국내 후보 순서)
import metrics       # noqa: E402  buy_and_hold, max_drawdown
import team          # noqa: E402  MAX_POSITIONS, BRAINS, keep_candidate, to_conviction
import analyst       # noqa: E402  apply(후보, None) = 팀장 부재 폴백 (analyze 는 부르지 않음 = LLM 끔)
from paper_wallet import PaperWallet, Holding, shares_within_cap   # noqa: E402
from risk_guard import CircuitBreaker                              # noqa: E402

DATA = HERE / "data"

# ---------------------------------------------------------------- 사전 등록 숫자 (§7, A1~A9)
REGIMES = {                                   # R0 run_regimes.py 와 같은 날짜
    "2015-17 상승": ("2015-01-01", "2017-12-31"),
    "2018 조정": ("2018-01-01", "2018-12-31"),
    "2020 급락·회복": ("2020-01-01", "2020-12-31"),
    "2022 하락": ("2022-01-01", "2022-12-31"),
    "2023-26 상승": ("2023-01-01", "2026-12-31"),
    "전체 2015-26": ("2015-01-01", "2026-12-31"),
}
WINDOW = 80          # decide 에 넘기는 최근 봉 수 (R0 와 같음)
WARMUP = 60          # 국면 시작은 달력의 60번째 봉 이후 (R0 idx_range 와 같음)
MIN_BARS = 60        # A7: 종목 자기 봉이 60개 쌓여야 매수 후보
TOTALS = {"us": 100_000, "us_pit": 100_000, "kr": 100_000_000}   # §7.0, §7.5
RATIOS = dict(main.CONFIG["배분비율"])     # 60/30/10
CAPS = dict(main.CONFIG["종목상한"])       # 30/20/15%
CB_CUM = main.CONFIG["서킷브레이커"]["누적한도"]   # 0.10
CB_DAY = main.CONFIG["서킷브레이커"]["일일한도"]   # 0.07
A2_INDEX_SHARE = 0.70
TREND_MONTHS = 10                          # H2·G11: 월말 종가 10개(그 달 포함) 평균
H3_HALF_DD, H3_STOP_DD, H3_PAUSE_DAYS = -0.10, -0.20, 20
H4_MIN_MONTHS, H4_SLOPE, H4_LO, H4_HI = 20, 0.25, 0.25, 2.0      # ai-hedge-fund 기본값 그대로
SWEEP_MIN = 1.0      # 남은 현금이 1(달러/원) 이상이면 지수로 옮긴다 → 남는 돈은 1 미만 (H1 "남는 금액 $1 미만")
SEED = 20261104

# STAGE0 §1.2: 코스피 주식 매도세(증권거래세+농특세) — (시행일, 합계). 체결일(양도일) 기준(A4)
KR_SELL_TAX = (
    ("0000-01-01", 0.0030),
    ("2019-06-03", 0.0025),
    ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020),
    ("2024-01-01", 0.0018),
    ("2025-01-01", 0.0015),
    ("2026-01-01", 0.0020),
)

BUY, SELL, HOLD, UNK = 1, -1, 0, -2
ACT = {"매수": BUY, "매도": SELL, "관망": HOLD}
TRAINERS = list(team.BRAINS)               # ["마라토너", "스프린터", "파이오니어"]


def kr_sell_tax(date: str) -> float:
    """국내 주식 매도세율(체결일 'YYYY-MM-DD' 기준, STAGE0 §1.2). ETF·지수 매도는 0 (§1.1, A3)."""
    rate = KR_SELL_TAX[0][1]
    for since, r in KR_SELL_TAX:
        if date >= since:
            rate = r
    return rate


# ================================================================ 데이터
def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[df["Close"].notna()]          # D1: 종가 빈 행은 버린다 (R0 sim.load 와 같음)


def drop_zero_volume(df: pd.DataFrame) -> pd.DataFrame:
    """A5: 국내 거래정지 행(Volume=0)을 시뮬레이션 전에 뺀다. 그날 그 종목은 신호도 체결도 없다."""
    return df[df["Volume"] != 0]


def _rate_series(path: Path) -> pd.Series:
    r = pd.read_csv(path, parse_dates=["date"])
    return pd.Series(r["rate_pct"].to_numpy(float), index=pd.DatetimeIndex(r["date"])).sort_index()


def _asof(series: pd.Series, keys) -> np.ndarray:
    """keys 각각에 대해 '그 날짜 이하의 마지막 값'. 없으면 NaN."""
    keys = pd.DatetimeIndex(keys)
    pos = series.index.searchsorted(keys, side="right") - 1      # pandas 가 날짜 단위(us/ns) 차이를 맞춰 줌
    vals = series.to_numpy(float)
    out = np.where(pos >= 0, vals[np.clip(pos, 0, None)], np.nan)
    return out


def rate_for_days(cal: pd.DatetimeIndex, series: pd.Series, rule: str) -> np.ndarray:
    """거래일 t 의 이자에 쓸 연 % 값.
    rule="prev_day"  (A1, 미국 DTB3): 전 거래일(t-1) 날짜 이하의 마지막 값 (그날 값이 없으면 직전 값)
    rule="prev_month"(A2, 국내 월별): t 가 m월이면 m-1월 값, 없으면 그 이전 마지막 값(이월)"""
    if rule == "prev_day":
        out = _asof(series, cal[:-1])                    # t 번째 거래일 ← (t-1) 번째 거래일 날짜 이하 마지막 값
        return np.concatenate(([np.nan], out))           # 달력 첫날은 전 거래일이 없음 (국면은 60번째 봉부터라 안 씀)
    if rule == "prev_month":
        first_of_prev = (cal.to_period("M") - 1).to_timestamp()        # m-1월 1일
        return _asof(series, first_of_prev.values)
    raise ValueError(rule)


def _universe(key: str) -> list[str]:
    if key == "us":
        info = json.loads((DATA / "us" / "universe.json").read_text(encoding="utf-8"))
        return [c for c in info["종목"] if c != "SPY"]                   # R0 universe.json 순서(시총 순위)
    if key == "us_pit":
        top = pd.read_csv(DATA / "us_pit" / "top20_2014-12-31.csv").sort_values("rank")
        info = json.loads((DATA / "us_pit" / "prices" / "universe.json").read_text(encoding="utf-8"))["종목"]
        top = top[(top["rank"] >= 1) & (top["rank"] <= 20)]           # A9: 1~20위만
        return [info[t]["지금_티커"] for t in top["ticker_2014"]]      # 저장된 티커(BRK-B, META)
    if key == "kr":
        return list(markets.KR_UNIVERSE.values())                       # A8: KR_UNIVERSE 순서
    raise ValueError(f"모르는 시장 {key!r}")


def load_frames(key: str, data_end: str | None = None):
    """(지수 df, {종목: df}, 금리 Series, 금리 규칙, 원래 거래량0 날짜) 를 읽는다. data_end 이후는 잘라낸다."""
    codes = _universe(key)
    zero_vol = {}
    if key in ("us", "us_pit"):
        idx = _read(DATA / "us" / "SPY.csv.gz")
        folder = DATA / "us" if key == "us" else DATA / "us_pit" / "prices"
        frames = {c: _read(folder / f"{c}.csv.gz") for c in codes}
        rates, rule = _rate_series(DATA / "rates" / "us_tbill.csv"), "prev_day"
    else:
        idx = _read(DATA / "kr" / "KS200.csv.gz")      # A3: KOSPI 200 가격지수 (069500 시세는 쓰지 않음)
        frames = {}
        for c in codes:
            raw = _read(DATA / "kr" / f"{c}.csv.gz")
            zero_vol[c] = {d.date().isoformat() for d in raw.index[raw["Volume"] == 0]}
            frames[c] = drop_zero_volume(raw)
        rates, rule = _rate_series(DATA / "rates" / "kr_shortrate.csv"), "prev_month"
    if data_end is not None:
        end = pd.Timestamp(data_end)
        idx = idx[idx.index <= end]
        frames = {c: f[f.index <= end] for c, f in frames.items()}
        rates = rates[rates.index <= end]
        frames = {c: f for c, f in frames.items() if len(f)}
    return idx, frames, rates, rule, zero_vol


# ================================================================ 시장 데이터 + 판단 캐시
class Stock:
    """종목 하나: 시세 배열, 달력↔자기 봉 위치, 트레이너별 지표·판단 캐시."""

    def __init__(self, code: str, df: pd.DataFrame, md: "MarketData"):
        self.code = code
        self.df = df
        self.dates = [d.date().isoformat() for d in df.index]
        self.open = df["Open"].to_numpy(float)
        self.close = df["Close"].to_numpy(float)
        pos = md.cal.get_indexer(df.index)
        if (pos < 0).any():
            raise ValueError(f"{code}: 지수 달력에 없는 날짜가 있음 ({df.index[pos < 0][:3]})")
        self.cal_of_own = pos                                     # 자기 봉 j → 달력 위치
        self.own_at_cal = np.full(len(md.cal), -1, dtype=np.int64)
        self.own_at_cal[pos] = np.arange(len(df))                 # 달력 t → 자기 봉 j (없으면 -1)
        self.last_own_at_cal = np.maximum.accumulate(self.own_at_cal)   # t 까지의 마지막 자기 봉
        self.ind = {t: md.brains[t]().add_indicators(df) for t in md.brains}
        self.flat = {t: np.full(len(df), UNK, dtype=np.int8) for t in md.brains}
        self.flat_reason = {t: {} for t in md.brains}


class MarketData:
    def __init__(self, key: str, idx_df: pd.DataFrame, frames: dict, rates: pd.Series, rate_rule: str,
                 brains: dict | None = None, zero_volume: dict | None = None, idx_code: str | None = None):
        self.key = key
        self.mk = markets.MARKETS["us" if key.startswith("us") else "kr"]
        self.fee, self.slip = self.mk.fee_rate, self.mk.slippage      # 주식: 수수료·슬리피지 (D8 / K-D8)
        self.idx_fee, self.idx_slip = self.mk.fee_rate, self.mk.slippage   # 지수 다리: 같은 수수료·슬리피지, 매도세 0
        self.idx_code = idx_code or ("SPY" if key.startswith("us") else "KS200")
        self.cal = idx_df.index
        self.dstr = [d.date().isoformat() for d in self.cal]
        self.idx_open = idx_df["Open"].to_numpy(float)
        self.idx_close = idx_df["Close"].to_numpy(float)
        self.brains = dict(brains or team.BRAINS)
        self.brain_obj = {t: cls() for t, cls in self.brains.items()}
        self.stocks = [Stock(c, f, self) for c, f in frames.items()]
        self.by_code = {s.code: s for s in self.stocks}
        if self.idx_code in self.by_code:
            raise ValueError("지수 코드가 종목 코드와 겹침")
        self.rate_pct = rate_for_days(self.cal, rates, rate_rule)
        self.rate_rule = rate_rule
        self.zero_volume = zero_volume or {}
        self.tax_at_cal = np.array([self.tax(d) for d in self.dstr])
        self._calendar_flags()
        self.exit_cache: dict = {}
        self.decide_calls = 0

    # --- 세금
    def tax(self, date: str) -> float:
        return kr_sell_tax(date) if self.mk.key == "kr" else self.mk.sell_tax_rate   # 미국 0 (D8)

    # --- 달력: 월말, 분기 첫날, 10개월선 상태
    def _calendar_flags(self):
        n = len(self.cal)
        months = self.cal.year.to_numpy() * 12 + self.cal.month.to_numpy()
        # 월말 = 다음 거래일이 다른 달인 날 (마지막 봉은 다음 날을 모르니 월말로 보지 않음)
        self.month_end = np.zeros(n, dtype=bool)
        self.month_end[:-1] = months[1:] != months[:-1]
        # 분기 첫 거래일 = 전 거래일과 달이 다르고 1·4·7·10월
        self.quarter_first = np.zeros(n, dtype=bool)
        self.quarter_first[1:] = (months[1:] != months[:-1]) & np.isin(self.cal.month.to_numpy()[1:], [1, 4, 7, 10])
        # H2·G11: 월말 종가 > 최근 10개 월말 종가(그 달 포함) 평균 → 다음 달 대기 자산 = 지수, 아니면 현금
        # trend_mode[t] = t 시가에 적용할 상태 (t-1 이전 마지막 월말의 신호). 월말이 10개 모이기 전은 지수(I3).
        self.trend_mode = np.empty(n, dtype=object)
        self.trend_defined = np.zeros(n, dtype=bool)
        me_closes = []
        cur, defined = "index", False
        for t in range(n):
            self.trend_mode[t] = cur
            self.trend_defined[t] = defined
            if self.month_end[t]:
                me_closes.append(self.idx_close[t])
                if len(me_closes) >= TREND_MONTHS:
                    avg = float(np.mean(me_closes[-TREND_MONTHS:]))
                    cur = "index" if self.idx_close[t] > avg else "cash"
                    defined = True

    # --- 판단 캐시
    def flat_action(self, tname: str, stock: Stock, j: int) -> int:
        """보유 없을 때 decide() 결과 (트레이너·종목·봉이 같으면 언제나 같음)."""
        a = stock.flat[tname][j]
        if a == UNK:
            w = stock.ind[tname].iloc[max(0, j - WINDOW + 1): j + 1]
            act, why = self.brain_obj[tname].decide(w, None)
            self.decide_calls += 1
            a = ACT[act]
            stock.flat[tname][j] = a
            if a == BUY:
                stock.flat_reason[tname][j] = why
        return int(a)

    def exit_check(self, tname: str, stock: Stock, e: int, j: int, buy_price: float):
        """봉 e 시가에 산 포지션을 봉 j 종가에서 판단했을 때 '매도'인지.
        decide 는 position 의 buy_price·days_held 만 보므로 (트레이너, 종목, e) 가 같으면 결과가 같다.
        봉 e 부터 j 까지 차례로 한 봉씩 판단하며, 첫 '매도'가 나온 봉을 기억한다(그 뒤는 계산 안 함)."""
        key = (tname, stock.code, e)
        ent = self.exit_cache.get(key)
        if ent is None:
            ent = self.exit_cache[key] = [e - 1, None, "", buy_price]
        if ent[3] != buy_price:
            raise AssertionError("같은 진입 봉인데 매수가가 다름")
        if ent[1] is None and ent[0] < j:
            brain, ind = self.brain_obj[tname], stock.ind[tname]
            for jj in range(ent[0] + 1, j + 1):
                w = ind.iloc[max(0, jj - WINDOW + 1): jj + 1]
                act, why = brain.decide(w, {"buy_price": buy_price, "days_held": jj - e, "shares": 1})
                self.decide_calls += 1
                ent[0] = jj
                if act == "매도":
                    ent[1], ent[2] = jj, why
                    break
        return ent[1] == j, ent[2]


_MARKET_CACHE: dict = {}


def get_market(key: str, data_end: str | None = None) -> MarketData:
    """시장 데이터(같은 프로세스 안에서는 한 번만 읽고 판단 캐시도 공유)."""
    k = (key, data_end)
    if k not in _MARKET_CACHE:
        idx, frames, rates, rule, zv = load_frames(key, data_end)
        _MARKET_CACHE[k] = MarketData(key, idx, frames, rates, rule, zero_volume=zv)
    return _MARKET_CACHE[k]


def period_range(md: MarketData, period) -> tuple[int, int]:
    """국면 → 달력 위치 [i0, i1]. 시작은 최소 60번째 봉(R0 idx_range 와 같음)."""
    s, e = REGIMES[period] if isinstance(period, str) else period
    i0 = int(md.cal.searchsorted(pd.Timestamp(s)))
    i1 = int(md.cal.searchsorted(pd.Timestamp(e), side="right")) - 1
    return max(i0, WARMUP), i1


# ================================================================ 설정
@dataclass
class Config:
    market: str = "us"
    period: object = "2018 조정"
    arm: str = "A0"                 # A0 | A1 | A1T | A2 | G11 | IDX
    cb: str = "none"                # none | current | staged   (H3: A0·A1 에서만)
    realloc: bool = False           # H4 (A1 에서만)
    interest: bool = True           # 쉬는 현금 이자 (A1·A2)
    total: float | None = None      # None = 시장 기본(미국 $100,000, 국내 ₩100,000,000)
    trainers: tuple | None = None   # 점검용: 일부 트레이너만
    ratios: dict | None = None      # 점검용: 배분비율 바꾸기
    caps: dict | None = None        # 점검용: 종목상한 바꾸기
    universe: tuple | None = None   # 점검용: 일부 종목만
    max_positions: int = team.MAX_POSITIONS
    cap_base: str = "start"         # "start"=team.py(시작 예산 × 상한) | "cash"=R0 sim(지금 현금 × 상한, 동등성 점검용)
    n_random: int = 0               # >0 이면 H1-4 무작위 시점 대조 (A1 에서)
    seed: int = SEED
    with_refs: bool = True          # 지수 B&H·동일비중 B&H·G11 참고선 같이 계산


ARMS = ("A0", "A1", "A1T", "A2", "G11", "IDX")


def _check_config(c: Config):
    if c.arm not in ARMS:
        raise ValueError(f"arm={c.arm!r}")
    if c.cb not in ("none", "current", "staged"):
        raise ValueError(f"cb={c.cb!r}")
    if c.cb != "none" and c.arm not in ("A0", "A1"):
        raise ValueError("H3 서킷 비교는 A0·A1 위에서만 (사전 등록 §7 H3)")
    if c.realloc and c.arm != "A1":
        raise ValueError("H4 재배분은 A1 위에서만 (사전 등록 §7 H4)")
    if c.cap_base not in ("start", "cash"):
        raise ValueError(c.cap_base)


# ================================================================ 지갑 하나(트레이너 슬리브)
class Sleeve:
    def __init__(self, name, brain, budget, cap, idle, wallet):
        self.name = name                # 표시 이름 ("마라토너", "지수70%" …)
        self.brain = brain              # 브레인 이름 (None = 트레이너 없음: 지수/현금만)
        self.start_cash = budget        # team.py st["start_cash"]
        self.cap = cap                  # 종목상한 비율
        self.cap_budget = budget        # shares_within_cap 의 budget (H4 재배분 뒤에만 바뀜, I5)
        self.idle = idle                # "cash" | "index" | "trend"
        self.wallet: PaperWallet = wallet
        self.positions: dict = {}       # code -> {"buy_price","days_held","shares","buy_date","entry_own","trade"}
        self.pending: list = []         # 다음 시가 주문 (team.py st["pending"])
        self.prev_value = None          # 어제 종가 평가액 (하루 -7% 규칙용)
        self.stopped = False            # 서킷 영구 정지
        # H3 단계적 서킷
        self.peak = budget
        self.half = False
        self.paused = False
        self.pause_end = None
        # 기록
        self.interest = 0.0
        self.cost_stock = 0.0           # 주식 다리 슬리피지+수수료
        self.tax_stock = 0.0            # 주식 매도세
        self.cost_index = 0.0           # 지수 다리 슬리피지+수수료
        self.over_slots = 0             # 빈자리가 모자라 주문 못 낸 후보 수 (보류 아님, 참고)
        self.units_moved = 0.0          # H4 로 받은(+)/준(-) 지수 단위 합
        # H4: 월 수익률(시간가중) 기록
        self.nav = 1.0
        self.nav_last_close = budget
        self.flow = None                # (재배분 직전 평가액, 직후 평가액) — 그날만
        self.nav_at_me = 1.0
        self.excess: list = []          # 월 초과수익 (트레이너 - 지수)
        self.monthly: list = []         # (월말 날짜, 트레이너 월수익, 지수 월수익)

    def mode(self, md: MarketData, t: int) -> str:
        return md.trend_mode[t] if self.idle == "trend" else self.idle

    def units(self, idx_code: str) -> float:
        h = self.wallet.holdings.get(idx_code)
        return float(h.shares) if h else 0.0


# ================================================================ 시뮬레이터 본체
class TeamSim:
    def __init__(self, md: MarketData, cfg: Config, i0: int, i1: int):
        self.md, self.cfg, self.i0, self.i1 = md, cfg, i0, i1
        self.total = cfg.total if cfg.total is not None else TOTALS[md.key]
        names = list(cfg.trainers) if cfg.trainers else TRAINERS
        ratios = cfg.ratios or RATIOS
        caps = cfg.caps or CAPS
        self.universe = [md.by_code[c] for c in (cfg.universe or [s.code for s in md.stocks]) if c in md.by_code]
        self.sleeves: list[Sleeve] = []
        arm = cfg.arm
        trainer_total = self.total
        if arm == "A2":
            self.sleeves.append(self._sleeve("지수70%", None, self.total * A2_INDEX_SHARE, 0.0, "index"))
            trainer_total = self.total * (1 - A2_INDEX_SHARE)
        if arm in ("A0", "A1", "A1T", "A2"):
            idle = {"A0": "cash", "A1": "index", "A1T": "trend", "A2": "cash"}[arm]
            for t in names:
                self.sleeves.append(self._sleeve(t, t, trainer_total * ratios[t], caps[t], idle))
        elif arm == "G11":
            self.sleeves.append(self._sleeve("G11", None, self.total, 0.0, "trend"))
        elif arm == "IDX":
            self.sleeves.append(self._sleeve("지수B&H", None, self.total, 0.0, "index"))
        self.trainers = [s for s in self.sleeves if s.brain]
        self.h4_w = {s.name: ratios[s.name] / sum(ratios[x.name] for x in self.trainers) for s in self.trainers}
        self.fills, self.orders, self.skips, self.trades, self.events = [], [], [], [], []
        self.open_fallbacks = 0
        self.rows = []
        self.rate_missing = 0

    def _sleeve(self, name, brain, budget, cap, idle):
        w = main.make_wallet(name, "us" if self.md.key.startswith("us") else "kr")   # 시장 비용으로 만든 지갑
        s = Sleeve(name, brain, budget, cap, idle, w)
        s.breaker = CircuitBreaker(CB_CUM, CB_DAY)                 # H3 (나) 지금 서킷
        s.day_breaker = CircuitBreaker(float("inf"), CB_DAY)       # H3 (다) 의 '하루 -7%' 만
        return s

    # ------------------------------------------------ 지갑 다리 (PaperWallet 계산 그대로)
    def _sell(self, s: Sleeve, code: str, px: float, qty, t: int, tax: float, kind: str):
        """PaperWallet.sell 로 판다. 매도세는 그날 세율로 잠깐 바꿔 넣는다(국내 A4, 지수 0)."""
        w = s.wallet
        before, keep = w.cash, w.sell_tax_rate
        w.sell_tax_rate = tax
        ok = w.sell(code, px, qty, self.md.dstr[t])
        w.sell_tax_rate = keep
        if not ok:
            raise AssertionError(f"{s.name} {code} 매도 실패 qty={qty}")
        net = w.cash - before
        gross = px * qty
        proceeds = px * (1 - w.slippage) * qty
        taxed = proceeds * tax
        cost = gross - net - taxed
        if kind == "index":
            s.cost_index += cost
        else:
            s.cost_stock += cost
            s.tax_stock += taxed
        self.fills.append({"sleeve": s.name, "date": self.md.dstr[t], "code": code, "side": "매도", "kind": kind,
                           "qty": qty, "price": px, "cash": net, "cost": cost, "tax": taxed})
        return net

    def _buy(self, s: Sleeve, code: str, px: float, qty, t: int, kind: str) -> bool:
        w = s.wallet
        before = w.cash
        if not w.buy(code, px, qty, self.md.dstr[t]):
            return False
        spent = before - w.cash
        cost = spent - px * qty
        if kind == "index":
            s.cost_index += cost
        else:
            s.cost_stock += cost
        self.fills.append({"sleeve": s.name, "date": self.md.dstr[t], "code": code, "side": "매수", "kind": kind,
                           "qty": qty, "price": px, "cash": -spent, "cost": cost, "tax": 0.0})
        return True

    def _idx_net_per_unit(self, s, t):
        w, px = s.wallet, self.md.idx_open[t]
        proceeds = px * (1 - w.slippage)
        return proceeds - proceeds * w.fee_rate            # 지수 1단위 팔면 받는 돈 (매도세 0)

    def _sell_index_all(self, s: Sleeve, t: int):
        u = s.units(self.md.idx_code)
        if u > 0:
            self._sell(s, self.md.idx_code, self.md.idx_open[t], u, t, 0.0, "index")

    def _raise_cash(self, s: Sleeve, need: float, t: int):
        """현금이 need 보다 모자라면 그만큼만 지수를 판다(소수 단위)."""
        short = need - s.wallet.cash
        if short <= 0:
            return
        held = s.units(self.md.idx_code)
        u = min(held, short / self._idx_net_per_unit(s, t) * (1 + 1e-9))
        if u > 0:
            self._sell(s, self.md.idx_code, self.md.idx_open[t], u, t, 0.0, "index")

    def _sweep_to_index(self, s: Sleeve, t: int):
        """남은 현금을 전부 지수로 (소수 단위, 남는 돈 < 1)."""
        w = s.wallet
        if w.cash < SWEEP_MIN:
            return
        px = self.md.idx_open[t]
        unit = px * (1 + w.slippage) * (1 + w.fee_rate)
        for shrink in (1e-12, 1e-9, 1e-6):
            u = w.cash / unit * (1 - shrink)
            if self._buy(s, self.md.idx_code, px, u, t, "index"):
                return
        raise AssertionError("지수 매수 실패")

    def _skip(self, s, code, why, t, kind):
        s.wallet.skip(code, why, self.md.dstr[t])           # team.py 처럼 지갑 로그에 '보류' 기록
        self.skips.append({"sleeve": s.name, "date": self.md.dstr[t], "code": code, "kind": kind, "reason": why})

    # ------------------------------------------------ 시가: ① 주문 체결 (+ 대기 자산 다리)
    def _open(self, t: int):
        md = self.md
        for s in self.sleeves:
            if t == self.i0:
                s.wallet.deposit(s.start_cash, md.dstr[t])
            mode = s.mode(md, t)
            todo, still = [], []
            for o in s.pending:
                (todo if md.by_code[o["code"]].own_at_cal[t] >= 0 else still).append(o)
            s.pending = still                    # 오늘 봉이 없는 종목(국내 거래정지)의 주문은 다음 거래된 봉으로 (A5)
            for pos in s.positions.values():     # 어제부터 들고 있던 것만 하루 늘림(그 종목 봉이 있는 날)
                if md.by_code[pos["code"]].own_at_cal[t] >= 0:
                    pos["days_held"] += 1
            # (1) 주식 매도 → 현금
            for o in todo:
                if o["action"] == "매도" and o["code"] in s.positions:
                    self._fill_sell(s, o, t)
            # (2) 대기 자산이 현금인 날(H2 전환·G11)엔 지수를 전부 판다
            if mode == "cash":
                self._sell_index_all(s, t)
            # (3) 주식 매수 (지수 대기면 모자란 만큼만 지수를 팔아서)
            for o in todo:
                if o["action"] == "매수" and o["code"] not in s.positions:
                    self._fill_buy(s, o, t, mode)
            # (4) 남은 현금 → 지수 (첫날 전부 매수, 매도 대금 재투자, 현금→지수 전환)
            if mode == "index":
                self._sweep_to_index(s, t)
        if self.cfg.realloc and md.quarter_first[t]:
            self._realloc(t)

    def _px(self, stock: Stock, j: int) -> float:
        px = main.open_price({"Open": stock.open[j], "Close": stock.close[j]})   # 체결가 = 시가 (main.py 그대로)
        if px != stock.open[j]:
            self.open_fallbacks += 1        # 시가 대신 종가 체결(S0-2). 국내는 Volume=0 행을 빼서 0이어야 함
        return px

    def _fill_sell(self, s: Sleeve, o: dict, t: int):
        md = self.md
        stock = md.by_code[o["code"]]
        j = int(stock.own_at_cal[t])
        pos = s.positions.pop(o["code"])
        px = self._px(stock, j)
        net = self._sell(s, stock.code, px, pos["shares"], t, md.tax_at_cal[t], "stock")
        tr = pos["trade"]
        tr.update({"exit_date": md.dstr[t], "exit_cal": t, "exit_own": j, "exit_price": px, "exit_net": net,
                   "exit_reason": o.get("reason", ""), "exit_signal_date": o["signal_date"]})

    def _fill_buy(self, s: Sleeve, o: dict, t: int, mode: str):
        md, w = self.md, s.wallet
        stock = md.by_code[o["code"]]
        j = int(stock.own_at_cal[t])
        px = self._px(stock, j)
        budget = w.cash if self.cfg.cap_base == "cash" else s.cap_budget
        cap = s.cap * o["cap_mult"]
        n = shares_within_cap(budget, cap, px, w.fee_rate, w.slippage)
        if n <= 0:
            why = f"상한 {main.fmt(md.mk, budget * cap, False)} 안에서 1주도 못 삼 (시가 {main.px_txt(md.mk, px)})"
            self._skip(s, stock.code, why, t, "0주")
            return
        exec_px = px * (1 + w.slippage)                 # PaperWallet.buy 와 같은 순서로 필요 금액 계산
        need = exec_px * n + exec_px * n * w.fee_rate
        avail = w.cash
        if mode == "index":
            avail += s.units(md.idx_code) * self._idx_net_per_unit(s, t)
        if need > avail:
            why = f"현금 부족 (필요 {main.fmt(md.mk, px * n, False)}, 보유 {main.fmt(md.mk, avail, False)})"
            self._skip(s, stock.code, why, t, "현금부족")
            return
        if mode == "index":
            self._raise_cash(s, need, t)
        if not self._buy(s, stock.code, px, n, t, "stock"):
            why = f"현금 부족 (필요 {main.fmt(md.mk, px * n, False)}, 보유 {main.fmt(md.mk, w.cash, False)})"
            self._skip(s, stock.code, why, t, "현금부족")
            return
        tr = {"sleeve": s.name, "trainer": s.brain, "code": stock.code, "entry_date": md.dstr[t], "entry_cal": t,
              "entry_own": j, "shares": n, "entry_price": px, "notional": px * n, "entry_spent": need,
              "signal_date": o["signal_date"], "signal_reason": o.get("reason", ""), "cap_mult": o["cap_mult"],
              "exit_date": None, "exit_cal": None,
              "exit_own": None, "exit_price": None, "exit_net": None, "exit_reason": None}
        self.trades.append(tr)
        s.positions[stock.code] = {"code": stock.code, "buy_price": px, "days_held": 0, "shares": n,
                                   "buy_date": md.dstr[t], "entry_own": j, "trade": tr}

    # ------------------------------------------------ H4 재배분 (분기 첫 거래일 시가, 체결 뒤)
    def _value_at_open(self, s: Sleeve, t: int) -> float:
        md = self.md
        v = s.wallet.cash + s.units(md.idx_code) * md.idx_open[t]
        for code, pos in s.positions.items():
            st = md.by_code[code]
            j = st.own_at_cal[t]
            px = st.open[j] if j >= 0 else st.close[st.last_own_at_cal[t]]
            v += pos["shares"] * px
        return v

    def _realloc(self, t: int):
        md = self.md
        tr = self.trainers
        base = {s.name: (self.cfg.ratios or RATIOS)[s.name] for s in tr}
        w_new, tstats = h4_weights([s.excess for s in tr], [base[s.name] for s in tr])
        w_new = dict(zip([s.name for s in tr], w_new))
        n = len(tr[0].excess)
        changed = any(abs(w_new[k] - self.h4_w[k]) > 1e-12 for k in w_new)
        ev = {"date": md.dstr[t], "kind": "H4", "n_months": n, "t": tstats, "w_old": dict(self.h4_w),
              "w_new": w_new, "moved": {}, "changed": changed}
        if not changed:
            self.events.append(ev)
            return
        vals = {s.name: self._value_at_open(s, t) for s in tr}
        V = sum(vals.values())
        px = md.idx_open[t]
        excess = {k: vals[k] - w_new[k] * V for k in vals}           # +: 줄 쪽, -: 받을 쪽
        give = {s.name: min(excess[s.name], s.units(md.idx_code) * px) for s in tr if excess[s.name] > 0}
        G = sum(give.values())
        need = {k: -x for k, x in excess.items() if x < 0}
        N = sum(need.values())
        moved = {}
        for s in tr:
            s.flow = (vals[s.name], None)
        if G > 0 and N > 0:
            for s in tr:                                              # 대기 자산(지수 단위)만 옮김, 비용 없음(I7)
                if s.name in give:
                    du = -give[s.name] / px
                elif s.name in need:
                    du = G * need[s.name] / N / px
                else:
                    du = 0.0
                if du:
                    _move_units(s.wallet, md.idx_code, du, px)
                    s.units_moved += du
                    moved[s.name] = du * px
        for s in tr:
            s.flow = (vals[s.name], self._value_at_open(s, t))
            s.cap_budget = w_new[s.name] * V                          # I5: 종목상한 기준 = 재배분 때 배정액
        self.h4_w = w_new
        ev["moved"] = moved
        ev["V"] = V
        ev["pre"] = vals
        ev["post"] = {s.name: s.flow[1] for s in tr}
        ev["short"] = G < sum(x for x in excess.values() if x > 0) - 1e-9 * V   # 옮길 지수가 모자랐나
        self.events.append(ev)

    # ------------------------------------------------ 종가: 이자 → 평가 → ②③④ 판단
    def _close(self, t: int):
        md, cfg = self.md, self.cfg
        d = md.dstr[t]
        rate = md.rate_pct[t] if cfg.interest else 0.0
        if cfg.interest and not math.isfinite(rate):
            self.rate_missing += 1
            rate = 0.0
        row = {"date": d}
        tot = {"value": 0.0, "stock": 0.0, "index": 0.0, "cash": 0.0, "interest": 0.0}
        for s in self.sleeves:
            w = s.wallet
            if rate and w.cash > 0:                          # A1/A2: 현금 × 연% / 100 / 252 (거래일마다)
                it = w.cash * rate / 100 / 252
                w.cash += it
                s.interest += it
                tot["interest"] += it
            prices = {md.idx_code: md.idx_close[t]}
            stock_v = 0.0
            for code, pos in s.positions.items():
                st = md.by_code[code]
                prices[code] = st.close[st.last_own_at_cal[t]]       # 국내 정지일이면 마지막 종가
                stock_v += pos["shares"] * prices[code]
            idx_v = s.units(md.idx_code) * md.idx_close[t]
            value = w.value(prices)                                  # PaperWallet.value (현금+주식+지수)
            if abs(value - (w.cash + stock_v + idx_v)) > 1e-6 * max(1.0, value):
                raise AssertionError("평가액 불일치")
            # H4 용 시간가중 수익률 (재배분 날은 시가 전후로 나눔)
            if s.flow is not None and s.flow[1] is not None:
                s.nav *= (s.flow[0] / s.nav_last_close) * (value / s.flow[1])
            else:
                s.nav *= value / s.nav_last_close
            s.flow = None
            s.nav_last_close = value
            if md.month_end[t] and s.brain:
                base_i = md.idx_close[self._last_me] if self._last_me is not None else md.idx_open[self.i0]
                r_k = s.nav / s.nav_at_me - 1
                r_i = md.idx_close[t] / base_i - 1
                s.excess.append(r_k - r_i)
                s.monthly.append((d, r_k, r_i))
                s.nav_at_me = s.nav
            row[f"v_{s.name}"] = value
            row[f"stock_{s.name}"] = stock_v
            row[f"index_{s.name}"] = idx_v
            row[f"cash_{s.name}"] = w.cash
            row[f"mode_{s.name}"] = s.mode(md, t)
            if s.brain:
                row[f"flag_{s.name}"] = ("정지" if s.stopped else "쉼" if s.paused else "절반" if s.half else "")
            tot["value"] += value
            tot["stock"] += stock_v
            tot["index"] += idx_v
            tot["cash"] += w.cash
            if s.brain and t < self.i1:
                self._decide(s, t, value)
            s.prev_value = value
        if md.month_end[t]:
            self._last_me = t
        row.update(tot)
        self.rows.append(row)

    def _liquidate_orders(self, s: Sleeve, t: int, reason: str):
        """team.py ③ 처럼 대기 주문을 '보유 전부 매도'로 바꾼다 (매수 대기 주문은 버린다)."""
        s.pending = [{"code": c, "action": "매도", "signal_date": self.md.dstr[t], "signal_cal": t,
                      "reason": reason, "cap_mult": 1.0} for c in s.positions]
        for o in s.pending:
            self.orders.append({"sleeve": s.name, **o})

    def _staged(self, s: Sleeve, t: int, value: float):
        """H3 단계적 서킷 (사전 등록 §7 H3). 종가마다 고점 대비 낙폭 d."""
        md = self.md
        hit = s.day_breaker.check(s.start_cash, s.prev_value, value)   # 기존 하루 -7% 규칙 그대로(영구 정지, I9)
        if hit:
            self._liquidate_orders(s, t, "서킷(하루 -7%)")
            s.stopped = True
            self.events.append({"date": md.dstr[t], "kind": "H3 하루-7% 정지", "sleeve": s.name, "value": value})
            return
        if s.paused:
            if t >= s.pause_end:                        # 20거래일 쉼 끝 → 고점 = 지금 평가액, 절반 상한으로 재개
                s.paused, s.peak, s.half = False, value, True
                self.events.append({"date": md.dstr[t], "kind": "H3 재개(절반)", "sleeve": s.name, "value": value})
            else:
                return
        if value > s.peak:
            if s.half:
                self.events.append({"date": md.dstr[t], "kind": "H3 원래 상한", "sleeve": s.name, "value": value})
            s.peak, s.half = value, False
        dd = value / s.peak - 1
        if dd <= H3_STOP_DD:
            self._liquidate_orders(s, t, "단계 서킷(-20%)")
            s.paused, s.pause_end, s.half = True, t + H3_PAUSE_DAYS, True
            self.events.append({"date": md.dstr[t], "kind": "H3 -20% 정리", "sleeve": s.name, "dd": dd,
                                "value": value, "peak": s.peak})
        elif dd <= H3_HALF_DD and not s.half:
            s.half = True
            self.events.append({"date": md.dstr[t], "kind": "H3 -10% 절반", "sleeve": s.name, "dd": dd,
                                "value": value, "peak": s.peak})

    def _decide(self, s: Sleeve, t: int, value: float):
        md, cfg = self.md, self.cfg
        d = md.dstr[t]
        # ② 보유 종목 매도 판단 (그 종목 봉이 오늘 있고, 이미 대기 주문이 없을 때)
        pend_codes = {o["code"] for o in s.pending}
        for code, pos in s.positions.items():
            st = md.by_code[code]
            j = int(st.own_at_cal[t])
            if j < 0 or code in pend_codes:
                continue
            if pos["days_held"] != j - pos["entry_own"]:
                raise AssertionError("days_held 계산 불일치")
            hit, why = md.exit_check(s.brain, st, pos["entry_own"], j, pos["buy_price"])
            if hit:
                o = {"code": code, "action": "매도", "signal_date": d, "signal_cal": t, "reason": why,
                     "cap_mult": 1.0}
                s.pending.append(o)
                self.orders.append({"sleeve": s.name, **o})
        # ③ 서킷 브레이커
        if cfg.cb == "current" and not s.stopped:
            hit = s.breaker.check(s.start_cash, s.prev_value, value)
            if hit:
                self._liquidate_orders(s, t, "서킷 브레이커")
                s.stopped = True
                self.events.append({"date": d, "kind": "서킷(지금)", "sleeve": s.name, "why": hit, "value": value})
        elif cfg.cb == "staged" and not s.stopped:
            self._staged(s, t, value)
        # ④ 신규 후보 → 다음 시가 매수 주문 (팀장 LLM 끔 → 규칙 그대로)
        if s.stopped or s.paused:
            return
        pending_buys = [o for o in s.pending if o["action"] == "매수"]
        if len(s.positions) + len(pending_buys) >= cfg.max_positions:
            return
        busy = set(s.positions) | {o["code"] for o in s.pending}
        cands = []
        for st in self.universe:                    # universe 순서 = 시총 순위 / KR_UNIVERSE 순서
            if st.code in busy:
                continue
            j = int(st.own_at_cal[t])
            if j < 0 or j + 1 < MIN_BARS:           # A5 오늘 봉 없음 / A7 60봉 미만
                continue
            if md.flat_action(s.brain, st, j) == BUY:
                cands.append({"code": st.code, "date": d, "reason": st.flat_reason[s.brain].get(j, "")})
        if not cands:
            return
        cands = analyst.apply(cands, None)          # 팀장 부재 → 규칙 그대로
        kept = [c for c in ({**c, "conviction": team.to_conviction(c.get("conviction"))} for c in cands)
                if team.keep_candidate(c)]
        kept.sort(key=lambda c: c.get("conviction") or 0, reverse=True)   # 모두 None → 순서 그대로(안정 정렬)
        slots = cfg.max_positions - len(s.positions) - len(pending_buys)
        s.over_slots += max(0, len(kept) - max(slots, 0))
        for c in kept[:max(slots, 0)]:
            o = {"code": c["code"], "action": "매수", "signal_date": c["date"], "signal_cal": t,
                 "reason": c.get("reason", ""), "cap_mult": 0.5 if s.half else 1.0}
            s.pending.append(o)
            self.orders.append({"sleeve": s.name, **o})

    # ------------------------------------------------ 실행
    def run(self) -> dict:
        self._last_me = None
        for t in range(self.i0, self.i1 + 1):
            self._open(t)
            self._close(t)
        return self._finish()

    def _final_value(self, s: Sleeve) -> float:
        """끝: 들고 있는 것은 마지막 종가에 판다고 보고 매도 비용을 뺀 값 (R0 와 같음, PaperWallet.sell 계산)."""
        md, w, t = self.md, s.wallet, self.i1
        v = w.cash
        for code, pos in s.positions.items():
            st = md.by_code[code]
            proceeds = st.close[st.last_own_at_cal[t]] * (1 - w.slippage) * pos["shares"]
            v += proceeds - proceeds * w.fee_rate - proceeds * md.tax_at_cal[t]
        u = s.units(md.idx_code)
        if u:
            proceeds = md.idx_close[t] * (1 - w.slippage) * u
            v += proceeds - proceeds * w.fee_rate
        return v

    def _finish(self) -> dict:
        md, cfg = self.md, self.cfg
        daily = pd.DataFrame(self.rows).set_index("date")
        # 하루 단위 기록: 비율, 체결 수, 보류 수, 비용
        daily["stock_frac"] = daily["stock"] / daily["value"]
        daily["index_frac"] = daily["index"] / daily["value"]
        daily["cash_frac"] = daily["cash"] / daily["value"]
        fl = pd.DataFrame(self.fills, columns=["date", "kind", "side", "cost", "tax"])
        sk = pd.DataFrame(self.skips, columns=["date", "kind"])
        st_f = fl[fl["kind"] == "stock"]
        daily["n_buys"] = st_f[st_f["side"] == "매수"].groupby("date").size().reindex(daily.index, fill_value=0)
        daily["n_sells"] = st_f[st_f["side"] == "매도"].groupby("date").size().reindex(daily.index, fill_value=0)
        daily["n_index_legs"] = fl[fl["kind"] == "index"].groupby("date").size().reindex(daily.index, fill_value=0)
        daily["n_skips"] = sk.groupby("date").size().reindex(daily.index, fill_value=0)
        daily["costs"] = (fl.assign(c=fl["cost"] + fl["tax"]).groupby("date")["c"].sum()
                          .reindex(daily.index, fill_value=0.0))
        finals = {s.name: self._final_value(s) for s in self.sleeves}
        final = sum(finals.values())
        equity = daily["value"].to_numpy(float).copy()
        equity[-1] = final
        for tr in self.trades:
            tr["held_at_end"] = tr["exit_date"] is None
        stock_frac = daily["stock_frac"].to_numpy()
        idx_frac = daily["index_frac"].to_numpy()
        cash_frac = daily["cash_frac"].to_numpy()
        skip_kinds: dict = {}
        for k in self.skips:
            skip_kinds[k["kind"]] = skip_kinds.get(k["kind"], 0) + 1
        stock_fills = [f for f in self.fills if f["kind"] == "stock"]
        res = {
            "config": cfg, "market": md.key, "start": md.dstr[self.i0], "end": md.dstr[self.i1],
            "i0": self.i0, "i1": self.i1, "total": self.total,
            "daily": daily, "equity": equity, "final": final, "finals": finals,
            "fills": self.fills, "orders": self.orders, "skips": self.skips, "trades": self.trades,
            "events": self.events,
            "sleeves": {s.name: {"brain": s.brain, "start_cash": s.start_cash, "final": finals[s.name],
                                 "interest": s.interest, "cost_stock": s.cost_stock, "tax_stock": s.tax_stock,
                                 "cost_index": s.cost_index, "stopped": s.stopped, "over_slots": s.over_slots,
                                 "monthly": s.monthly, "cap_budget_end": s.cap_budget,
                                 "cash_end": s.wallet.cash, "units_end": s.units(md.idx_code),
                                 "units_moved": s.units_moved,
                                 "wallet_log_len": len(s.wallet.log)} for s in self.sleeves},
            "metrics": {
                "return": final / self.total - 1,
                "mdd": metrics.max_drawdown(list(equity)) or 0.0,
                "stock_frac_mean": float(np.mean(stock_frac)),
                "index_frac_mean": float(np.mean(idx_frac)),
                "cash_frac_mean": float(np.mean(cash_frac)),
                "days_with_stock": float(np.mean(daily["stock"].to_numpy() > 0)),
                "buys": sum(1 for f in stock_fills if f["side"] == "매수"),
                "sells": sum(1 for f in stock_fills if f["side"] == "매도"),
                "index_legs": sum(1 for f in self.fills if f["kind"] == "index"),
                "skips": len(self.skips), "skip_kinds": skip_kinds,
                "over_slots": sum(s.over_slots for s in self.sleeves),
                "cost_stock": sum(s.cost_stock for s in self.sleeves),
                "tax_stock": sum(s.tax_stock for s in self.sleeves),
                "cost_index": sum(s.cost_index for s in self.sleeves),
                "interest": sum(s.interest for s in self.sleeves),
                "rate_missing_days": self.rate_missing,
                "open_fallbacks": self.open_fallbacks,
                "min_cash": float(min(daily[[c for c in daily.columns
                                             if c.startswith("cash_") and c != "cash_frac"]].min())),
            },
        }
        res["metrics"]["costs_total"] = (res["metrics"]["cost_stock"] + res["metrics"]["tax_stock"]
                                         + res["metrics"]["cost_index"])
        return res


def _move_units(w: PaperWallet, code: str, du: float, px: float):
    """지갑 사이에서 지수 단위를 옮긴다(팀 내부 이동이라 매매·비용 없음, I7)."""
    h = w.holdings.get(code)
    if du < 0:
        if h is None or h.shares + du < -1e-9:
            raise AssertionError("옮길 지수 단위가 모자람")
        h.shares = max(0.0, h.shares + du)
        if h.shares == 0:
            del w.holdings[code]
    else:
        if h is None:
            w.holdings[code] = Holding(shares=du, avg_price=px)
        else:
            h.avg_price = (h.avg_price * h.shares + px * du) / (h.shares + du)
            h.shares += du


def h4_weights(excess_lists, base):
    """H4 몫: n<20 이면 기본몫, 아니면 기본몫 × min(2, max(0.25, 1 + 0.25·t)) 를 합 1로.
    t = 평균 / 표준편차(표본, ddof=1) × √n. 표준편차가 0이면 t=0 (I8)."""
    base = np.asarray(base, float) / np.sum(base)
    n = len(excess_lists[0])
    if n < H4_MIN_MONTHS:
        return list(base), None
    ts = []
    for x in excess_lists:
        x = np.asarray(x, float)
        sd = float(np.std(x, ddof=1))
        ts.append(float(np.mean(x)) / sd * math.sqrt(n) if sd > 0 else 0.0)
    raw = base * np.array([min(H4_HI, max(H4_LO, 1 + H4_SLOPE * t)) for t in ts])
    return list(raw / raw.sum()), ts


# ================================================================ 참고선
def index_buy_hold(md: MarketData, i0: int, i1: int, budget: float) -> dict:
    """지수 B&H (R0 sim.buy_hold 와 같은 방식: metrics.buy_and_hold, 정수 단위, 같은 비용, 매도세 0)."""
    frame = pd.DataFrame({"Open": md.idx_open[i0:i1 + 1], "Close": md.idx_close[i0:i1 + 1]},
                         index=md.cal[i0:i1 + 1])
    bh = metrics.buy_and_hold(frame, budget, md.idx_fee, md.idx_slip)
    unit = md.idx_open[i0] * (1 + md.idx_slip) * (1 + md.idx_fee)
    equity = list(budget - bh["shares"] * unit + bh["shares"] * md.idx_close[i0:i1 + 1])
    equity[-1] = budget + bh["profit"]
    return {"return": bh["profit"] / budget, "mdd": metrics.max_drawdown(equity) or 0.0, "equity": equity,
            "shares": bh["shares"]}


def equal_weight_buy_hold(md: MarketData, i0: int, i1: int, total: float, codes=None) -> dict:
    """종목군 동일비중 B&H (R0 buy_hold 와 같은 비용 기준, 국내는 매도세를 국면 끝 날짜 세율로 뺌 —
    main._buy_and_hold 와 같은 식). 국면 첫날까지 상장된 종목만(I12)."""
    stocks = [md.by_code[c] for c in (codes or [s.code for s in md.stocks]) if c in md.by_code]
    live = []
    for st in stocks:
        if st.last_own_at_cal[i0] < 0:
            continue                                  # 국면 시작 뒤 상장 → 제외
        ja = int(np.searchsorted(st.cal_of_own, i0))  # i0 이후 첫 자기 봉
        jb = int(st.last_own_at_cal[i1])
        if ja <= jb:
            live.append((st, ja, jb))
    if not live:
        return {"return": 0.0, "mdd": 0.0, "equity": [total] * (i1 - i0 + 1), "n": 0}
    b = total / len(live)
    eq = np.zeros(i1 - i0 + 1)
    profit = 0.0
    for st, ja, jb in live:
        frame = st.df.iloc[ja:jb + 1][["Open", "Close"]]
        bh = metrics.buy_and_hold(frame, b, md.fee, md.slip)
        tax = bh["shares"] * st.close[jb] * (1 - md.slip) * md.tax_at_cal[i1]
        profit += bh["profit"] - tax
        unit = st.open[ja] * (1 + md.slip) * (1 + md.fee)
        left = b - bh["shares"] * unit
        start_cal = st.cal_of_own[ja]
        for k, t in enumerate(range(i0, i1 + 1)):
            if t < start_cal:
                eq[k] += b
            else:
                eq[k] += left + bh["shares"] * st.close[st.last_own_at_cal[t]]
    eq[-1] = total + profit
    return {"return": profit / total, "mdd": metrics.max_drawdown(list(eq)) or 0.0, "equity": list(eq),
            "n": len(live)}


# ================================================================ H1-4 무작위 시점 대조 (가산형 근사)
class Contribution:
    """트레이너 기여(가산형 근사, I13):
        기여 = Σ_거래 [ 금액 × (종목 수익률 − 같은 구간 지수 수익률) − 그 거래가 더 낸 비용 ]
      - 금액 N = 주식 수 × 진입 시가, 구간 = 진입 체결 시가 → 청산 체결 시가(끝까지 보유면 마지막 종가)
      - 더 낸 비용 = 진입 때 (지수 매도 + 주식 매수) 비용 + 청산 때 (주식 매도 + 지수 재매수) 비용.
        끝까지 보유면 청산 쪽은 (주식 청산 비용 − 원래 지수였으면 냈을 청산 비용).
      - 복리·거래끼리 겹침·정수 주 효과는 무시한다. 실제와 무작위에 똑같이 적용한다.
    무작위: 각 거래의 종목·금액·보유 봉 수는 그대로, 진입 봉만 국면 안에서 '들어갈 수 있는' 봉 중 균등 무작위."""

    def __init__(self, md: MarketData, res: dict):
        self.md = md
        i0, i1 = res["i0"], res["i1"]
        tr = res["trades"]
        self.trainer = np.array([x["sleeve"] for x in tr])
        k = len(tr)
        opens, cals, taxes, base, codes = [], [], [], {}, []
        off = 0
        for x in tr:
            if x["code"] not in base:
                st = md.by_code[x["code"]]
                base[x["code"]] = off
                opens.append(st.open)
                cals.append(st.cal_of_own)
                taxes.append(md.tax_at_cal[st.cal_of_own])
                off += len(st.open)
        self.OPEN = np.concatenate(opens) if opens else np.zeros(0)
        self.CAL = np.concatenate(cals) if cals else np.zeros(0, int)
        self.TAX = np.concatenate(taxes) if taxes else np.zeros(0)
        self.b = np.array([base[x["code"]] for x in tr], dtype=np.int64)
        self.N = np.array([x["notional"] for x in tr], float)
        self.e = np.array([x["entry_own"] for x in tr], dtype=np.int64)
        self.jend = np.zeros(k, dtype=np.int64)
        self.endclose = np.zeros(k)
        self.lo = np.zeros(k, dtype=np.int64)
        for n, x in enumerate(tr):
            st = md.by_code[x["code"]]
            self.jend[n] = st.last_own_at_cal[i1]
            self.endclose[n] = st.close[self.jend[n]]
            jfirst = int(np.searchsorted(st.cal_of_own, i0))            # i0 이후 첫 자기 봉(신호 봉)
            self.lo[n] = max(jfirst + 1, MIN_BARS)                      # 체결 봉 = 신호 다음 봉, A7
        x_end = np.array([x["exit_own"] if x["exit_own"] is not None else -1 for x in tr], dtype=np.int64)
        self.L = np.where(x_end >= 0, x_end, self.jend + 1) - self.e    # 보유 봉 수 (끝까지 보유면 jend+1 까지)
        self.hi = self.jend + 1 - self.L
        if k and ((self.e < self.lo) | (self.e > self.hi)).any():
            raise AssertionError("실제 거래가 무작위 범위 밖")
        self.idx_end = md.idx_close[i1]
        self.tax_end = md.tax_at_cal[i1]
        f, s = md.fee, md.slip
        self.cb_stk = (1 + s) * (1 + f) - 1        # 매수 비용률 (주식·지수 같음)
        self.cb_idx = (1 + md.idx_slip) * (1 + md.idx_fee) - 1
        self.cs_idx = 1 - (1 - md.idx_slip) * (1 - md.idx_fee)
        self.slip, self.fee = s, f

    def per_trade(self, entries: np.ndarray) -> np.ndarray:
        """entries: (..., k) 진입 자기 봉. 거래별 기여를 같은 모양으로 돌려준다."""
        md = self.md
        x = entries + self.L
        exited = x <= self.jend
        xi = np.minimum(x, self.jend)
        g_s = np.where(exited, self.OPEN[self.b + xi], self.endclose) / self.OPEN[self.b + entries]
        i_exit = np.where(exited, md.idx_open[self.CAL[self.b + xi]], self.idx_end)
        g_i = i_exit / md.idx_open[self.CAL[self.b + entries]]
        tax = np.where(exited, self.TAX[self.b + xi], self.tax_end)
        cs_stk = 1 - (1 - self.slip) * (1 - self.fee - tax)
        N = self.N
        cost = N * (self.cb_stk + self.cs_idx) + np.where(
            exited, N * g_s * (cs_stk + self.cb_idx), N * g_s * cs_stk - N * g_i * self.cs_idx)
        return N * (g_s - g_i) - cost

    def actual(self) -> np.ndarray:
        return self.per_trade(self.e)

    def draws(self, n: int, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        span = self.hi - self.lo + 1
        u = rng.random((n, len(self.e)))
        ent = self.lo + np.floor(u * span).astype(np.int64)
        return ent


def random_control(md: MarketData, res: dict, n: int = 1000, seed: int = SEED) -> dict:
    c = Contribution(md, res)
    if len(c.e) == 0:
        return {"n_trades": 0}
    act = c.actual()
    ent = c.draws(n, seed)
    rnd = c.per_trade(ent)
    out = {"n_trades": len(c.e), "n_draws": n, "seed": seed}
    groups = {"전체": np.ones(len(c.e), bool)}
    for name in sorted(set(c.trainer)):
        groups[name] = c.trainer == name
    for g, m in groups.items():
        a = float(act[m].sum())
        r = rnd[:, m].sum(axis=1)
        out[g] = {"actual": a, "random_mean": float(r.mean()), "random_sd": float(r.std()),
                  "pct_below": float((r < a).mean()), "pct_le": float((r <= a).mean()), "trades": int(m.sum())}
    return out


# ================================================================ 진입점
def run(cfg: Config, md: MarketData | None = None) -> dict:
    """사전 등록 조건 하나를 돌린다. md 를 주면(합성 데이터 점검용) 그것을 쓴다."""
    _check_config(cfg)
    md = md or get_market(cfg.market)
    i0, i1 = period_range(md, cfg.period)
    if i1 <= i0:
        raise ValueError("국면이 너무 짧음")
    res = TeamSim(md, cfg, i0, i1).run()
    if cfg.with_refs:
        bh = index_buy_hold(md, i0, i1, res["total"])
        ew = equal_weight_buy_hold(md, i0, i1, res["total"], cfg.universe)
        refs = {"index_bh": bh, "ew_bh": ew}
        if cfg.arm != "G11":
            g = run(Config(market=cfg.market, period=cfg.period, arm="G11", interest=cfg.interest,
                           total=res["total"], with_refs=False), md)
            refs["g11"] = {"return": g["metrics"]["return"], "mdd": g["metrics"]["mdd"], "equity": list(g["equity"])}
        res["refs"] = refs
        m = res["metrics"]
        m["vs_index_bh"] = m["return"] - bh["return"]
        m["vs_ew_bh"] = m["return"] - ew["return"]
    if cfg.n_random > 0:
        res["random"] = random_control(md, res, cfg.n_random, cfg.seed)
    return res


# A6: 분할 정지 3건 뒤 20봉 안에 '거래량 급증' 조건으로 생긴 파이오니어 매수 건수 (데이터는 고치지 않고 보고만)
A6_SPLIT_SUSPENSIONS = {"005930": "2018-05-03", "035420": "2018-10-11", "035720": "2021-04-14"}   # 정지 마지막 날


def a6_split_volume_buys(md: MarketData, res: dict, bars: int = 20) -> dict:
    """정지가 끝난 뒤 그 종목의 거래된 봉 20개 안에 체결된 파이오니어 매수 중, 신호 사유가 '거래량 급증'(조건 A)인 건수."""
    out = {}
    for code, last_zero in A6_SPLIT_SUSPENSIONS.items():
        st = md.by_code.get(code)
        if st is None:
            continue
        j0 = int(np.searchsorted(np.array(st.dates), last_zero, side="right"))     # 정지 뒤 첫 거래된 봉
        window = set(st.dates[j0:j0 + bars])
        tr = [t for t in res["trades"] if t["code"] == code and t["trainer"] == "파이오니어"
              and t["entry_date"] in window]
        out[code] = {"after": st.dates[j0] if j0 < len(st.dates) else None,
                     "pioneer_buys": len(tr), "volume_signal_buys": sum("거래량" in t["signal_reason"] for t in tr)}
    return out


def label(cfg: Config) -> str:
    s = cfg.arm
    if cfg.cb != "none":
        s += f"+CB:{cfg.cb}"
    if cfg.realloc:
        s += "+H4"
    return s


def sanity_line(res: dict) -> str:
    """점검용 한 줄(성적 비교가 아니라 '제대로 돌았나'만)."""
    m = res["metrics"]
    return (f"{res['market']:6s} {label(res['config']):14s} {res['start']}~{res['end']} "
            f"매수 {m['buys']:4d} 매도 {m['sells']:4d} 지수다리 {m['index_legs']:4d} 보류 {m['skips']:4d} "
            f"최소현금 {m['min_cash']:.4f} 이자 {m['interest']:,.0f} 비용 {m['costs_total']:,.0f} "
            f"NaN {int(np.isnan(res['equity']).sum())} 시가대체 {m['open_fallbacks']}")


if __name__ == "__main__":
    # 한 조건만 돌려 '돌았나' 한 줄 보기: python -I sim_team.py us A1 "2018 조정"
    _a = sys.argv[1:]
    _r = run(Config(market=_a[0] if _a else "us", arm=_a[1] if len(_a) > 1 else "A0",
                    period=_a[2] if len(_a) > 2 else "2018 조정"))
    print(sanity_line(_r))
