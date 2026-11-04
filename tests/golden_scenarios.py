"""
golden_scenarios.py — 골든(바꾸기 전 결과) 장면 실행기
------------------------------------------------------------------
설계 docs/h1-forward-design.md §6 T-GOLD, §7 R13 ("h1=None 이면 운영 동작이 바이트까지 같다").

무엇을 하나 (주식 초보용 설명)
- 가짜 시장(정해진 씨앗으로 만든 합성 시세)에서 운영 팀장 루프 `team.run` 을 여러 날 돌린다.
- 날마다 남는 것(상태 JSON 파일 내용, 화면 출력, 팀장 claude 에게 보낸 질문, 그날 `screener.scan()` 결과)을
  파일로 모은다. 이것이 "골든"이다.
- 코드를 고치기 **전** 커밋(847ad13)에서 한 번 만들어 `tests/golden/` 에 두고,
  고친 뒤에는 같은 장면을 다시 돌려 **바이트까지 같은지** 본다(`tests/test_h1_golden.py`).

바꿔 끼우는 곳은 입출력 경계뿐이다 (그 밖의 함수는 진짜 코드가 돈다 → 나중 변경이 골든에 걸린다)
- 시세 받기: `FinanceDataReader` 모듈(`DataReader`·`StockListing`) → 가짜 모듈
- 팀장 호출: `shutil.which`·`subprocess.run` → 가짜 claude (인터넷·로그인·키 없음)
- 저장 폴더: `team.STATE_DIR`·`main.RESULTS_DIR` → 임시 폴더
- 시계: `main.datetime`(`main.confirmed_bars` 가 쓰는 `datetime.now`) → 시간대 있는 고정 시각
- 환경변수: `ANTHROPIC_API_KEY` 를 가짜 값으로 넣어 두고, claude 에 넘긴 환경에서 빠졌는지 기록한다

시세는 어느 컴퓨터에서나 같은 값이 나오게 만든다: 정수 난수(만분율 수익률) + 곱셈 + 반올림만 쓴다
(지수·로그 함수는 CPU 마다 마지막 자리가 다를 수 있어서 쓰지 않음).

실행
    python tests/golden_scenarios.py --write <폴더>     # 장면을 돌려 <폴더> 에 파일로 쓴다(가지 확인 포함)
    python tests/golden_scenarios.py --check            # 가지 확인만
이 파일은 자기 위 폴더(저장소 루트 또는 git worktree)의 team·main·screener·analyst 를 읽는다.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np      # noqa: E402
import pandas as pd     # noqa: E402

import main             # noqa: E402
import team             # noqa: E402
import screener         # noqa: E402
import analyst          # noqa: E402

for _mod in (main, team, screener, analyst):
    # 다른 폴더의 같은 이름 모듈을 읽으면 "자기와 비교"가 된다 → 바로 멈춘다
    if Path(_mod.__file__).resolve().parent != ROOT:
        raise RuntimeError(f"{_mod.__name__} 를 {ROOT} 가 아닌 곳에서 읽었어요: {_mod.__file__}")

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
TRAINERS = ("마라토너", "스프린터", "파이오니어")

# ============================ 가짜 시세 ============================

DATES = pd.bdate_range("2024-01-02", "2026-12-31")      # 평일 전부(휴장일 없음). 원본 시세의 날짜


def _rnd(x, kr):
    """가격 반올림: 국내는 원 단위 정수, 미국은 센트(소수 둘째 자리). 파이썬 round 는 어디서나 같은 값."""
    return float(round(x)) if kr else round(x, 2)


def make_frame(seed, base, kr, first=None, last=None, crash=None, crash_mult=0.70):
    """결정적인 합성 일봉 하나 (Open·High·Low·Close·Volume).
    - 종가: 전날 종가 × (1 + 정수/10000). 하루 −2.3% ~ +2.4%.
    - 시가: 전날 종가 × (1 + 정수/10000) (−0.9% ~ +0.9%). 종가와 일부러 다르게 (시가 체결을 구분하려고).
    - 거래량: 100만~300만, 20일 중 하루꼴로 2.5배 급증(파이오니어 '거래량 급증' 신호용).
    - crash: 그날 종가만 crash_mult 배(서킷 브레이커 장면용 폭락).
    - first/last: 상장 전·자료 끝(그 밖의 행은 없음)."""
    rng = np.random.default_rng(seed)
    n = len(DATES)
    ret = rng.integers(-230, 241, n)
    gap = rng.integers(-90, 91, n)
    hi = rng.integers(0, 151, n)
    lo = rng.integers(0, 151, n)
    vol = rng.integers(1_000_000, 3_000_001, n)
    spike = rng.integers(0, 20, n)
    rows, prev = [], float(base)
    crash_ts = pd.Timestamp(crash) if crash else None
    for i, day in enumerate(DATES):
        c = prev * (1 + int(ret[i]) / 10000)
        if crash_ts is not None and day == crash_ts:
            c = c * crash_mult
        o = prev * (1 + int(gap[i]) / 10000)
        c, o = _rnd(c, kr), _rnd(o, kr)
        h = _rnd(max(o, c) * (1 + int(hi[i]) / 10000), kr)
        lw = _rnd(min(o, c) * (1 - int(lo[i]) / 10000), kr)
        v = float(int(vol[i]) * 5 // 2) if int(spike[i]) == 0 else float(int(vol[i]))
        rows.append((o, h, lw, c, v))
        prev = c
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=DATES)
    df.index.name = "Date"
    if first:
        df = df.loc[pd.Timestamp(first):]
    if last:
        df = df.loc[:pd.Timestamp(last)]
    return df


def with_halts(df, halts):
    """거래정지일 행으로 바꾼다 (네이버 실제 모양 두 가지, tests/test_kr_fix_s0.py 와 같음).
    form "zero": Open=High=Low=0, Close=직전 종가, Volume=0 / "flat": OHLC 전부 직전 종가, Volume=0."""
    df = df.copy()
    for first, n, form in halts:
        i0 = df.index.get_loc(pd.Timestamp(first))
        prev = float(df["Close"].iloc[i0 - 1])
        for i in range(i0, i0 + n):
            df.iloc[i, df.columns.get_loc("Open")] = 0.0 if form == "zero" else prev
            df.iloc[i, df.columns.get_loc("High")] = 0.0 if form == "zero" else prev
            df.iloc[i, df.columns.get_loc("Low")] = 0.0 if form == "zero" else prev
            df.iloc[i, df.columns.get_loc("Close")] = prev
            df.iloc[i, df.columns.get_loc("Volume")] = 0.0
    return df


@dataclass(frozen=True)
class Spec:
    seed: int
    base: float
    fail: bool = False              # 받기 실패(가짜 네트워크 오류)
    first: str | None = None        # 상장일(짧은 이력)
    last: str | None = None         # 자료 끝(오래된 봉)
    halts: tuple = ()               # 국내 거래정지 ((첫날, 일수, 모양), ...)


class World:
    """가짜 FinanceDataReader. stock_cut·bench_cut 날짜까지의 원본 행만 돌려준다(실제 원본처럼 확정 전 봉 포함).
    확정 봉 고르기는 진짜 main.confirmed_bars 가 한다."""

    def __init__(self, market, specs, bench_code, bench_spec, listing=None, crash=None):
        self.market, self.bench_code, self.listing_syms = market, bench_code, listing
        kr = market == "kr"
        self.frames, self.fail = {}, set()
        for code, sp in specs.items():
            if sp.fail:
                self.fail.add(code)
                continue
            df = make_frame(sp.seed, sp.base, kr, sp.first, sp.last, crash=crash)
            self.frames[code] = with_halts(df, sp.halts) if sp.halts else df
        self.frames[bench_code] = make_frame(bench_spec.seed, bench_spec.base, False)
        self.stock_cut = self.bench_cut = None

    def DataReader(self, code, start):          # noqa: N802 (FinanceDataReader 이름 그대로)
        if code in self.fail:
            raise ConnectionError(f"가짜 네트워크 오류 ({code})")
        cut = self.bench_cut if code == self.bench_code else self.stock_cut
        return self.frames[code].loc[pd.Timestamp(start):pd.Timestamp(cut)].copy()

    def StockListing(self, name):               # noqa: N802
        if name != "S&P500" or self.listing_syms is None:
            raise AssertionError(f"이 장면에서는 S&P500 목록만 받아요 (받은 값: {name})")
        return pd.DataFrame({"Symbol": list(self.listing_syms)})

    def module(self):
        return types.SimpleNamespace(DataReader=self.DataReader, StockListing=self.StockListing,
                                     __name__="FinanceDataReader")


# ============================ 가짜 claude ============================

# 팀장 답의 모양을 차례로 돌려 쓴다(장면 전체에서 후보 하나마다 다음 칸). (verdict, conviction) / None = 답에서 빠짐
REPLY_KINDS = (
    ("buy", "0.9"),        # 문자열 확신도 → 0.9 로 읽힘
    ("hold", 0.8),         # 팀장 hold → 보류
    ("veto", 0.9),         # veto → 후보에서 빠짐
    ("buy", 0.3),          # 낮은 확신도 → 보류
    ("buy", "모름"),        # 숫자 아닌 확신도 → 무의견 → 통과
    (" VETO", 0.9),        # 운영 apply 는 공백 붙은 대문자를 veto 로 보지 않는다(지금 동작 그대로 고정)
    ("Hold", 0.7),         # 운영 team 은 대문자 Hold 를 hold 로 보지 않는다(지금 동작 그대로 고정)
    None,                  # 답에서 빠진 종목 → 규칙 그대로 통과
    ("buy", 0.5),          # 경계값 → 통과
    ("buy", "0.3"),        # 문자열 낮은 확신도 → 보류
    ("buy", None),         # 확신도 없음 → 통과
    ("buy", 0.75),
)

PROMPT_LINE = re.compile(r"^- (\S+): 신호사유=", re.MULTILINE)


class FakeClaude:
    """`shutil.which("claude")` 와 `subprocess.run(["claude", "-p", 프롬프트], ...)` 를 흉내 낸다.
    mode: "answer"(정상 답) | "missing"(claude 없음) | "timeout" | "oserror" | "nonzero" | "bad_json" | "no_analysis"."""

    def __init__(self, real_which, real_run):
        self.real_which, self.real_run = real_which, real_run
        self.mode = "answer"
        self.counter = 0
        self.calls = []

    def which(self, name, *a, **k):
        if name == "claude":
            return None if self.mode == "missing" else "/가짜/bin/claude"
        return self.real_which(name, *a, **k)

    def run(self, args, *a, **kw):
        if not (isinstance(args, (list, tuple)) and args and args[0] == "claude"):
            return self.real_run(args, *a, **kw)
        env = kw.get("env")
        rec = {"args": list(args[:2]), "prompt": args[2] if len(args) > 2 else None,
               "kwargs": sorted(kw), "timeout": kw.get("timeout"),
               "capture_output": kw.get("capture_output"), "text": kw.get("text"),
               "env_given": env is not None,
               "api_key_in_env": None if env is None else ("ANTHROPIC_API_KEY" in env),
               "mode": self.mode}
        self.calls.append(rec)
        if self.mode == "timeout":
            rec["reply"] = "TimeoutExpired"
            raise subprocess.TimeoutExpired(args, kw.get("timeout"))
        if self.mode == "oserror":
            rec["reply"] = "OSError"
            raise OSError("가짜 OSError")
        if self.mode == "nonzero":
            rec["reply"] = {"returncode": 1, "stdout": "한도 초과"}
            return subprocess.CompletedProcess(args, 1, stdout="한도 초과", stderr="오류")
        if self.mode == "bad_json":
            out = '분석 결과: {"analysis": [ 깨진 JSON'
            rec["reply"] = {"returncode": 0, "stdout": out}
            return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
        if self.mode == "no_analysis":
            out = '{"result": "analysis 키가 없음"}'
            rec["reply"] = {"returncode": 0, "stdout": out}
            return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
        codes = PROMPT_LINE.findall(rec["prompt"] or "")
        items, kinds = [], {}
        for code in codes:
            kind = REPLY_KINDS[self.counter % len(REPLY_KINDS)]
            self.counter += 1
            kinds[code] = kind
            if kind is None:
                continue
            items.append({"code": code, "verdict": kind[0], "conviction": kind[1], "note": f"가짜 팀장 메모 {code}"})
        items.append("문자열 항목(무시돼야 함)")
        items.append({"verdict": "buy", "note": "code 없는 항목(무시돼야 함)"})
        out = "팀장 분석입니다.\n" + json.dumps({"analysis": items}, ensure_ascii=False) + "\n끝."
        rec["kinds"] = {c: (list(k) if k else None) for c, k in kinds.items()}
        rec["reply"] = {"returncode": 0, "stdout": out}
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")


# ============================ 시계 ============================

def make_clock(fixed: datetime):
    """main.datetime 대신 넣을 시계. now(tz) 는 고정 시각을 그 시간대로 돌려준다."""
    if fixed.tzinfo is None:
        raise ValueError("시계는 시간대가 있어야 해요")

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed.astimezone(KST).replace(tzinfo=None)

    return FixedClock


# ============================ 장면 ============================

@dataclass(frozen=True)
class Step:
    label: str          # 폴더 이름(영문·숫자)
    now: datetime       # 실행 시각(시간대 있음)
    stock_cut: str      # 종목 원본 시세가 있는 마지막 날짜
    bench_cut: str      # 기준 지수(SPY/KS200) 원본 시세가 있는 마지막 날짜
    claude: str = "answer"
    note: str = ""      # 이 장면이 지나야 하는 가지(사람용 설명)


def us_now(bar):
    """미국 봉 bar 를 처리하는 실행 시각: 다음날 한국 07:10 (= 뉴욕 장 마감 뒤)."""
    d = pd.Timestamp(bar) + pd.Timedelta(days=1)
    return datetime(d.year, d.month, d.day, 7, 10, tzinfo=KST)


def kr_now(bar, hh=23, mm=5):
    d = pd.Timestamp(bar)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=KST)


US_LISTING = ("ALFA", "BRVO", "CHRL", float("nan"), "DLTA", "ECHO", "FXTR", "GOLF", "HTEL", "INDA",
              "JULT", "KILO", "LIMA", "FAIL", "NEWB", "STAL")
US_N = 15     # 목록 16칸(빈칸 1) 중 15종목 전부


def us_world():
    specs = {s: Spec(seed=100 + i, base=40.0 + 13 * i) for i, s in enumerate(US_LISTING) if isinstance(s, str)}
    specs["FAIL"] = Spec(seed=0, base=1.0, fail=True)
    specs["NEWB"] = Spec(seed=301, base=25.0, first=US_NEWB_FIRST)
    specs["STAL"] = Spec(seed=310, base=60.0, last=US_STAL_LAST)
    return World("us", specs, "SPY", Spec(seed=9, base=500.0), listing=US_LISTING, crash=US_CRASH)


KR_N = 10
KR_CODES = ("005930", "000660", "373220", "207940", "005380", "000270", "068270", "105560", "012450", "329180")


def kr_world():
    specs = {c: Spec(seed=200 + i, base=float(30_000 + 17_000 * i)) for i, c in enumerate(KR_CODES)}
    specs["373220"] = Spec(seed=0, base=1.0, fail=True)
    specs["329180"] = Spec(seed=401, base=150_000.0, first=KR_SHORT_FIRST)
    for code, halts in KR_HALTS.items():
        specs[code] = Spec(seed=specs[code].seed, base=specs[code].base, halts=halts)
    return World("kr", specs, "KS200", Spec(seed=19, base=400.0), crash=KR_CRASH)


# ---- 장면 값 (아래 숫자는 모든 가지를 지나도록 골랐다. 바꾸면 골든을 다시 만들어야 한다) ----
US_NEWB_FIRST = "2026-06-22"      # NEWB: 이 날 상장 → 2026-09-25 에 처음 70봉이 되어 스캔에 들어옴
US_STAL_LAST = "2026-09-08"       # STAL: 자료가 이 날 끝남(이 봉에서 스프린터·파이오니어 매수 신호) → 오래된 봉 제외
US_CRASH = "2026-09-30"           # 미국 종목 전부 이날 종가 −30% → 서킷 브레이커
KR_SHORT_FIRST = "2026-06-22"     # 329180: 짧은 이력 → 2026-09-25 에 처음 70봉
KR_HALTS = {
    "012450": (("2026-09-25", 3, "zero"),),   # 스프린터 매수 대기 중 3일 정지 → 정지 뒤 첫 거래일 시가 체결
    "000270": (("2026-10-01", 2, "flat"),),   # 마라토너 보유 중 2일 정지 → 판단 쉼, 스크리너 오래된 봉 제외
}
KR_CRASH = "2026-10-08"           # 국내 종목 전부 이날 종가 −30% → 서킷 브레이커


def us_steps():
    S = Step
    return [
        S("01-first-0921", us_now("2026-09-21"), "2026-09-21", "2026-09-21",
          note="① 첫 실행: 후보 + 팀장 buy/hold/veto/낮은 확신도/문자열 확신도, 주문"),
        S("02-same-bar-0921", us_now("2026-09-21"), "2026-09-21", "2026-09-21",
          note="④ 같은 봉 다시: 세 트레이너 모두 처리됨 → 스캔 생략(멱등)"),
        S("03-fill-0922", us_now("2026-09-22"), "2026-09-22", "2026-09-22",
          note="② 어제 주문 → 오늘 시가 체결 / ⑤ 후보·보유·주문 없는 트레이너는 저장 안 함"),
        S("04-same-bar-0922", us_now("2026-09-22"), "2026-09-22", "2026-09-22",
          note="④ 같은 봉 다시: 저장 안 된 트레이너가 있어 스캔은 하고, 저장된 트레이너는 '이미 처리됨'"),
        S("05-no-claude-0923", us_now("2026-09-23"), "2026-09-23", "2026-09-23", claude="missing",
          note="팀장(claude) 없음 → 규칙 폴백"),
        S("06-0924", us_now("2026-09-24"), "2026-09-24", "2026-09-24",
          note="③ 보유 종목 매도 신호 → 다음 시가 매도 주문"),
        S("07-timeout-0925", us_now("2026-09-25"), "2026-09-25", "2026-09-25", claude="timeout",
          note="③ 매도 체결 / 팀장 시간 초과 → 폴백 / NEWB 가 처음 70봉"),
        S("08-oserror-0928", us_now("2026-09-28"), "2026-09-28", "2026-09-28", claude="oserror",
          note="팀장 OSError → 폴백"),
        S("09-0929", us_now("2026-09-29"), "2026-09-29", "2026-09-29",
          note="0주 보류(상한 안에서 1주도 못 삼)·매도 신호"),
        S("10-crash-0930", us_now("2026-09-30"), "2026-09-30", "2026-09-30",
          note="⑥ 폭락 → 서킷 브레이커 발동(다음 시가 전량 정리, 정지)"),
        S("11-liquidate-1001", us_now("2026-10-01"), "2026-10-01", "2026-10-01",
          note="⑥ 서킷 정리 매도 체결"),
        S("12-intraday-1002", datetime(2026, 10, 2, 15, 0, tzinfo=ET), "2026-10-02", "2026-10-02",
          note="뉴욕 15:00(16:15 전) 실행: 오늘 봉은 아직 확정 아님 → 어제 봉 기준"),
        S("13-1002", us_now("2026-10-02"), "2026-10-02", "2026-10-02",
          note="정지된 트레이너는 변화 없음 → 저장 안 함"),
        S("14-1005", us_now("2026-10-05"), "2026-10-05", "2026-10-05",
          note="보유+매수 대기 5개(MAX_POSITIONS) → 신규 후보를 보지 않음"),
    ]


def kr_steps():
    S = Step
    return [
        S("01-no-candidates-0921", kr_now("2026-09-21"), "2026-09-21", "2026-09-21",
          note="⑤ 후보 없음 → 세 트레이너 모두 저장 안 함"),
        S("02-first-0922", kr_now("2026-09-22"), "2026-09-22", "2026-09-22",
          note="① 후보 + 팀장 판정 → 주문"),
        S("03-nonzero-0923", kr_now("2026-09-23"), "2026-09-23", "2026-09-23", claude="nonzero",
          note="② 체결 / 팀장 0 아닌 종료 → 폴백"),
        S("04-0924", kr_now("2026-09-24"), "2026-09-24", "2026-09-24",
          note="① 후보·판정 → 012450 매수 주문(다음날부터 정지)"),
        S("05-halt-0925", kr_now("2026-09-25"), "2026-09-25", "2026-09-25",
          note="⑦ 012450 거래정지(원본 Volume=0) → 대기 주문 그대로, 스크리너 오래된 봉 제외"),
        S("06-halt-0928", kr_now("2026-09-28"), "2026-09-28", "2026-09-28", note="⑦ 정지 2일째"),
        S("07-halt-0929", kr_now("2026-09-29"), "2026-09-29", "2026-09-29", note="⑦ 정지 3일째"),
        S("08-after-halt-0930", kr_now("2026-09-30"), "2026-09-30", "2026-09-30",
          note="⑦ 정지 뒤 첫 거래일 시가에 체결"),
        S("09-bad-json-1001", kr_now("2026-10-01"), "2026-10-01", "2026-10-01", claude="bad_json",
          note="⑦ 보유 종목 000270 정지 → 판단 쉼, 스크리너 오래된 봉 제외 / 팀장 JSON 깨짐 → 폴백"),
        S("10-1002", kr_now("2026-10-02"), "2026-10-02", "2026-10-02", note="⑦ 000270 정지 2일째"),
        S("11-stock-data-late-1005", kr_now("2026-10-05"), "2026-10-02", "2026-10-05",
          note="⑦ 종목 시세가 늦음(KS200 만 오늘 봉) → 오래된 후보 제외(team), 보유 판단 쉼, 체결 없음"),
        S("12-1006", kr_now("2026-10-06"), "2026-10-06", "2026-10-06",
          note="늦었던 봉의 시가로 체결"),
        S("13-ks200-2229-1007", kr_now("2026-10-07", 22, 29), "2026-10-07", "2026-10-07",
          note="⑧ 22:29 KST: KS200 오늘 봉은 아직 확정 아님 → 기준 봉은 어제"),
        S("14-ks200-2231-1007", kr_now("2026-10-07", 22, 31), "2026-10-07", "2026-10-07",
          note="⑧ 22:31 KST: KS200 오늘 봉 확정 → 오늘 처리"),
        S("15-crash-1008", kr_now("2026-10-08"), "2026-10-08", "2026-10-08",
          note="⑥ 폭락 → 서킷 브레이커"),
        S("16-no-analysis-1009", kr_now("2026-10-09"), "2026-10-09", "2026-10-09", claude="no_analysis",
          note="⑥ 정리 매도 체결 / 팀장 답에 analysis 없음 → 폴백"),
        S("17-same-bar-1009", kr_now("2026-10-09"), "2026-10-09", "2026-10-09",
          note="④ 같은 봉 다시"),
    ]


SCENARIOS = {
    "us": {"world": us_world, "steps": us_steps, "n": US_N},
    "kr": {"world": kr_world, "steps": kr_steps, "n": KR_N},
}


# ============================ 실행 ============================

@contextlib.contextmanager
def patched(world, claude, state_dir, results_dir):
    """입출력 경계만 바꿔 끼우고, 끝나면 모두 되돌린다."""
    saved = {
        "fdr": sys.modules.get("FinanceDataReader"),
        "state": team.STATE_DIR, "results": main.RESULTS_DIR, "datetime": main.datetime,
        "which": shutil.which, "run": subprocess.run, "key": os.environ.get("ANTHROPIC_API_KEY"),
    }
    sys.modules["FinanceDataReader"] = world.module()
    team.STATE_DIR = state_dir
    main.RESULTS_DIR = results_dir
    shutil.which = claude.which
    subprocess.run = claude.run
    os.environ["ANTHROPIC_API_KEY"] = "golden-dummy-key"
    try:
        yield
    finally:
        if saved["fdr"] is None:
            sys.modules.pop("FinanceDataReader", None)
        else:
            sys.modules["FinanceDataReader"] = saved["fdr"]
        team.STATE_DIR = saved["state"]
        main.RESULTS_DIR = saved["results"]
        main.datetime = saved["datetime"]
        shutil.which = saved["which"]
        subprocess.run = saved["run"]
        if saved["key"] is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved["key"]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _snapshot(folder: Path) -> dict:
    if not folder.exists():
        return {}
    return {_nfc(p.relative_to(folder).as_posix()): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _dumps(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def run_market(market: str):
    """한 시장의 장면을 처음부터 끝까지 돌린다.
    돌려주는 값: (files, info)
      files = {"<시장>/<장면>/<파일>": bytes} ← 골든과 바이트 비교하는 것
        stdout.txt  : team.run 화면 출력
        step.json   : 장면 설정 + 그 실행에서 가짜 claude 가 받은 호출 + 같은 시각 screener.scan() 결과
        state/...   : 실행 뒤 상태 폴더의 파일 전부(team._save 가 쓴 바이트 그대로)
      info = {"world": 가짜 세계, "steps": [장면마다 {"step","stdout","calls","scan","raw","states"}]} ← 가지 확인용"""
    sc = SCENARIOS[market]
    world = sc["world"]()
    claude = FakeClaude(shutil.which, subprocess.run)
    files, steps = {}, []
    with tempfile.TemporaryDirectory(prefix=f"golden-{market}-") as tmp:
        state_dir, results_dir = Path(tmp) / "state", Path(tmp) / "results"
        with patched(world, claude, state_dir, results_dir):
            for step in sc["steps"]():
                world.stock_cut, world.bench_cut = step.stock_cut, step.bench_cut
                main.datetime = make_clock(step.now)
                claude.mode = step.claude
                n_calls = len(claude.calls)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    team.run(sc["n"], market=market)
                calls = claude.calls[n_calls:]
                found, used = screener.scan(sc["n"], market=market)    # 같은 시각·같은 시세로 스크리너만 한 번 더
                scan = {"used": used, "found": found}
                stdout = buf.getvalue()
                raw = _snapshot(state_dir)
                base = f"{market}/{step.label}"
                files[f"{base}/stdout.txt"] = stdout.encode("utf-8")
                files[f"{base}/step.json"] = _dumps({
                    "step": {"label": step.label, "now": step.now.isoformat(), "stock_cut": step.stock_cut,
                             "bench_cut": step.bench_cut, "claude": step.claude, "note": step.note},
                    "claude_calls": calls,
                    "scan": scan,
                })
                for rel, data in raw.items():
                    files[f"{base}/state/{rel}"] = data
                steps.append({"step": step, "stdout": stdout, "calls": calls, "scan": scan, "raw": raw,
                              "states": {k: json.loads(v) for k, v in raw.items()}})
    return files, {"world": world, "steps": steps}


def run_all():
    files, infos = {}, {}
    for m in SCENARIOS:
        f, info = run_market(m)
        files.update(f)
        infos[m] = info
    return files, infos


# ============================ 가지 확인 ============================
# 장면이 정말 그 가지를 지났는지 확인한다(골든을 만들 때 꼭 돈다). 결과 파일에는 아무것도 더하지 않는다.

TRAINER_IN_PROMPT = re.compile(r"너는 '([^']+)' 트레이너의 팀장")


def _state_key(market, trainer):
    return f"team_{trainer}.json" if market == "us" else f"kr/team_{trainer}.json"


def _signals_on_last_bar(df):
    """이 시세의 마지막 봉에서 매수 신호를 내는 트레이너(진짜 브레인으로 계산, 확인용)."""
    return [t for t, cls in screener.BRAINS.items() if cls().decide(cls().add_indicators(df), None)[0] == "매수"]


def _confirmed(world, market, code, now, cut):
    raw = world.frames[code].loc[pd.Timestamp(team.START):pd.Timestamp(cut)]
    return main.confirmed_bars(raw, now, market)


def _kind_name(kind):
    if kind is None:
        return "missing"
    v, c = kind
    return f"{v}:{c!r}"


def _leader_effects(market, steps):
    """팀장 답 종류별로 실제 효과(주문·hold 보류·확신도 보류·빠짐)를 모은다."""
    seen = {}
    for st in steps:
        for call in st["calls"]:
            if "kinds" not in call:
                continue
            m = TRAINER_IN_PROMPT.search(call["prompt"] or "")
            trainer = m.group(1)
            state = st["states"].get(_state_key(market, trainer))
            if state is None:
                continue
            bar = state["last_date"]
            for code, kind in call["kinds"].items():
                kind = tuple(kind) if kind else None
                ordered = any(o["code"] == code and o["action"] == "매수" for o in state["pending"])
                logs = [e for e in state["wallet"]["log"]
                        if e["종류"] == "보류" and e["종목"] == code and e["시각"] == bar]
                hold = any(e["사유"] == "팀장 hold" for e in logs)
                low = any(e["사유"].startswith("팀장 확신도 낮음") for e in logs)
                eff = "ordered" if ordered else "hold" if hold else "low_conv" if low else "dropped"
                seen.setdefault(_kind_name(kind), set()).add(eff)
    return seen


def check_branches(market: str, info: dict) -> list[str]:
    """장면이 지나야 하는 가지를 확인한다. 문제 목록(빈 목록이면 통과)."""
    world, steps = info["world"], info["steps"]
    by = {st["step"].label: st for st in steps}
    bad = []

    def need(ok, msg):
        if not ok:
            bad.append(f"[{market}] {msg}")

    def prev_of(label):
        i = [st["step"].label for st in steps].index(label)
        return steps[i - 1]

    # 공통: 모든 claude 호출은 환경을 넘기고 ANTHROPIC_API_KEY 를 뺐다(구독 강제), 시간 제한은 analyst.TIMEOUT
    for st in steps:
        for c in st["calls"]:
            need(c["env_given"] and c["api_key_in_env"] is False, f"{st['step'].label}: API 키가 claude 환경에 남음")
            need(c["timeout"] == analyst.TIMEOUT and c["args"] == ["claude", "-p"], f"{st['step'].label}: 호출 모양")
    # 공통: 팀장 폴백 모드마다 그 모드로 실제 호출(또는 claude 없음이면 호출 0)이 있었다
    for st in steps:
        mode = st["step"].claude
        if mode == "answer":
            continue
        if mode == "missing":
            need(not st["calls"] and "트레이너별 후보" in st["stdout"]
                 and any(st["scan"]["found"].values()), f"{st['step'].label}: claude 없음 장면에 후보가 없거나 호출이 있음")
        else:
            need(st["calls"] and all(c["mode"] == mode for c in st["calls"]),
                 f"{st['step'].label}: 팀장 {mode} 호출이 없음")
    # ① 팀장 판정 종류별 효과
    eff = _leader_effects(market, steps)
    for kind, want in (("buy:'0.9'", "ordered"), ("hold:0.8", "hold"), ("veto:0.9", "dropped"),
                       ("buy:0.3", "low_conv"), ("buy:'모름'", "ordered"), (" VETO:0.9", "ordered"), ("Hold:0.7", "ordered")):
        need(want in eff.get(kind, set()), f"① 팀장 답 {kind} → {want} 를 못 봄 (본 것: {eff.get(kind)})")
    # ④ 같은 봉 다시: 상태 파일이 바이트까지 그대로
    for st in steps:
        if "same-bar" in st["step"].label or "2229" in st["step"].label:
            need(st["raw"] == prev_of(st["step"].label)["raw"], f"④ {st['step'].label}: 같은 봉 다시인데 상태가 바뀜")
            need("이미 처리됨" in st["stdout"], f"④ {st['step'].label}: '이미 처리됨' 출력 없음")
    need(any("스캔 생략 (멱등)" in st["stdout"] for st in steps), "④ 스캔 생략(세 트레이너 모두 처리됨) 장면 없음")
    # ⑤ 후보·보유·주문 없음 → 저장 안 함 (그 트레이너 파일은 그대로)
    saw5 = False
    for i, st in enumerate(steps[1:], 1):
        for t in TRAINERS:
            if f"{t}: 후보·보유·주문 없음 → 저장 안 함" in st["stdout"]:
                saw5 = True
                k = _state_key(market, t)
                need(st["raw"].get(k) == steps[i - 1]["raw"].get(k), f"⑤ {st['step'].label} {t}: 저장 안 함인데 파일이 바뀜")
    need(saw5, "⑤ '후보·보유·주문 없음 → 저장 안 함' 장면 없음")
    # ② 다음날 시가 체결: 매수 로그 날짜 = 처리한 봉, 매수가 = 그날 원본 시가(종목 행 Open)
    fills = 0
    for st in steps:
        for t in TRAINERS:
            s = st["states"].get(_state_key(market, t))
            if not s:
                continue
            for code, pos in s["positions"].items():
                if pos["buy_date"] == s["last_date"]:
                    o = float(world.frames[code].loc[pd.Timestamp(pos["buy_date"]), "Open"])
                    need(pos["buy_price"] == o, f"② {st['step'].label} {t} {code}: 매수가 {pos['buy_price']} ≠ 시가 {o}")
                    fills += 1
    need(fills >= 3, f"② 다음날 시가 체결이 너무 적음({fills})")
    # ③ 매도 신호 → 다음 시가 매도 (서킷 아닌 매도)
    saw3 = False
    for i, st in enumerate(steps[1:], 1):
        for t in TRAINERS:
            before = steps[i - 1]["states"].get(_state_key(market, t)) or {"pending": []}
            after = st["states"].get(_state_key(market, t))
            if not after:
                continue
            for o in before["pending"]:
                if o["action"] == "매도" and o["reason"] != "서킷 브레이커" and o["code"] not in after["positions"] \
                        and any(e["종류"] == "매도" and e["종목"] == o["code"] and e["시각"] == after["last_date"]
                                for e in after["wallet"]["log"]):
                    saw3 = True
    need(saw3, "③ 매도 신호 → 다음 시가 매도 체결 장면 없음")
    # ⑥ 서킷 발동 → 다음 시가 전량 정리, 정지
    crash = [st for st in steps if "crash" in st["step"].label]
    need(len(crash) == 1 and "🛑서킷" in crash[0]["stdout"], "⑥ 폭락 장면에서 서킷이 안 걸림")
    if crash:
        nxt = steps[steps.index(crash[0]) + 1]
        stopped = [t for t in TRAINERS if (crash[0]["states"].get(_state_key(market, t)) or {}).get("stopped")]
        need(stopped, "⑥ 정지된 트레이너 없음")
        for t in stopped:
            s0 = crash[0]["states"][_state_key(market, t)]
            need(s0["pending"] and all(o["action"] == "매도" and o["reason"] == "서킷 브레이커" for o in s0["pending"]),
                 f"⑥ {t}: 정리 주문이 전부 '서킷 브레이커' 매도가 아님")
            s1 = nxt["states"][_state_key(market, t)]
            need(not s1["positions"] and not s1["pending"] and s1["stopped"], f"⑥ {t}: 다음 시가에 전량 정리 안 됨")
    # 스크리너: 받기 실패 종목은 건너뛰고, 70봉 미만은 세지 않음
    used = [st["scan"]["used"] for st in steps]
    need(len(set(used)) == 2 and used == sorted(used), f"스크리너 used 가 70봉 경계에서 한 번 늘어야 함: {used}")

    if market == "us":
        # 오래된 봉(STAL): 마지막 봉에 매수 신호가 있는데 후보에서 빠짐
        st = steps[0]
        df = _confirmed(world, "us", "STAL", st["step"].now, st["step"].stock_cut)
        need(_signals_on_last_bar(df), "STAL 마지막 봉에 매수 신호가 없음(오래된 봉 제외를 못 봄)")
        need(all(c["code"] != "STAL" for s in steps for cs in s["scan"]["found"].values() for c in cs),
             "STAL 이 후보로 나옴")
        intr = by["12-intraday-1002"]
        need("마지막 확정 봉 2026-10-01" in intr["stdout"], "뉴욕 15:00 실행인데 오늘 봉(10-02)을 썼음")
    else:
        # ⑦-1 정지 중 대기 주문은 그대로, 정지 뒤 첫 거래일 시가에 체결
        for lab in ("05-halt-0925", "06-halt-0928", "07-halt-0929"):
            s = by[lab]["states"][_state_key("kr", "스프린터")]
            need(any(o["code"] == "012450" and o["action"] == "매수" and o["signal_date"] == "2026-09-24"
                     for o in s["pending"]), f"⑦ {lab}: 정지 중 대기 주문이 없음")
            need("012450" not in s["positions"], f"⑦ {lab}: 정지일에 체결됨")
        s = by["08-after-halt-0930"]["states"][_state_key("kr", "스프린터")]
        pos = s["positions"].get("012450")
        need(pos is not None and pos["buy_date"] == "2026-09-30"
             and pos["buy_price"] == float(world.frames["012450"].loc[pd.Timestamp("2026-09-30"), "Open"]),
             "⑦ 정지 뒤 첫 거래일(09-30) 시가 체결이 아님")
        # ⑦-2 정지 중 보유 종목: 판단 쉼, 보유일수 그대로
        d8 = by["08-after-halt-0930"]["states"][_state_key("kr", "마라토너")]["positions"]["000270"]["days_held"]
        d10 = by["10-1002"]["states"][_state_key("kr", "마라토너")]["positions"]["000270"]["days_held"]
        need("판단 쉼 000270" in by["09-bad-json-1001"]["stdout"] and "판단 쉼 000270" in by["10-1002"]["stdout"],
             "⑦ 정지 중 보유 종목 '판단 쉼' 출력 없음")
        need(d8 == d10, f"⑦ 정지 중 보유일수가 늘어남 ({d8} → {d10})")
        # ⑦-3 스크리너 오래된 봉 제외: 정지 종목의 마지막 거래 봉에 매수 신호가 있는데 후보에서 빠짐
        for lab, code in (("05-halt-0925", "012450"), ("09-bad-json-1001", "000270")):
            st = by[lab]
            df = _confirmed(world, "kr", code, st["step"].now, st["step"].stock_cut)
            need(df.index[-1].date().isoformat() < st["step"].stock_cut, f"⑦ {lab}: {code} 가 정지가 아님")
            need(_signals_on_last_bar(df), f"⑦ {lab}: {code} 마지막 봉에 매수 신호가 없음")
            need(all(c["code"] != code for cs in st["scan"]["found"].values() for c in cs),
                 f"⑦ {lab}: 정지 종목 {code} 가 후보로 나옴")
        # ⑦-4 team 의 오래된 후보 제외(종목 시세가 기준 봉보다 늦음)
        need("(기준 봉에 거래 없음)" in by["11-stock-data-late-1005"]["stdout"], "⑦ team 오래된 후보 제외 출력 없음")
        # ⑧ KS200 22:30 전후
        need("마지막 확정 봉 2026-10-06" in by["13-ks200-2229-1007"]["stdout"], "⑧ 22:29 인데 KS200 오늘 봉을 씀")
        need(all(by["14-ks200-2231-1007"]["states"][_state_key("kr", t)]["last_date"] == "2026-10-07"
                 for t in TRAINERS), "⑧ 22:31 에 오늘 봉(10-07)을 처리하지 않음")
        need(not by["01-no-candidates-0921"]["raw"], "⑤ 첫날 후보 없음인데 파일이 생김")
    return bad


def read_dir(folder: Path, skip=("README.md",)) -> dict:
    """골든 폴더를 {상대경로: bytes} 로 읽는다(README 는 사람용이라 뺌). 맥의 한글 파일 이름(NFD)도 NFC 로 맞춘다."""
    return {k: v for k, v in _snapshot(Path(folder)).items() if k not in skip}


def write_dir(files: dict, folder: Path):
    folder = Path(folder)
    for rel, data in files.items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="골든 장면 실행기")
    ap.add_argument("--write", help="결과를 쓸 폴더")
    ap.add_argument("--check", action="store_true", help="가지 확인만")
    ap.add_argument("--show", help="이 시장의 화면 출력을 찍는다(개발용)")
    a = ap.parse_args(argv)
    if a.show:
        _, info = run_market(a.show)
        for nt in info["steps"]:
            print("#" * 20, nt["step"].label, nt["step"].claude)
            print(nt["stdout"])
            print("scan used", nt["scan"]["used"], {t: [c["code"] for c in cs] for t, cs in nt["scan"]["found"].items()})
        return 0
    files, infos = run_all()
    problems = [p for m, info in infos.items() for p in check_branches(m, info)]
    if problems:
        print("가지 확인 실패:\n  " + "\n  ".join(problems))
        return 1
    counts = ", ".join(f"{m} {len(info['steps'])}장면" for m, info in infos.items())
    print(f"가지 확인 통과 ({counts})")
    if a.write:
        write_dir(files, Path(a.write))
        print(f"{len(files)}개 파일을 {a.write} 에 썼어요")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
