"""
h1.py - H1 포워드 모의매매 엔진 (설계 docs/h1-forward-design.md 3판, 단계 2b-1 "엔진")
------------------------------------------------------------------
무엇을 하나 (주식 초보용 설명)
- H1 = "쉬는 돈을 지수에" 규칙. 트레이너가 주식에 쓰지 않은 돈을 현금으로 두지 않고
  지수(미국 SPY, 국내 KOSPI 200 가격지수 KS200)를 소수 단위로 사 둔다. 주식을 살 때 모자란 만큼만 지수를 판다.
- 같은 날·같은 후보·같은 팀장 판정으로 장부 두 개를 나란히 돌린다.
    A1 = 쉬는 돈을 지수로(= H1)      A0 = 쉬는 돈을 현금으로(비교용 그림자 장부. 운영 team.py 장부가 아님)
- 진짜 돈·진짜 주문은 없다. 장부(가짜 지갑 + 기록)만 쓴다.
- 계산 식과 순서는 연구 시뮬레이터 R2 sim_team.py 의 A1 과 같다
  (_open·_fill_sell·_fill_buy·_raise_cash·_sweep_to_index·_idx_net_per_unit·KR_SELL_TAX·SWEEP_MIN).

이 파일에 있는 것 (단계 2b-1)
- 상수(§3.3), 예외 4종(H1LogicError·H1DataProblem·H1Refused·H1PreconditionError), idle_code·kr_sell_tax·
  rule_constants·next_open·ledger_fingerprint·decision_key·env_key
- IdleBar(대기 자산 그날 시가·종가), StrictFrames(없는 종목을 찾으면 바로 L6 오류인 시세 묶음), Fetched(받은 시세 모양)
- DecisionLog: 팀장 판정 기록(추가만 하는 JSONL, 줄마다 fsync, read_only 로 읽기만 할 수 있음)
- Leader: 판정 기록을 거쳐 팀장(claude)에게 묻는 창구(기록에 없는 후보만, 묻기 직전마다 시각 재확인)
- 새 장부 만들기·장부 ↔ JSON dict 바꾸기(엄격: NaN·inf·항목 모양까지, json_loads_strict)
- delist_registrations(장부 corp_actions 의 상장폐지 등록), apply_split(분할 ⑦-2 적용, 순수 함수)
- H1Day: team.run_trainer(h1=…) 에 넘기는 하루 처리기(시가 체결 a~e, 팀장 결과 버퍼, 종가 기록).
  처리 중 찾은 장부 논리 오류는 예외 대신 Problem 으로 모은다(봉 처리를 끝까지 해서 지문이 남게)
- run_bar: 봉 하나를 장부 6개(A0·A1 × 트레이너 3명)에 처리하고 h1_check 로 점검한 결과를 돌려준다

2b-1 독립 검토(docs/h1-review-2b1.md) B-1~B-10 반영: 상장폐지 정보는 장부 corp_actions 하나, 분할 적용 함수, 엔진 L 은
Problem 으로(끝까지 못 가는 L 예외는 번호·지문을 붙임), 사전 조건 위반은 H1PreconditionError(L 아님), bad_verdict 폴백,
DecisionLog(read_only), 엄격 읽기 보강, S 의 prev_cal_date 확인.

다음 단계(2b-2)에서 붙일 것: 실행 명령(start·run·restart·corp-action·amend-rules·status), 파일 저장·커밋 지점(HEAD)·
백업·잠금·관문(code_hash·env)·시세 받기(fetch)·자료 점검(D1·D2·D4~D7)·요약 출력. 여기서는 파일을 쓰지 않는다
(판정 기록 추가만 예외 — 장부보다 먼저 디스크에 있어야 하므로, 설계 §3.6).

import 관계: h1 → team(그 밖의 운영 모듈) / team 은 h1 을 import 하지 않는다. h1_check 와 h1 은 서로를 모듈째로만
import 한다(모듈을 읽는 순간에는 서로의 이름을 쓰지 않음 → 어느 쪽을 먼저 읽어도 됨).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import analyst
import h1_check
import main
import markets
import screener
import team
from paper_wallet import Holding, PaperWallet, shares_within_cap
from risk_guard import CircuitBreaker

# ============================ 상수 (설계 §3.3, §2.2 ⑩) ============================

REPO = Path(__file__).resolve().parent
H1_DIR = team.STATE_DIR / "h1"                    # state/h1 (F1) — 2b-2 의 파일 저장이 쓴다
ARMS = ("A0", "A1")                               # A0 쉬는 돈=현금(그림자), A1 쉬는 돈=지수(H1)
TRAINERS = ("마라토너", "스프린터", "파이오니어")      # 처리 순서도 이 순서(설계 §2.3-3)
TOTALS = {"us": 100_000, "kr": 100_000_000}       # F2: 시장마다 총액
SCHEMA = {"us": "h1-us-2", "kr": "h1-kr-2"}
N_UNIVERSE = 40                                   # Q7: 미국 종목군 수
SWEEP_MIN = 1.0                                   # R2 SWEEP_MIN: 남은 현금이 1(달러/원) 이상이면 지수로
SHORT_MARGIN = 1e-9                               # R2 R6·_raise_cash 의 여유
SWEEP_SHRINK = (1e-12, 1e-9, 1e-6)                # R2 _sweep_to_index 의 줄임 순서
LEDGER_BREAKER = (float("inf"), float("inf"))     # Q1: 장부 서킷 끔(절대 안 걸림)
SHADOW_BREAKER = (main.CONFIG["서킷브레이커"]["누적한도"], main.CONFIG["서킷브레이커"]["일일한도"])
KR_SELL_TAX = (("0000-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
               ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
               ("2026-01-01", 0.0020))            # STAGE0 §1.2 (Q9), 체결일 기준 — R2 표와 같은 값
WINDOW_BARS = 63
MAX_LATE_BATCH = 5
MAX_LATE_TOTAL = 10
MAX_RESTARTS = 2
DEADLINE = "2027-06-30"
FALLBACK_FLAG = 0.20
RETRO_TOL = 1e-6
RETRO_DAYS = 5
LOCK_WAIT_S = 1800
BACKUPS_KEEP = 10
CAL_PROBE = {"us": ("AAPL", "MSFT"), "kr": ("005930", "000660")}
CAL_HOLE_RATIO = 0.5                              # D5: 종목군 절반 이상이 거래한 날
NEXT_OPEN = {"us": ("09:30", "America/New_York"), "kr": ("09:00", "Asia/Seoul")}
FINGERPRINT_VERSION = 1                           # ledger_fingerprint 계산 방식 판
CODE_FILES = ("team.py", "h1.py", "h1_check.py", "h1_report.py", "h1_replay.py",
              "main.py", "markets.py", "paper_wallet.py",
              "screener.py", "analyst.py", "risk_guard.py", "metrics.py",
              "marathoner_brain.py", "sprinter_brain.py", "pioneer_brain.py",
              "prompts/마라토너.md", "prompts/스프린터.md", "prompts/파이오니어.md")
# EPS_CASH·EPS_REL 은 h1_check.py 에 있고, rule_constants() 가 함께 적는다(§2.2 ⑩)
ENV_PACKAGES = ("pandas", "numpy", "ta", "FinanceDataReader")   # + python 버전

# 장부(트레이너 한 명) 칸. "schema" 는 JSON 에만 있고 메모리의 장부에는 없다.
LEDGER_KEYS = ("schema", "h1", "wallet", "positions", "pending", "prev_value", "stopped", "last_date",
               "start_cash", "start_date", "orders", "fills", "skips", "corp_actions", "days")
WALLET_KEYS = ("name", "cash", "currency", "fee_rate", "sell_tax_rate", "slippage", "holdings", "log")
H1_HEAD_KEYS = ("market", "arm", "trainer", "idle_code", "idle_mode", "restart_no", "code_hash", "env", "updated_at")
DAY_META_KEYS = ("run_at", "mode", "late", "late_calls", "code_hash", "env")   # 지문에서 빼는 실행 메모 칸
FP_KEEP = ("wallet", "positions", "pending", "prev_value", "stopped", "last_date", "start_cash", "start_date",
           "orders", "fills", "skips", "corp_actions", "days")
FP_WALLET_KEEP = ("cash", "currency", "fee_rate", "sell_tax_rate", "slippage", "holdings", "log")
LEADER_MODES = ("llm", "late", "replay")


# ============================ 예외 ============================

class H1LogicError(Exception):
    """장부 논리 오류(L 등급) → 종료 코드 2. 그 봉은 저장하지 않는다. code: "L11" 처럼 점검 번호(알면)."""
    exit_code = 2

    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class H1DataProblem(Exception):
    """자료 문제(D 등급) → 종료 코드 4. 그 봉은 저장하지 않고 다음 실행이 다시 한다. kind: "D1"…"D6"."""
    exit_code = 4

    def __init__(self, kind, msg):
        super().__init__(f"{kind}: {msg}")
        self.kind = kind


class H1Refused(Exception):
    """실행 거절 → 종료 코드 3·5·6·8 (code 속성). 2b-2 의 관문·잠금·밀린 봉·장부 없음이 쓴다."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class H1PreconditionError(ValueError):
    """run_bar 를 부르는 쪽(h1.run·start·재현)이 지켜야 할 **사전 조건**이 어긋남 (2b-1 검토 B-3·B-10).
    장부 내용이 틀린 것이 아니라 "넘긴 인자(달력·봉·지수 봉·정지 목록)가 서로 맞지 않는" 것이라 L 로 세지 않는다.
    고르는 기준: 장부를 한 줄도 보지 않고, 넘겨받은 인자끼리 또는 인자와 장부의 날짜만 비교해서 알 수 있는 모순.
      - 처리할 봉 t ≤ 장부 last_date (이미 처리한 봉 — 2b-2 의 멱등 확인이 먼저 걸러야 함)
      - prev_cal_date 가 없거나, 장부 last_date(S 이면 달력의 S 전 거래일)와 다름 (빠진 봉·달력 문제 → 2b-2 의 D4·D5 가 먼저)
      - 달력에 t 가 없거나 달력의 t 앞 거래일 ≠ prev_cal_date
      - IdleBar 의 코드·날짜가 그 시장 대기 자산·t 와 다름
      - halted 에 넣은 종목에 t 확정 행이 있음(정지 판정과 시세가 서로 다름 → 자료를 다시 받아야 함)
      - delist 인자가 장부 corp_actions 의 상장폐지 등록과 다름
    2b-2 는 이 예외를 종료 코드 4(자료 문제와 같이 그 봉 저장 안 함, 다음 실행이 다시)로 다루고 runs.jsonl 에 적으면 된다."""


# ============================ 작은 함수 ============================

def idle_code(market) -> str:
    """대기 자산 코드 = 그 시장 벤치마크(F4): 미국 "SPY", 국내 "KS200"."""
    return markets.MARKETS[_mkey(market)].benchmark


def _mkey(market) -> str:
    return main.mkt(market).key


def kr_sell_tax(date: str) -> float:
    """국내 주식 매도세율(체결일 'YYYY-MM-DD' 기준, STAGE0 §1.2 — R2 sim_team.kr_sell_tax 와 같은 식).
    지수(KS200) 매도는 이 표를 쓰지 않고 0 이다."""
    rate = KR_SELL_TAX[0][1]
    for since, r in KR_SELL_TAX:
        if date >= since:
            rate = r
    return rate


def stock_sell_tax(market, date: str) -> float:
    """주식 한 건 매도세율: 국내는 날짜별 표, 미국은 0."""
    return kr_sell_tax(date) if _mkey(market) == "kr" else 0.0


def decision_key(market, date, trainer, code) -> str:
    """판정 기록 열쇠 (Q12). 예) "us|2026-11-09|마라토너|AAPL"."""
    return f"{_mkey(market)}|{date}|{trainer}|{code}"


def order_id(order) -> str:
    """주문 기록 id = "<신호일>|<종목>|<매수/매도>" (장부 안에서 하나뿐, L5)."""
    return f"{order['signal_date']}|{order['code']}|{order['action']}"


def env_key(env) -> str:
    """env dict(파이썬·라이브러리 버전)의 지문. L22 의 허용 목록 (code_hash, env_key) 에 쓴다."""
    blob = json.dumps(env or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def fmt_units(u) -> str:
    """지수 소수 단위를 화면에 찍을 때만 소수 6자리로(저장·계산은 float 그대로, 설계 F3·R4)."""
    return f"{float(u):.6f}"


def _check_iso(d, what="날짜"):
    ok = isinstance(d, str) and len(d) == 10
    if ok:
        try:
            ok = _date.fromisoformat(d).isoformat() == d
        except ValueError:
            ok = False
    if not ok:
        raise ValueError(f"{what}는 'YYYY-MM-DD' 10자리여야 해요 (받은 값: {d!r})")


def next_open(market, bar_date: str) -> datetime:
    """봉 bar_date 다음 평일의 장 시작 시각(시간대 있음). 미국 09:30 뉴욕, 국내 09:00 서울.
    휴장일은 따지지 않는다(그래서 조금 이르게 끊는 쪽 — 설계 §2.3-2)."""
    _check_iso(bar_date, "bar_date")
    hhmm, tzname = NEXT_OPEN[_mkey(market)]
    d = _date.fromisoformat(bar_date) + timedelta(days=1)
    while d.weekday() >= 5:            # 토(5)·일(6) → 월요일
        d += timedelta(days=1)
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo(tzname))


def _local_now():
    return datetime.now().astimezone()


def _aware(t):
    if not isinstance(t, datetime) or t.tzinfo is None:
        raise ValueError("시계(now)는 시간대가 있는 datetime 을 돌려줘야 해요")
    return t


def rule_constants(market) -> dict:
    """§2.2 ⑩ 고정 값. start 가 meta.rules 에 적고, 매 실행 지금 코드 값과 비교한다(다르면 종료 코드 3, 2b-2)."""
    mk = _mkey(market)
    m = markets.MARKETS[mk]
    return {
        "market": mk,
        "total": TOTALS[mk],
        "ratios": dict(main.CONFIG["배분비율"]),
        "caps": dict(main.CONFIG["종목상한"]),
        "max_positions": team.MAX_POSITIONS,
        "conv_min": team.CONV_MIN,
        "fee_rate": m.fee_rate,
        "slippage": m.slippage,
        "stock_sell_tax": [list(x) for x in KR_SELL_TAX] if mk == "kr" else [["0000-01-01", m.sell_tax_rate]],
        "idle_sell_tax": 0.0,
        "ledger_breaker": "off",
        "shadow_breaker": list(SHADOW_BREAKER),
        "sweep_min": SWEEP_MIN,
        "short_margin": SHORT_MARGIN,
        "sweep_shrink": list(SWEEP_SHRINK),
        "idle_code": idle_code(mk),
        "n_universe": N_UNIVERSE,
        "window_bars": WINDOW_BARS,
        "max_late_batch": MAX_LATE_BATCH,
        "max_late_total": MAX_LATE_TOTAL,
        "max_restarts": MAX_RESTARTS,
        "deadline": DEADLINE,
        "fallback_flag": FALLBACK_FLAG,
        "retro_tol": RETRO_TOL,
        "retro_days": RETRO_DAYS,
        "cal_probe": list(CAL_PROBE[mk]),
        "cal_hole_ratio": CAL_HOLE_RATIO,
        "next_open": list(NEXT_OPEN[mk]),
        "eps_cash": h1_check.EPS_CASH,
        "eps_rel": h1_check.EPS_REL,
        "fingerprint_version": FINGERPRINT_VERSION,
    }


# ============================ 장부 내용 지문 ============================

def _plain_wallet(w):
    if isinstance(w, PaperWallet):
        return asdict(w)
    return w


def ledger_fingerprint(states: dict) -> str:
    """장부 내용 지문 (설계 §3.3, 2차 검토 R2-1). states = {arm: {trainer: st}} (한 시장의 장부 6개).
    실행 메모 칸(schema, h1 머리 전체, 하루 기록의 run_at·mode·late·late_calls·code_hash·env)과 지갑 이름을 빼고
    매매 내용만 남겨 정렬 JSON 의 sha256 을 낸다. 코드를 고쳐도 매매가 같으면 같은 값이 나온다.
    float 는 파이썬 repr 그대로라 비트가 같으면 글자도 같다. NaN·inf 가 있으면 ValueError(allow_nan=False)."""
    ledgers = {}
    for arm, by_trainer in states.items():
        for tname, st in by_trainer.items():
            missing = [k for k in FP_KEEP if k not in st]
            if missing:
                raise H1LogicError(f"{arm}/{tname}: 지문에 필요한 칸이 없음 {missing}", code="L24")
            w = _plain_wallet(st["wallet"])
            copy = {k: st[k] for k in FP_KEEP if k != "wallet"}
            copy["wallet"] = {k: w[k] for k in FP_WALLET_KEEP}
            copy["days"] = [{k: v for k, v in row.items() if k not in DAY_META_KEYS} for row in st["days"]]
            ledgers[f"{arm}/{tname}"] = copy
    blob = json.dumps({"v": FINGERPRINT_VERSION, "ledgers": ledgers}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ============================ 시세 자료형 ============================

@dataclass(frozen=True)
class IdleBar:
    """대기 자산(지수) 그날 한 줄: 코드·날짜·시가·종가. 시가로 사고팔고, 종가로 평가한다."""
    code: str
    date: str
    open: float
    close: float


@dataclass
class Fetched:
    """시세 받기 결과(받기 함수 fetch 는 2b-2). df = main.confirmed_bars 를 거친 확정 시세,
    halt_dates = 국내 원본에서 거래량 0 인 날짜(거래정지일). 미국은 빈 집합."""
    df: object
    halt_dates: frozenset


class StrictFrames(dict):
    """team._prices 에 넘기는 엄격한 시세 묶음 (설계 §2.3 준비 7, 검토 m6).
    - `code in frames` 는 늘 True → team._prices 가 인터넷으로 받으러 가지 않는다.
    - 없는 종목을 꺼내면 H1LogicError(code="L6"). 보유·대기 종목은 run_bar 사전 확인에서 이미 D2·D3 으로 걸리므로
      여기까지 왔다면 엔진의 논리 오류다(2b-1 검토 B-3)."""

    def __contains__(self, key):
        return True

    def __missing__(self, key):
        raise H1LogicError(f"엄격 시세 묶음에 없는 종목 {key!r} 을 찾았어요(받아 둔 종목만 쓸 수 있음)", code="L6")


def _dates_of(df):
    return [x.date().isoformat() for x in df.index]


def cut_frame(df, t):
    """시세를 t 이하 날짜만 남긴다(미래 봉을 보지 않게). None 은 그대로 None."""
    if df is None:
        return None
    return df[[d <= t for d in _dates_of(df)]]


def _row_at(df, t):
    """df 의 날짜 t 행(없으면 None). 같은 날짜가 둘이면 자료 문제."""
    hits = [i for i, d in enumerate(_dates_of(df)) if d == t]
    if not hits:
        return None
    if len(hits) > 1:
        raise H1DataProblem("D3", f"같은 날짜 {t} 행이 {len(hits)}개")
    return df.iloc[hits[0]]


# ============================ 판정 기록 (§3.6) ============================

def _jsonable(v):
    """JSON 으로 그대로 적을 수 있으면 그대로, 아니면(NaN·이상한 객체) repr 글자로."""
    try:
        json.dumps(v, allow_nan=False, ensure_ascii=False)
        return v
    except (TypeError, ValueError):
        return repr(v)


class DecisionLog:
    """팀장 판정 기록 state/h1/analyst_cache.jsonl — 한 줄 = 기록 하나, 추가만 한다(고치기·지우기 없음).

    읽을 때(만들 때)
    - 같은 열쇠가 두 번 → H1LogicError(code="L18")
    - 마지막이 아닌 줄이 깨짐(JSON 아님·열쇠 없음) → H1LogicError(code="L24")
    - 마지막 줄만 반쯤 쓰임(줄바꿈으로 끝나지 않음 = 쓰는 중 꺼짐) → self.truncated 에 {"bytes", "preview"} 로 남기고
      (2b-2 가 runs.jsonl 에 적음) 그 줄은 읽지 않는다. 그 줄은 아직 어느 장부에도 안 쓰였다.
      read_only=False(잠금을 잡은 run·start 만)일 때만 파일에서 실제로 잘라 낸다. read_only=True(status·보고서·재현 비교)는
      파일을 건드리지 않고 알리기만 한다(2b-1 검토 B-8). read_only 로 연 기록에는 append 할 수 없다.
    append(records): 줄마다 쓰기 + fsync. 이미 있는 열쇠면 H1LogicError(L18) — 아무것도 쓰지 않는다.
    prefix_digest(n): (줄 수, 앞 n 줄 sha256). HEAD 에 적어 두고 다음 실행에서 지난 줄이 바뀌었는지 본다(L18)."""

    def __init__(self, path, read_only=False):
        self.path = Path(path)
        self.read_only = bool(read_only)
        self.truncated = None
        self._records = []
        self._by_key = {}
        self._lines = []
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        parts = data.split(b"\n")
        tail = parts.pop()                      # 마지막 줄바꿈 뒤(정상이면 b"")
        for i, raw in enumerate(parts, 1):
            try:
                rec = json.loads(raw)
            except (UnicodeDecodeError, ValueError):
                raise H1LogicError(f"판정 기록 {self.path.name} {i}번째 줄이 깨졌어요(마지막 줄이 아님)", code="L24")
            if not isinstance(rec, dict) or not isinstance(rec.get("key"), str):
                raise H1LogicError(f"판정 기록 {i}번째 줄에 열쇠(key)가 없어요", code="L24")
            if rec["key"] in self._by_key:
                raise H1LogicError(f"판정 기록에 같은 열쇠가 두 번: {rec['key']} ({i}번째 줄)", code="L18")
            self._add(rec, raw + b"\n")
        if tail:
            if not self.read_only:
                keep = len(data) - len(tail)
                with open(self.path, "r+b") as f:
                    f.truncate(keep)
                    f.flush()
                    os.fsync(f.fileno())
            self.truncated = {"bytes": len(tail), "preview": tail[:200].decode("utf-8", "replace"),
                              "cut": not self.read_only}

    def _add(self, rec, line: bytes):
        self._records.append(rec)
        self._by_key[rec["key"]] = rec
        self._lines.append(line)

    def __len__(self):
        return len(self._records)

    def records(self) -> list:
        """기록 전부(파일 순서). 돌려받은 dict 를 고치지 말 것."""
        return list(self._records)

    def get(self, key):
        rec = self._by_key.get(key)
        return None if rec is None else dict(rec)

    def append(self, records) -> None:
        if self.read_only:
            raise ValueError("읽기 전용으로 연 판정 기록에는 쓸 수 없어요(read_only=True)")
        recs = list(records)
        seen = set()
        for r in recs:
            if not isinstance(r, dict) or not isinstance(r.get("key"), str):
                raise H1LogicError("판정 기록 한 줄은 key 가 있는 dict 여야 해요", code="L18")
            if r["key"] in self._by_key or r["key"] in seen:
                raise H1LogicError(f"이미 있는 판정 기록 열쇠를 다시 쓰려 함: {r['key']}", code="L18")
            seen.add(r["key"])
        lines = [(json.dumps(r, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
                 for r in recs]
        if not recs:
            return
        new = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            for line in lines:
                view = memoryview(line)
                while view:
                    n = os.write(fd, view)
                    view = view[n:]
                os.fsync(fd)                         # 줄마다 디스크에 (장부보다 먼저)
                self._add(json.loads(line), line)
        finally:
            os.close(fd)
        if new:                                      # 새 파일이면 폴더 항목도 디스크에
            try:
                dfd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass

    def prefix_digest(self, n=None) -> tuple:
        """(줄 수, 앞 n 줄(없으면 전부) 바이트의 sha256)."""
        lines = self._lines if n is None else self._lines[:n]
        return len(lines), hashlib.sha256(b"".join(lines)).hexdigest()


# ============================ 팀장 창구 (Leader) ============================

class Leader:
    """team.run_trainer 의 팀장 자리(설계 §3.3 Leader.__call__). 한 봉(date)에 하나 만들어 A0·A1 이 같이 쓴다.

    mode: "llm"(LLM 에 물음) | "late"(다음 장이 이미 열림 → 묻지 않음) | "replay"(재현 → 묻지 않음)
    now: 시간대 있는 지금 시각을 주는 함수(시험·재현에서 바꿔 끼움). 기본은 이 컴퓨터 시각.
    ask: LLM 묻기 함수(기본 analyst.analyze_logged, 같은 인자). 시험은 가짜를 넣는다.
    cli_version: 이번 실행에서 한 번 구한 `claude --version` 값(analyst.claude_cli_version()) — 그대로 넘긴다.

    부를 때(trainer, cands)
    1. 후보마다 열쇠를 만들고, 판정 기록에 없는 후보만 모은다(같은 트레이너에서 A0 가 먼저 물으면 A1 은 A0 에 없던 것만).
    2. mode="llm" 이면 묻기 **직전에** 시각을 다시 본다. 다음 장 시작(next_open)을 지났으면 그 호출부터 묻지 않고
       late_no_llm 으로 적는다(self.late_calls 를 센다). 아니면 ask(...) 를 한 번 부른다.
    3. 없는 후보 하나하나 기록을 만들어 곧바로 append(fsync). 답에서 빠진 종목은 missing_in_reply 폴백.
       답은 왔지만 판정 글자를 정리하면 buy·hold·veto 가 아닌 종목(예 "maybe", 빈칸)은 bad_verdict 폴백
       (source="fallback", 확신도도 쓰지 않음 → 규칙 그대로. 폴백 비율·W3 에 센다, 2b-1 검토 B-5).
    4. 돌려주는 값: 기록이 source="llm" 이고 판정(verdict, 정리된 값)이 있는 종목만
       {code: {"code", "verdict", "conviction"(숫자 또는 None), "note"}}. 빈 dict 는 team 에서 폴백(None)과 똑같다."""

    def __init__(self, market, date, log: DecisionLog, mode: str, *, now=None, ask=None, cli_version=None,
                 timeout=None):
        if mode not in LEADER_MODES:
            raise ValueError(f"팀장 mode 는 {LEADER_MODES} 중 하나 (받은 값 {mode!r})")
        _check_iso(date, "date")
        self.market = _mkey(market)
        self.date = date
        self.log = log
        self.mode = mode
        self.now = now if now is not None else _local_now
        self.ask = ask
        self.cli_version = cli_version
        self.timeout = analyst.TIMEOUT if timeout is None else timeout
        self.next_open = next_open(self.market, date)
        self.llm_calls = 0          # 실제로 LLM 을 부른 횟수
        self.late_calls = 0         # mode="llm" 이었지만 묻기 직전 시각 재확인으로 묻지 않은 호출 수
        self.went_late = False

    def _stamp(self):
        return _aware(self.now()).isoformat(timespec="seconds")

    def _next_call_no(self, trainer):
        prefix = f"{self.market}|{self.date}|{trainer}|"
        nums = []
        for r in self.log.records():
            cid = r.get("call_id")
            if isinstance(cid, str) and cid.startswith(prefix):
                try:
                    nums.append(int(cid[len(prefix):]))
                except ValueError:
                    pass
        return (max(nums) + 1) if nums else 1

    def __call__(self, trainer, cands):
        keyed, seen = [], set()
        for c in cands:
            key = decision_key(self.market, self.date, trainer, c["code"])
            if key in seen:
                continue
            seen.add(key)
            keyed.append((key, c))
        todo = [c for key, c in keyed if self.log.get(key) is None]
        if todo:
            self._ask_and_record(trainer, todo)
        out = {}
        for key, c in keyed:
            rec = self.log.get(key)
            if rec is None:
                raise H1LogicError(f"판정 기록을 쓴 뒤에도 열쇠가 없음: {key}", code="L17")
            if rec.get("source") == "llm" and rec.get("verdict") is not None:
                out[c["code"]] = {"code": c["code"], "verdict": rec["verdict"], "conviction": rec.get("conviction"),
                                  "note": rec.get("note")}
        return out

    def _ask_and_record(self, trainer, todo):
        status, result, meta = None, None, None
        if self.mode == "replay":
            status = "replay_no_llm"
        elif self.mode == "late":
            status = "late_no_llm"
        else:
            if not self.went_late and _aware(self.now()) >= self.next_open:     # 묻기 직전 재확인 (R2-14)
                self.went_late = True
            if self.went_late:
                status = "late_no_llm"
                self.late_calls += 1
        if status is None:
            ask = self.ask if self.ask is not None else analyst.analyze_logged
            result, meta = ask(trainer, todo, timeout=self.timeout, now=self.now, cli_version=self.cli_version)
            self.llm_calls += 1
            meta = dict(meta or {})
            status = meta.get("status") or "bad_json"
        asked_at = meta.get("asked_at") if meta else self._stamp()
        call_id = f"{self.market}|{self.date}|{trainer}|{self._next_call_no(trainer)}"
        batch = [c["code"] for c in todo]
        records = []
        for c in todo:
            code = c["code"]
            item = None
            if status == "ok" and isinstance(result, dict):
                item = result.get(code)
            if status == "ok" and isinstance(item, dict):
                source, rec_status = "llm", "ok"
                if analyst.normalize_verdict(item.get("verdict")) is None:
                    source, rec_status = "fallback", "bad_verdict"
            elif status == "ok":
                source, rec_status, item = "fallback", "missing_in_reply", None
            else:
                source, rec_status, item = "fallback", status, None
            note = None
            if item is not None and item.get("note") is not None:
                note = str(item.get("note"))[:500]
            records.append({
                "key": decision_key(self.market, self.date, trainer, code),
                "market": self.market, "date": self.date, "trainer": trainer, "code": code,
                "verdict": analyst.normalize_verdict(item.get("verdict")) if item is not None else None,
                "verdict_raw": _jsonable(item.get("verdict")) if item is not None else None,
                "conviction": team.to_conviction(item.get("conviction")) if source == "llm" else None,
                "conviction_raw": _jsonable(item.get("conviction")) if item is not None else None,
                "note": note,
                "source": source, "status": rec_status,
                "model": (meta or {}).get("model"),
                "cli_version": (meta or {}).get("cli_version", self.cli_version) if meta else self.cli_version,
                "asked_at": asked_at,
                "elapsed_s": float((meta or {}).get("elapsed_s") or 0.0),
                "next_open": self.next_open.isoformat(),
                "call_id": call_id, "batch": batch,
                "signal": {"price": _jsonable(c.get("price")), "rsi": _jsonable(c.get("rsi")),
                           "reason": _jsonable(c.get("reason")), "date": _jsonable(c.get("date"))},
            })
        self.log.append(records)                 # 장부보다 먼저 디스크에 (§3.6)
        return records


# ============================ 장부 만들기 · JSON 바꾸기 ============================

def new_ledger(market, arm, trainer, start_date, *, restart_no=0, code_hash="", env=None, updated_at=None) -> dict:
    """트레이너 한 명의 새 H1 장부(메모리 모양). 시작 금액 = 총액 × 배분비율(60/30/10), S 날짜로 입금만."""
    mk = _mkey(market)
    if arm not in ARMS or trainer not in TRAINERS:
        raise ValueError(f"모르는 장부 {arm}/{trainer}")
    _check_iso(start_date, "start_date")
    cash = TOTALS[mk] * main.CONFIG["배분비율"][trainer]
    st = team._new_state(trainer, cash, start_date, mk)     # 지갑 + 입금 (파일은 건드리지 않음)
    st["h1"] = {"market": mk, "arm": arm, "trainer": trainer, "idle_code": idle_code(mk),
                "idle_mode": "cash" if arm == "A0" else "index", "restart_no": restart_no,
                "code_hash": code_hash, "env": dict(env or {}), "updated_at": updated_at}
    for k in ("orders", "fills", "skips", "corp_actions", "days"):
        st[k] = []
    return {k: st[k] for k in LEDGER_KEYS if k != "schema"}


def new_ledgers(market, start_date, **kw) -> dict:
    """한 시장의 새 장부 6개 {arm: {trainer: st}}."""
    return {arm: {t: new_ledger(market, arm, t, start_date, **kw) for t in TRAINERS} for arm in ARMS}


def ledger_to_json(st, market) -> dict:
    """메모리 장부 → JSON 으로 적을 dict(칸 순서 고정, schema 붙임). 지갑은 asdict(지수 단위 float 그대로)."""
    mk = _mkey(market)
    keys = set(st)
    want = set(LEDGER_KEYS) - {"schema"}
    if keys - {"schema"} != want:
        raise H1LogicError(f"장부 칸이 다름: 빠짐 {sorted(want - keys)} / 남음 {sorted(keys - want - {'schema'})}",
                           code="L24")
    if "schema" in st and st["schema"] != SCHEMA[mk]:
        raise H1LogicError(f"장부 형식 {st['schema']!r} ≠ {SCHEMA[mk]!r}", code="L24")
    out = {"schema": SCHEMA[mk]}
    for k in LEDGER_KEYS[1:]:
        out[k] = _plain_wallet(st[k]) if k == "wallet" else st[k]
    return out


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _bad(msg):
    raise H1LogicError(msg, code="L24")


def json_loads_strict(text):
    """장부·HEAD 파일 읽기용 json.loads: NaN·Infinity·-Infinity 글자를 거절한다(파이썬 json 은 기본으로 받아 줌).
    깨진 JSON 도 H1LogicError(code="L24")."""
    def no_const(name):
        raise H1LogicError(f"JSON 에 {name} 이 있음(유한한 숫자만 받음)", code="L24")
    try:
        return json.loads(text, parse_constant=no_const)
    except H1LogicError:
        raise
    except (ValueError, TypeError) as e:
        raise H1LogicError(f"JSON 이 깨졌어요: {e}", code="L24")


# 장부 안 항목의 모양 (2b-1 검토 B-9). 값: 받아 주는 타입 이름들
_NUM, _INT, _STR, _BOOL, _NONE, _DICT, _LIST = "num", "int", "str", "bool", "none", "dict", "list"
_POS_SHAPE = {"buy_price": (_NUM,), "days_held": (_INT,), "shares": (_INT,), "buy_date": (_STR,)}
_PENDING_SHAPE = {"code": (_STR,), "action": (_STR,), "signal_date": (_STR,), "reason": (_STR,)}
_PENDING_OPTIONAL = {"note": (_STR, _NONE)}
_ORDER_SHAPE = {"id": (_STR,), "signal_date": (_STR,), "code": (_STR,), "action": (_STR,), "reason": (_STR,),
                "origin": (_STR,), "created_on": (_STR,), "status": (_STR,), "done_date": (_STR, _NONE),
                "why": (_STR, _NONE)}
_FILL_SHAPE = {"date": (_STR,), "code": (_STR,), "kind": (_STR,), "side": (_STR,), "qty": (_NUM,), "price": (_NUM,),
               "exec_price": (_NUM,), "fee": (_NUM,), "slip_cost": (_NUM,), "tax": (_NUM,), "cash_delta": (_NUM,),
               "cash_before": (_NUM,), "cash_after": (_NUM,), "units_before": (_NUM,), "units_after": (_NUM,),
               "order_id": (_STR, _NONE), "purpose": (_STR,), "need": (_NUM, _NONE), "short": (_NUM, _NONE)}
_SKIP_SHAPE = {"date": (_STR,), "code": (_STR,), "kind": (_STR,), "reason": (_STR,), "need": (_NUM, _NONE),
               "avail": (_NUM, _NONE), "order_id": (_STR, _NONE), "price": (_NUM, _NONE)}
_DAY_SHAPE = {"date": (_STR,), "prev_cal_date": (_STR, _NONE), "run_at": (_STR, _NONE), "mode": (_STR,),
              "late": (_BOOL,), "late_calls": (_INT,), "code_hash": (_STR,), "env": (_DICT,), "idle_open": (_NUM,),
              "idle_close": (_NUM,), "marks": (_DICT,), "cash": (_NUM,), "stock_value": (_NUM,),
              "idle_units": (_NUM,), "idle_value": (_NUM,), "value": (_NUM,), "n_buys": (_INT,), "n_sells": (_INT,),
              "n_idle_legs": (_INT,), "n_skips": (_INT,), "over_slots": (_INT,), "costs": (_DICT,),
              "events": (_LIST,), "screened": (_LIST,), "leader": (_LIST,), "halted": (_LIST,)}
_CA_SHAPE = {"delist": {"code": (_STR,), "last_date": (_STR,), "last_close": (_NUM,)},
             "split": {"code": (_STR,), "r": (_NUM,), "date": (_STR,), "applied_after": (_STR,)},
             "correction": {"code": (_STR,)}}


def _is(v, kinds):
    for k in kinds:
        if (k == _NUM and _isnum(v)) or (k == _INT and isinstance(v, int) and not isinstance(v, bool)) \
                or (k == _STR and isinstance(v, str)) or (k == _BOOL and isinstance(v, bool)) \
                or (k == _NONE and v is None) or (k == _DICT and isinstance(v, dict)) \
                or (k == _LIST and isinstance(v, list)):
            return True
    return False


def _check_item(where, item, shape, optional=None, exact=True):
    if not isinstance(item, dict):
        _bad(f"{where} 가 dict 가 아님")
    keys, want = set(item), set(shape)
    allowed = want | set(optional or {})
    if not want <= keys or (exact and not keys <= allowed):
        _bad(f"{where} 칸이 다름: 빠짐 {sorted(want - keys)} / 남음 {sorted(keys - allowed)}")
    for k, kinds in {**shape, **(optional or {})}.items():
        if k in item and not _is(item[k], kinds):
            _bad(f"{where}.{k} 모양이 다름 ({item[k]!r})")


def _all_finite(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            _all_finite(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _all_finite(v, f"{path}[{i}]")
    elif isinstance(obj, float) and not math.isfinite(obj):
        _bad(f"{path} = {obj!r} (NaN·inf 는 받지 않음)")


def ledger_from_json(d, market, arm=None, trainer=None) -> dict:
    """JSON dict → 메모리 장부(엄격). schema·칸·모양이 틀리면 H1LogicError(code="L24") — 새 지갑으로 덮지 않는다.
    보유는 Holding(**v) 로 그대로 만든다 → 정수 주식은 int 그대로, 지수 단위는 float 비트 그대로.
    2b-1 검토 B-9: 어디든 NaN·inf 가 있으면 거절하고, positions·pending·orders·fills·skips·days·corp_actions 항목의
    필수 칸과 타입도 본다(파일에서 읽을 때는 json_loads_strict 로 NaN 글자부터 거절)."""
    mk = _mkey(market)
    if not isinstance(d, dict):
        _bad("장부가 dict 가 아님")
    if set(d) != set(LEDGER_KEYS):
        _bad(f"장부 칸이 다름: 빠짐 {sorted(set(LEDGER_KEYS) - set(d))} / 남음 {sorted(set(d) - set(LEDGER_KEYS))}")
    if d["schema"] != SCHEMA[mk]:
        _bad(f"장부 형식 {d['schema']!r} ≠ {SCHEMA[mk]!r}")
    _all_finite(d)
    head = d["h1"]
    if not isinstance(head, dict) or set(head) != set(H1_HEAD_KEYS):
        _bad("h1 머리 칸이 다름")
    if head["market"] != mk or head["idle_code"] != idle_code(mk):
        _bad("h1 머리의 시장·대기 자산이 다름")
    if arm is not None and (head["arm"] != arm or head["idle_mode"] != ("cash" if arm == "A0" else "index")):
        _bad(f"h1 머리의 장부 {head['arm']!r} ≠ {arm!r}")
    if trainer is not None and head["trainer"] != trainer:
        _bad(f"h1 머리의 트레이너 {head['trainer']!r} ≠ {trainer!r}")
    w = d["wallet"]
    if not isinstance(w, dict) or set(w) != set(WALLET_KEYS):
        _bad("지갑 칸이 다름")
    if w["currency"] != markets.MARKETS[mk].currency:
        _bad(f"지갑 통화 {w['currency']!r} ≠ 시장 통화")
    for k in ("cash", "fee_rate", "sell_tax_rate", "slippage"):
        if not _isnum(w[k]):
            _bad(f"지갑 {k} 가 숫자가 아님")
    if not isinstance(w["holdings"], dict) or not isinstance(w["log"], list):
        _bad("지갑 보유·기록 모양이 다름")
    holdings = {}
    for code, h in w["holdings"].items():
        if not isinstance(h, dict) or set(h) != {"shares", "avg_price"} or not _isnum(h["shares"]) \
                or not _isnum(h["avg_price"]):
            _bad(f"보유 {code} 모양이 다름")
        holdings[code] = Holding(**h)
    if not isinstance(d["positions"], dict):
        _bad("positions 가 dict 가 아님")
    for k in ("pending", "orders", "fills", "skips", "corp_actions", "days"):
        if not isinstance(d[k], list):
            _bad(f"{k} 가 목록이 아님")
    for code, pos in d["positions"].items():
        _check_item(f"positions[{code}]", pos, _POS_SHAPE)
    for i, o in enumerate(d["pending"]):
        _check_item(f"pending[{i}]", o, _PENDING_SHAPE, _PENDING_OPTIONAL)
    for name, items, shape in (("orders", d["orders"], _ORDER_SHAPE), ("fills", d["fills"], _FILL_SHAPE),
                               ("skips", d["skips"], _SKIP_SHAPE), ("days", d["days"], _DAY_SHAPE)):
        for i, it in enumerate(items):
            _check_item(f"{name}[{i}]", it, shape)
    for i, ca in enumerate(d["corp_actions"]):
        if not isinstance(ca, dict) or ca.get("kind") not in _CA_SHAPE:
            _bad(f"corp_actions[{i}] 종류를 모름 ({ca!r})")
        _check_item(f"corp_actions[{i}]", ca, {"kind": (_STR,), **_CA_SHAPE[ca["kind"]]}, exact=False)
    if not isinstance(d["stopped"], bool):
        _bad("stopped 가 참/거짓이 아님")
    if d["prev_value"] is not None and not _isnum(d["prev_value"]):
        _bad("prev_value 모양이 다름")
    if d["last_date"] is not None and not isinstance(d["last_date"], str):
        _bad("last_date 모양이 다름")
    if not _isnum(d["start_cash"]) or not isinstance(d["start_date"], str):
        _bad("시작 금액·날짜 모양이 다름")
    wallet = PaperWallet(name=w["name"], cash=w["cash"], currency=w["currency"], fee_rate=w["fee_rate"],
                         sell_tax_rate=w["sell_tax_rate"], slippage=w["slippage"])
    wallet.holdings = holdings
    wallet.log = w["log"]
    st = {k: d[k] for k in LEDGER_KEYS if k not in ("schema", "wallet")}
    st["wallet"] = wallet
    return {k: st[k] for k in LEDGER_KEYS if k != "schema"}


def clone_states(states, market) -> dict:
    """장부 6개를 JSON 왕복으로 깊이 복사한다(저장 → 읽기와 같은 길, float 비트 그대로)."""
    out = {}
    for arm in ARMS:
        out[arm] = {}
        for tname in TRAINERS:
            blob = json.dumps(ledger_to_json(states[arm][tname], market), ensure_ascii=False, allow_nan=False)
            out[arm][tname] = ledger_from_json(json.loads(blob), market, arm, tname)
    return out


def _flat(states):
    return [(arm, tn, states[arm][tn]) for arm in ARMS for tn in TRAINERS]


def delist_registrations(states) -> dict:
    """장부 corp_actions 의 상장폐지 등록 → {code: {"last_date", "last_close"}} (2b-1 검토 B-4: 출처는 이것 하나).
    여섯 장부의 등록이 서로 다르면 H1LogicError(code="L23")."""
    seen = None
    for arm, tn, st in _flat(states):
        regs = {}
        for ca in st["corp_actions"]:
            if ca.get("kind") == "delist":
                regs[ca["code"]] = {"last_date": ca["last_date"], "last_close": ca["last_close"]}
        if seen is None:
            seen = regs
        elif regs != seen:
            raise H1LogicError(f"여섯 장부의 상장폐지 등록이 서로 다름({arm}/{tn})", code="L23")
    return seen or {}


def apply_split(states, code, r, date, source, at) -> dict:
    """순수 액면분할·병합 적용 (설계 §2.2 ⑦-2, 2b-1 검토 B-2). 입력 states 는 고치지 않고 새 장부 6개를 돌려준다.
    r = 새 주식 수 ÷ 옛 주식 수(예 2 = 1주가 2주로, 0.5 = 2주가 1주로). date = 출처의 분할 기준일.
    - 두 장부 6개에 똑같이: positions 주식 수 ×r·buy_price ÷r, wallet.holdings 주식 수 ×r·avg_price ÷r. 대기 주문은 그대로.
    - 평가액은 그 순간 그대로다(수량 ×r, 가격 ÷r). 지수(대기 자산)에는 쓸 수 없다.
    - 어느 장부든 r 을 곱한 주식 수가 정수가 아니면 아무것도 바꾸지 않고 ValueError(설계 ⑦-2 → ⑦-3 재시작 길).
    - 모든 장부의 corp_actions 에 {"kind": "split", "code", "r", "date", "applied_after": 지금 장부 last_date,
      "source", "at"} 한 줄을 더한다. 점검(h1_check)은 applied_after 날 종가 뒤에 수량 ×r·매수가 ÷r 를 반영한다.
    CLI(corp-action --split)·잠금·저장은 2b-2 몫."""
    if not (_isnum(r) and math.isfinite(r) and r > 0) or r == 1:
        raise ValueError(f"분할 비율 r 은 1 이 아닌 양수여야 해요 (받은 값 {r!r})")
    _check_iso(date, "date")
    flat = _flat(states)
    mks = {st["h1"]["market"] for _, _, st in flat}
    lasts = {st["last_date"] for _, _, st in flat}
    if len(mks) != 1 or len(lasts) != 1 or None in lasts:
        raise ValueError("분할은 같은 시장·같은 last_date 의 처리된 장부 6개에만 적용해요")
    mk, last = mks.pop(), lasts.pop()
    if code == idle_code(mk):
        raise ValueError("대기 자산(지수)에는 분할을 적용하지 않아요")
    out = clone_states(states, mk)
    plan = []
    for arm, tn, st in _flat(out):
        pos = st["positions"].get(code)
        h = st["wallet"].holdings.get(code)
        if pos is None:
            if h is not None:
                raise H1LogicError(f"{arm}/{tn}: positions 없이 지갑에 {code} 보유", code="L2")
            continue
        if h is None or h.shares != pos["shares"]:
            raise H1LogicError(f"{arm}/{tn}: {code} positions·지갑 수량이 다름", code="L2")
        q = pos["shares"] * r
        if not float(q).is_integer():
            raise ValueError(f"{arm}/{tn}: {code} {pos['shares']}주 × {r} = {q} 가 정수가 아님 → 공식 적용 불가(⑦-3)")
        plan.append((st, pos, h, int(q)))
    for st, pos, h, q in plan:
        pos["shares"] = q
        pos["buy_price"] = pos["buy_price"] / r
        h.shares = q
        h.avg_price = h.avg_price / r
    for _, _, st in _flat(out):
        st["corp_actions"].append({"kind": "split", "code": code, "r": r, "date": date, "applied_after": last,
                                   "source": source, "at": at})
    return out


# ============================ 하루 처리기 (H1Day) ============================

class H1Day:
    """team.run_trainer(h1=…) 에 넘기는 하루 처리기. 장부(arm) 하나에 하나, 트레이너 셋이 같이 쓴다.

    속성(설계 §3.3): market, arm, idle(IdleBar), leader(판정 기록 팀장 — 부르면 Leader 를 부르고 late_calls 를 셈),
    late(봉 시작 때 늦었나), mode, start_date(S), halted(그날 정지 종목), delist({code: {last_date, last_close}}),
    code_hash, env, screened({트레이너: 스크리너 후보 목록}), prev_cal_date(달력의 바로 앞 거래일), run_at,
    problems(엔진이 처리 중에 찾은 장부 논리 오류 Problem 목록 — run_bar 가 결과에 합침).

    fill: 시가 단계 a~e (아래 docstring). note_leader: 팀장 결과를 버퍼에만. close_day: marks·평가·그림자 서킷·
    새 주문·팀장 결과(skips·leader·over_slots)·하루 기록 1줄.

    2b-1 검토 B-3: 처리 중 "일어나면 안 되는 일"(지수 판 뒤 매수 실패 L11, 평가액 불일치 L7, 팀장 효과 재계산 불일치 L19,
    끝난 주문 다시 처리 L14 …)은 예외로 멈추지 않고 problems 에 L 로 적은 뒤 봉 처리를 끝까지 한다. 그래서 run_bar 가
    처리 뒤 장부와 내용 지문을 돌려줄 수 있다(errors.jsonl 의 "저장하려던 지문", 설계 §2.2 ④-나)."""

    def __init__(self, market, arm, idle: IdleBar, leader, *, start_date, prev_cal_date=None, mode="llm",
                 late=False, halted=frozenset(), delist=None, code_hash="", env=None, screened=None, run_at=None,
                 problems=None):
        if arm not in ARMS:
            raise ValueError(f"모르는 장부 {arm!r}")
        self.market = _mkey(market)
        self.arm = arm
        self.idle = idle
        self.decider = leader
        self.late = bool(late)
        self.mode = mode
        self.start_date = start_date
        self.prev_cal_date = prev_cal_date
        self.halted = frozenset(halted)
        self.delist = dict(delist or {})
        self.code_hash = code_hash
        self.env = dict(env or {})
        self.screened = dict(screened or {})
        self.run_at = run_at
        self.problems = [] if problems is None else problems
        self._leader_buf = {}
        self._late_calls = {}

    def _L(self, code, tname, detail):
        """장부 논리 오류를 problems 에 적는다(예외로 멈추지 않음)."""
        self.problems.append(h1_check.Problem("L", code, self.market, self.arm, tname, self.idle.date, detail))

    # team 의 `h1.leader(tname, cands)` 자리
    def leader(self, trainer, cands):
        before = getattr(self.decider, "late_calls", 0)
        out = self.decider(trainer, cands)
        self._late_calls[trainer] = self._late_calls.get(trainer, 0) + getattr(self.decider, "late_calls", 0) - before
        return out

    # ---------------- 지갑 다리 (PaperWallet 계산 그대로, R2 _sell·_buy) ----------------

    def _units(self, w):
        h = w.holdings.get(self.idle.code)
        return float(h.shares) if h else 0.0

    def _idx_net_per_unit(self, w):
        """지수 1단위를 팔면 받는 돈(매도세 0) — R2 _idx_net_per_unit 그대로."""
        px = self.idle.open
        proceeds = px * (1 - w.slippage)
        return proceeds - proceeds * w.fee_rate

    def _fill_row(self, st, *, t, code, kind, side, qty, price, exec_price, fee, slip_cost, tax, cash_delta,
                  cash_before, units_before, purpose, order_id=None, need=None, short=None):
        w = st["wallet"]
        st["fills"].append({
            "date": t, "code": code, "kind": kind, "side": side, "qty": qty, "price": price,
            "exec_price": exec_price, "fee": fee, "slip_cost": slip_cost, "tax": tax, "cash_delta": cash_delta,
            "cash_before": cash_before, "cash_after": w.cash, "units_before": units_before,
            "units_after": self._units(w), "order_id": order_id, "purpose": purpose, "need": need, "short": short})

    def _buy(self, st, code, kind, px, qty, t, *, purpose, order_id=None, need=None, short=None) -> bool:
        w = st["wallet"]
        cb, ub = w.cash, self._units(w)
        if not w.buy(code, px, qty, t):
            return False
        exec_price = px * (1 + w.slippage)          # PaperWallet.buy 와 같은 계산 순서
        cost = exec_price * qty
        fee = cost * w.fee_rate
        self._fill_row(st, t=t, code=code, kind=kind, side="buy", qty=qty, price=px, exec_price=exec_price,
                       fee=fee, slip_cost=qty * px * w.slippage, tax=0.0, cash_delta=-(cost + fee),
                       cash_before=cb, units_before=ub, purpose=purpose, order_id=order_id, need=need, short=short)
        return True

    def _sell(self, st, tname, code, kind, px, qty, t, tax_rate, *, purpose, order_id=None, need=None,
              short=None) -> bool:
        """판다. 지갑이 거절하면(보유보다 많음 등) L2 를 적고 False."""
        w = st["wallet"]
        cb, ub = w.cash, self._units(w)
        if not w.sell(code, px, qty, t, tax_rate=tax_rate):
            self._L("L2", tname, f"{code} 매도를 지갑이 거절함 qty={qty!r}")
            return False
        exec_price = px * (1 - w.slippage)          # PaperWallet.sell 과 같은 계산 순서
        proceeds = exec_price * qty
        fee = proceeds * w.fee_rate
        tax = proceeds * tax_rate
        self._fill_row(st, t=t, code=code, kind=kind, side="sell", qty=qty, price=px, exec_price=exec_price,
                       fee=fee, slip_cost=qty * px * w.slippage, tax=tax, cash_delta=proceeds - fee - tax,
                       cash_before=cb, units_before=ub, purpose=purpose, order_id=order_id, need=need, short=short)
        return True

    def _sweep(self, st, tname, t, purpose) -> bool:
        """남은 현금을 전부 지수로(소수 단위, 남는 돈 < 1) — R2 _sweep_to_index 그대로.
        현금 < SWEEP_MIN 이면 아무것도 안 함. 줄임 1e-12 → 1e-9 → 1e-6 중 처음 성공하는 값.
        셋 다 실패면 L11 을 적고 False (현금은 그대로 남음 → 점검 L10 도 걸림)."""
        w = st["wallet"]
        if w.cash < SWEEP_MIN:
            return False
        px = self.idle.open
        unit = px * (1 + w.slippage) * (1 + w.fee_rate)
        for shrink in SWEEP_SHRINK:
            u = w.cash / unit * (1 - shrink)
            if self._buy(st, self.idle.code, "idle", px, u, t, purpose=purpose):
                return True
        self._L("L11", tname, f"지수 매수 실패(쓸어 담기 '{purpose}', 현금 {w.cash!r})")
        return False

    def _skip(self, st, t, code, kind, why, *, need=None, avail=None, order_id=None, price=None):
        st["wallet"].skip(code, why, t)               # team.py·R2 처럼 지갑 기록에도 '보류'
        st["skips"].append({"date": t, "code": code, "kind": kind, "reason": why, "need": need, "avail": avail,
                            "order_id": order_id, "price": price})

    # ---------------- 시가 (G1) ----------------

    def fill(self, st, tname, cap, bar_date, cache, m, logs) -> bool:
        """봉 t 시가 단계 (설계 §2.3 a~e, A0/A1 차이 표). 무엇인가 했으면 True.
        t = S 이면 아무것도 안 한다(입금만, §2.5).
        a  (A1, S+1) 현금 전부 지수(purpose="start")
        a′ (상장폐지 등록 종목, 등록 last_date 뒤 첫 처리 봉) 두 장부 모두 등록 가격으로 전량 정리, 대기 주문 dropped
        b  대기 주문 나누기: t 확정 행이 있고 시가가 있으면 오늘 체결, 정지(halted)면 그대로 둠
           (그 밖은 run_bar 사전 확인에서 D2·D3 으로 걸려야 함 → 여기까지 오면 L6)
        c  주식 매도 먼저(보유 중인 것만, 국내 세율 = 체결일 표)
        d  주식 매수(대기 목록 순서). 0주·현금부족 보류. A1 은 모자란 만큼만 지수 매도(여유 1e-9)
        e  (A1) 남은 현금 ≥ 1 이면 지수로"""
        t = bar_date
        if t == st["start_date"]:
            return False
        w = st["wallet"]
        positions = st["positions"]
        is_a1 = self.arm == "A1"
        fee, slip = w.fee_rate, w.slippage
        by_id = {o["id"]: o for o in st["orders"]}
        changed = False

        def finish(rec, status, why=None):
            if rec["status"] != "pending":
                self._L("L14", tname, f"주문 {rec['id']} 은 이미 {rec['status']} 인데 다시 {status}")
            rec["status"], rec["done_date"], rec["why"] = status, t, why

        # a. A1 첫날(S+1): 주문보다 먼저 현금 전부 지수
        if is_a1 and st["last_date"] == st["start_date"]:
            if self._units(w) != 0.0 or st["fills"]:
                self._L("L10", tname, "S+1 인데 이미 지수·체결이 있음 → 첫 전부 지수를 하지 않음")
            elif self._sweep(st, tname, t, "start"):
                logs.append(f"지수 매수 {self.idle.code} {fmt_units(self._units(w))}단위(첫날 전부)")
                changed = True
            else:
                self._L("L10", tname, f"S+1 첫 전부 지수를 하지 못함(현금 {w.cash!r})")

        # a′. 상장폐지 정리 (§2.2 ⑦-4)
        for code in sorted(self.delist):
            reg = self.delist[code]
            if t <= reg["last_date"]:
                continue
            if code in positions:
                px = float(reg["last_close"])
                if self._sell(st, tname, code, "stock", px, positions[code]["shares"], t,
                              stock_sell_tax(self.market, t), purpose="delist"):
                    positions.pop(code)
                    logs.append(f"상장폐지 정리 {code}@{px}")
                changed = True
            keep = []
            for o in st["pending"]:
                if o["code"] != code:
                    keep.append(o)
                    continue
                rec = by_id.get(order_id(o))
                if rec is None:
                    self._L("L14", tname, f"대기 주문 {order_id(o)} 의 주문 기록이 없음")
                else:
                    finish(rec, "dropped", "delist")
                changed = True
            st["pending"] = keep

        # b. 대기 주문 나누기
        todo, still = [], []
        for o in st["pending"]:
            rec = by_id.get(order_id(o))
            if rec is None or rec["status"] != "pending":
                self._L("L14", tname, f"대기 주문 {order_id(o)} 의 주문 기록이 없거나 pending 이 아님 → 처리 안 함")
                still.append(o)
                continue
            code = o["code"]
            if code in self.halted:
                still.append(o)                        # 정지 중: 다음 거래된 봉 시가로 (STAGE0 A5)
                continue
            df = cache[code]                           # 엄격 cache: 받아 두지 않은 종목이면 H1LogicError(L6)
            row = _row_at(df, t) if df is not None else None
            px = main.open_price(row) if row is not None else None
            if px is None:
                self._L("L6", tname, f"대기 주문 종목 {code} 의 {t} 확정 행·시가 없음(사전 확인 D2·D3 을 지났는데)")
                still.append(o)
                continue
            todo.append((o, rec, px))
        st["pending"] = still

        # c. 주식 매도 → 현금
        for o, rec, px in todo:
            if o["action"] != "매도":
                continue
            code = o["code"]
            changed = True
            if code not in positions:
                finish(rec, "dropped", "보유 없음")
                continue
            if self._sell(st, tname, code, "stock", px, positions[code]["shares"], t, stock_sell_tax(self.market, t),
                          purpose="order", order_id=rec["id"]):
                positions.pop(code)
                finish(rec, "filled")
                logs.append(f"매도 {code}{team._at(m, px)}({o.get('reason', '')})")
            else:
                finish(rec, "dropped", "매도 실패")

        # d. 주식 매수 (대기 목록 순서)
        for o, rec, px in todo:
            if o["action"] != "매수":
                continue
            code = o["code"]
            changed = True
            if code in positions:
                finish(rec, "dropped", "이미 보유")
                continue
            n = shares_within_cap(st["start_cash"], cap, px, fee, slip)
            if n <= 0:
                why = f"상한 {main.fmt(m, st['start_cash'] * cap, False)} 안에서 1주도 못 삼 (시가 {main.px_txt(m, px)})"
                self._skip(st, t, code, "0주", why, order_id=rec["id"], price=px)
                finish(rec, "skipped", "0주")
                logs.append(f"보류 {code}({why})")
                continue
            exec_px = px * (1 + slip)                  # PaperWallet.buy 와 같은 순서로 필요 금액 계산
            need = exec_px * n + exec_px * n * fee
            if is_a1:
                u_net = self._idx_net_per_unit(w)
                avail = w.cash + self._units(w) * u_net
                short_of_cash = need > avail * (1 - SHORT_MARGIN)
            else:
                avail = w.cash
                short_of_cash = need > avail
            why = f"현금 부족 (필요 {main.fmt(m, px * n, False)}, 보유 {main.fmt(m, avail, False)})"
            if short_of_cash:                          # A1 은 지수를 팔지 않고 보류 (R2 I2·R6)
                self._skip(st, t, code, "현금부족", why, need=need, avail=avail, order_id=rec["id"], price=px)
                finish(rec, "skipped", "현금부족")
                logs.append(f"보류 {code}(현금 부족)")
                continue
            short, sold_idle = (0.0 if is_a1 else None), False
            if is_a1:                                  # R2 _raise_cash: 모자란 만큼만 지수 매도
                short = need - w.cash
                if short > 0:
                    held = self._units(w)
                    u = min(held, short / u_net * (1 + SHORT_MARGIN))
                    if u > 0:
                        sold_idle = self._sell(st, tname, self.idle.code, "idle", self.idle.open, u, t, 0.0,
                                               purpose=f"fund:{code}", need=need, short=short)
                        if sold_idle:
                            logs.append(f"지수 매도 {self.idle.code} {fmt_units(u)}단위({code} 자금)")
                else:
                    short = 0.0
            if not self._buy(st, code, "stock", px, n, t, purpose="order", order_id=rec["id"], need=need,
                             short=short):
                if sold_idle:
                    self._L("L11", tname, f"지수를 판 뒤 {code} 매수 실패(일어날 수 없게 만든 길)")
                else:
                    self._L("L12", tname, f"필요 금액이 가능 금액 안인데 {code} 매수 실패")
                self._skip(st, t, code, "현금부족", why, need=need, avail=avail, order_id=rec["id"], price=px)
                finish(rec, "skipped", "현금부족")
                continue
            positions[code] = {"buy_price": px, "days_held": 0, "shares": n, "buy_date": t}
            finish(rec, "filled")
            tip = f" 팀장:{o['note']}" if o.get("note") else ""
            logs.append(f"매수 {code}x{n}{team._at(m, px)}{tip}")

        # e. A1 쓸어 담기 (매도 대금·남은 돈 → 지수)
        if is_a1 and self._sweep(st, tname, t, "sweep"):
            logs.append(f"지수 매수 {self.idle.code} → 보유 {fmt_units(self._units(w))}단위(쓸어 담기)")
            changed = True
        return changed

    # ---------------- 팀장 결과 (G4) ----------------

    def note_leader(self, st, tname, bar_date, cands0, analysis, kept, slots) -> None:
        """team ④ 가 주문을 다 낸 뒤 부른다. 장부는 고치지 않고 트레이너별 버퍼에만 담는다(close_day 가 씀)."""
        self._leader_buf[tname] = {"date": bar_date, "cands0": [dict(c) for c in cands0],
                                   "analysis": analysis, "kept": [dict(c) for c in kept], "slots": slots}

    def _leader_effects(self, tname, bar_date, buf):
        """team ④ 와 같은 규칙으로 후보마다 효과를 다시 정한다: veto·hold·low_conv·ordered·over_slots.
        다시 정한 결과가 team ④ 의 kept 와 다르면 L19 를 적는다(효과는 team 의 kept 를 따른다)."""
        analysis = buf["analysis"]
        verdicts = {k: (v or {}).get("verdict") for k, v in (analysis or {}).items()}
        kept_codes = [c["code"] for c in buf["kept"]]
        n_slots = max(buf["slots"], 0)
        rows, skips, mine = [], [], []
        for c in buf["cands0"]:
            code = c["code"]
            a = analysis.get(code) if analysis is not None else None
            verdict = a.get("verdict") if a else None
            if analysis is not None and a and a.get("verdict") == "veto":
                effect = "veto"
            else:
                cc = {**c, "conviction": a.get("conviction"), "note": a.get("note")} if a else c
                conv = team.to_conviction(cc.get("conviction"))
                if verdicts.get(code) == "hold":
                    effect = "hold"
                    skips.append((code, "팀장hold", "팀장 hold"))
                elif not team.keep_candidate({**cc, "conviction": conv}):
                    effect = "low_conv"
                    skips.append((code, "확신도낮음", f"팀장 확신도 낮음 ({conv:.2f} < {team.CONV_MIN})"))
                else:
                    effect = "kept"
                    mine.append(code)
            rows.append({"code": code, "key": decision_key(self.market, bar_date, tname, code),
                         "verdict": verdict, "effect": effect})
        if sorted(mine) != sorted(kept_codes):
            self._L("L19", tname, f"팀장 효과를 다시 계산한 결과가 team ④ 와 다름 {mine} vs {kept_codes}")
        rank = {code: i for i, code in enumerate(kept_codes)}
        for r in rows:
            if r["effect"] == "kept":
                r["effect"] = "ordered" if rank.get(r["code"], n_slots) < n_slots else "over_slots"
        over = max(0, len(kept_codes) - n_slots)
        return rows, skips, over

    # ---------------- 종가 (G5) ----------------

    def close_day(self, st, tname, bar_date, prices, value) -> None:
        """종가 단계 i: 평가 확인·marks·그림자 서킷·새 주문 기록·팀장 결과·하루 기록 1줄.
        평가 가격표에 보유 종목이 빠짐(R14)·지수 종가가 다름·평가액 불일치는 L7 로 적고 하루 기록은 그대로 남긴다."""
        t = bar_date
        w = st["wallet"]
        missing = [c for c in w.holdings if c not in prices]
        if missing:                                   # R14: 가격표에 없으면 평균 매입가로 평가돼 조용히 틀림
            self._L("L7", tname, f"평가 가격표에 보유 종목 {missing} 이 없음")
        if prices.get(self.idle.code) != self.idle.close:
            self._L("L7", tname, "가격표의 대기 자산 종가가 IdleBar 와 다름")
        positions = st["positions"]
        if set(positions) - set(w.holdings):
            self._L("L2", tname, f"지갑 보유에 없는 positions {sorted(set(positions) - set(w.holdings))}")
        marks = {c: prices[c] for c in positions if c in prices}
        stock_value = sum(w.holdings[c].shares * marks[c] for c in positions if c in marks and c in w.holdings)
        units = self._units(w)
        idle_value = units * self.idle.close
        total = w.cash + stock_value + idle_value
        if abs(total - value) > h1_check.EPS_REL * max(1.0, abs(total), abs(value)):
            self._L("L7", tname, f"평가액 불일치 {total!r} vs wallet.value {value!r}")

        # 그림자 서킷 (§2.6): prev = 그 장부의 바로 전 하루 기록 value (S 는 None)
        days = st["days"]
        prev = days[-1]["value"] if days else None
        events = []
        hit = CircuitBreaker(*SHADOW_BREAKER).check(st["start_cash"], prev, value)
        if hit:
            first = not any(e.get("kind") == "shadow_breaker" for d in days for e in d.get("events", []))
            events.append({"kind": "shadow_breaker", "why": hit, "first": first})

        # 새 주문 기록 (§3.5 orders)
        by_id = {o["id"]: o for o in st["orders"]}
        for o in st["pending"]:
            oid = order_id(o)
            old = by_id.get(oid)
            if old is not None:
                if old["status"] != "pending":
                    self._L("L5", tname, f"끝난 주문과 같은 id 의 새 주문 {oid}")
                continue
            rec = {"id": oid, "signal_date": o["signal_date"], "code": o["code"], "action": o["action"],
                   "reason": o.get("reason", ""), "origin": "candidate" if o["action"] == "매수" else "sell_signal",
                   "created_on": t, "status": "pending", "done_date": None, "why": None}
            st["orders"].append(rec)
            by_id[oid] = rec

        # 팀장 결과 (note_leader 버퍼)
        buf = self._leader_buf.pop(tname, None)
        leader_rows, over = [], 0
        if buf is not None:
            if buf["date"] != t:
                self._L("L19", tname, f"팀장 버퍼 날짜 {buf['date']} ≠ {t} → 버림")
            else:
                leader_rows, skips, over = self._leader_effects(tname, t, buf)
                for code, kind, why in skips:
                    st["skips"].append({"date": t, "code": code, "kind": kind, "reason": why, "need": None,
                                        "avail": None, "order_id": None, "price": None})

        today = [f for f in st["fills"] if f["date"] == t]
        row = {
            "date": t, "prev_cal_date": self.prev_cal_date, "run_at": self.run_at, "mode": self.mode,
            "late": self.late, "late_calls": self._late_calls.get(tname, 0), "code_hash": self.code_hash,
            "env": dict(self.env),
            "idle_open": self.idle.open, "idle_close": self.idle.close, "marks": marks,
            "cash": w.cash, "stock_value": stock_value, "idle_units": units, "idle_value": idle_value,
            "value": value,
            "n_buys": sum(1 for f in today if f["kind"] == "stock" and f["side"] == "buy"),
            "n_sells": sum(1 for f in today if f["kind"] == "stock" and f["side"] == "sell"),
            "n_idle_legs": sum(1 for f in today if f["kind"] == "idle"),
            "n_skips": sum(1 for s in st["skips"] if s["date"] == t),
            "over_slots": over,
            "costs": {"fee": sum(f["fee"] for f in today), "slip": sum(f["slip_cost"] for f in today),
                      "tax": sum(f["tax"] for f in today)},
            "events": events,
            "screened": [c["code"] for c in self.screened.get(tname, [])],
            "leader": leader_rows,
            "halted": sorted(self.halted),
        }
        days.append(row)


# ============================ 봉 하나 (run_bar) ============================

@dataclass
class BarResult:
    """run_bar 결과. ok 가 False 면(L 오류) 그 봉은 저장하지 않는다(종료 코드 2).
    L 오류가 있어도 states·fingerprint 는 처리 끝까지 간 장부다 → errors.jsonl 의 "저장하려던 내용 지문"으로 쓴다."""
    date: str
    states: dict                 # 처리 뒤 장부 6개 {arm: {trainer: st}} (입력 장부는 그대로 둠)
    problems: list               # h1_check.Problem (엔진이 찾은 L + check_day 의 L + W 경고)
    lines: list                  # team.run_trainer 가 돌려준 사람용 한 줄들 ("A0 마라토너: …")
    found: dict                  # 스크리너 결과 {트레이너: [후보]}
    used: int
    mode: str                    # "llm" | "late" | "replay"
    late: bool
    llm_calls: int
    late_calls: int
    new_records: list            # 이번 봉에서 판정 기록에 더한 줄
    fingerprint: str | None      # 처리 뒤 장부 6개의 내용 지문 (NaN 등으로 못 내면 None)

    @property
    def errors(self):
        return h1_check.errors(self.problems)

    @property
    def ok(self):
        return not self.errors


def _safe_fingerprint(states):
    try:
        return ledger_fingerprint(states)
    except Exception:          # NaN 이 섞이는 등 지문을 낼 수 없으면 None (그 사실 자체가 L21)
        return None


def _attach(e, t, states, problems=None):
    """끝까지 갈 수 없어 예외로 끝나는 L 에 그때까지의 지문·날짜·문제 목록을 붙인다(2b-1 검토 B-3)."""
    if getattr(e, "fingerprint", None) is None:
        e.fingerprint = _safe_fingerprint(states) if states is not None else None
    e.date = t
    e.problems = list(problems or [])
    if getattr(e, "code", None) is None and isinstance(e, H1LogicError):
        e.code = "L24"
    return e


def _pre(msg):
    raise H1PreconditionError(f"사전 조건 위반: {msg}")


def run_bar(market, t, states, frames, universe, idle: IdleBar, *, decisions: DecisionLog, leader_mode="llm",
            halted=frozenset(), delist=None, prev_cal_date=None, calendar=None, now=None, ask=None,
            cli_version=None, code_hash="", env=None, allowed=None, head=None, universe_sha256=None,
            meta_universe_sha256=None, brains=None) -> BarResult:
    """확정 봉 t 하나를 한 시장의 장부 6개(A0·A1 × 트레이너 3명)에 처리한다 (설계 §2.3 "봉 t 하나" 1~4).
    파일은 쓰지 않는다(판정 기록 추가만 예외). 저장(백업 → 장부 6개 → HEAD)은 2b-2 의 일이다.

    인자
      market     "us" | "kr"
      t          처리할 봉 'YYYY-MM-DD'. 여섯 장부의 last_date 는 모두 같고 t 보다 앞이어야 한다(t = S 이면 None)
      states     {arm: {trainer: st}} 처리 전 장부(메모리 모양, ledger_from_json 결과). **고치지 않는다**
      frames     {code: 확정 시세 DataFrame 또는 None(받기 실패)} — 종목군 + 두 장부 보유·대기 종목.
                 여기서 t 이하로 잘라 엄격 cache(StrictFrames)로 만든다(미래 봉을 보지 않음)
      universe   스크리너가 훑는 종목 순서(미국 = S 날 고정 40종목, 국내 = KR_UNIVERSE)
      idle       IdleBar(대기 자산 코드, t, 시가, 종가)
      decisions  DecisionLog (판정 기록, 여기서 줄이 더해질 수 있음. read_only 로 연 것은 안 됨)
      leader_mode "llm"(운영) | "replay"(재현: LLM 안 부름). "llm" 이면 now() < next_open(t) 일 때만 llm, 아니면 late
      halted     t 에 거래정지인 종목(국내: 원본에 t 행이 있고 거래량 0). 정지 종목은 t 확정 행이 없어야 한다
      delist     **넘기지 않아도 된다.** 상장폐지 정보는 장부 corp_actions 의 등록 하나만 쓴다(2b-1 검토 B-4).
                 넘기면 {code: {"last_date", "last_close"}} 가 corp_actions 에서 만든 값과 같은지만 확인한다
      prev_cal_date 달력에서 t 바로 앞 거래일. **S 에서도 꼭 준다**(S 전 거래일, 2b-1 검토 B-10).
                 t > S 이면 장부 last_date 와 같아야 한다
      calendar   달력 날짜 목록(calendar.jsonl 마지막 줄, S 전 거래일 ~ t). 주면 t 가 있고 그 앞 날짜가 prev_cal_date
                 인지 사전 조건으로 보고, L16 점검에도 쓴다. None 이면 둘 다 생략
      now, ask, cli_version  Leader 에 넘김(시계·LLM 함수·claude 버전 — 실행마다 한 번 구한 값)
      code_hash, env  하루 기록에 적을 코드 지문·환경. allowed = L22 허용 {(code_hash, env_key(env))}(None 이면 생략)
      head       L18 점검용 HEAD 의 (판정 기록 줄 수, 앞부분 sha256). None 이면 생략
      universe_sha256 / meta_universe_sha256  L22 종목군 파일 지문 비교(둘 다 있을 때)
      brains     screener.scan_frames 의 brains (None = screener.BRAINS. 재현 W3 의 가짜 브레인용)

    순서: 사전 조건 → 장부·자료 확인(보유·대기 종목 D2·D3) → 스크리너 한 번(두 장부 공유) → 팀장 방식 →
          트레이너마다(마라토너→스프린터→파이오니어) A0→A1 순서로
          team.run_trainer(breaker=CircuitBreaker(inf, inf), cache=엄격 cache, h1=H1Day) → h1_check.check_day.

    돌려줌: BarResult. 엔진이 처리 중 찾은 L 과 check_day 의 L 이 모두 problems 에 있다. result.ok 가 False 면 저장하지 말 것
            (states·fingerprint 는 있으므로 errors.jsonl 에 남긴다).
    예외 (그 봉은 저장 안 함)
      H1PreconditionError(ValueError) — 사전 조건 위반(그 클래스 설명의 기준). L 이 아니다. 2b-2 는 종료 코드 4 로.
      H1DataProblem — D1(지수 봉 값 이상)·D2(보유·대기 종목 시세 없음)·D3(그 종목 t 행·시가 없음), 종료 코드 4.
      H1LogicError — 끝까지 처리할 수 없는 장부 논리 오류만(장부 6개의 시작일·last_date·상장폐지 등록이 서로 다름,
                     엄격 cache 에 없는 종목 L6, 장부 모양 L24 …). 늘 .code(L 번호)가 있고, .fingerprint(그때까지
                     장부 6개의 내용 지문, 못 내면 None)·.date·.problems 가 붙는다. 종료 코드 2."""
    mk = _mkey(market)
    _check_iso(t, "t")
    if leader_mode not in ("llm", "replay"):
        raise ValueError(f"leader_mode 는 'llm' 또는 'replay' (받은 값 {leader_mode!r})")
    for arm in ARMS:
        if arm not in states or any(tn not in states[arm] for tn in TRAINERS):
            _pre(f"장부 6개가 다 있어야 해요({arm})")
    flat = [states[a][tn] for a in ARMS for tn in TRAINERS]
    starts = {st["start_date"] for st in flat}
    lasts = {st["last_date"] for st in flat}
    if len(starts) != 1 or len(lasts) != 1:
        raise _attach(H1LogicError(f"여섯 장부의 시작일·last_date 가 다름 {sorted(map(str, starts | lasts))}",
                                   code="L16"), t, states)
    S, last = starts.pop(), lasts.pop()
    if last is None and t != S:
        _pre(f"처음 처리하는 봉은 S({S}) 여야 해요 (받은 t {t})")
    if last is not None and t <= last:
        _pre(f"봉 {t} 는 이미 처리됨(last_date {last}) — 멱등 확인이 먼저 걸러야 함")
    if prev_cal_date is None:
        _pre("prev_cal_date(달력의 바로 앞 거래일)가 없음 — S 에서도 S 전 거래일을 줘야 해요")
    _check_iso(prev_cal_date, "prev_cal_date")
    if not prev_cal_date < t:
        _pre(f"prev_cal_date {prev_cal_date} ≥ t {t}")
    if last is not None and prev_cal_date != last:
        _pre(f"달력의 앞 거래일 {prev_cal_date} ≠ 장부 last_date {last} (빠진 봉 → D4·D5 를 먼저 볼 것)")
    if calendar is not None:
        cal = list(calendar)
        if t not in cal or cal.index(t) == 0 or cal[cal.index(t) - 1] != prev_cal_date:
            _pre(f"달력에 {t} 가 없거나 그 앞 거래일이 prev_cal_date {prev_cal_date} 가 아님")
    if idle.code != idle_code(mk) or idle.date != t:
        _pre(f"대기 자산 봉이 다름 ({idle.code} {idle.date}, 기대 {idle_code(mk)} {t})")
    for v in (idle.open, idle.close):
        if not (_isnum(v) and math.isfinite(v) and v > 0):
            raise H1DataProblem("D1", f"대기 자산 {idle.code} {t} 시가·종가가 이상함 ({idle.open!r}, {idle.close!r})")
    halted = frozenset(halted)
    try:
        regs = delist_registrations(states)
    except H1LogicError as e:
        raise _attach(e, t, states)
    if delist is not None:
        given = {c: {"last_date": v["last_date"], "last_close": v["last_close"]} for c, v in delist.items()}
        if given != regs:
            _pre(f"delist 인자 {sorted(given)} 가 장부 corp_actions 의 상장폐지 등록 {sorted(regs)} 와 다름")
    gone = {c for c, v in regs.items() if t > v["last_date"]}     # 이 봉에서 정리할 종목만 시세 확인에서 뺀다(B-4)

    # 엄격 cache (t 이하)
    cut = {code: cut_frame(df, t) for code, df in frames.items()}
    strict = StrictFrames(cut)

    # 자료 준비 확인 (D3 의 장부 쪽: 보유·대기 종목은 t 확정 행, 대기 주문 종목은 시가까지)
    for st in flat:
        pend = {o["code"] for o in st["pending"]}
        for code in (set(st["positions"]) | pend) - gone:
            if code not in cut or cut[code] is None:
                raise H1DataProblem("D2", f"보유·대기 종목 {code} 시세 없음")
            row = _row_at(cut[code], t)
            if code in halted:
                if row is not None:
                    _pre(f"{code}: 정지 목록에 있는데 {t} 확정 행이 있음(정지 판정과 시세가 서로 다름)")
                continue
            if row is None:
                raise H1DataProblem("D3", f"보유·대기 종목 {code} 의 {t} 확정 행 없음(정지 아님)")
            if code in pend and main.open_price(row) is None:
                raise H1DataProblem("D3", f"대기 주문 종목 {code} 의 {t} 시가 없음")

    # 1. 스크리너 한 번 (두 장부 공유)
    found, used = screener.scan_frames(cut, list(universe), asof=t, brains=brains)

    # 2. 팀장 방식
    clock = now if now is not None else _local_now
    if leader_mode == "replay":
        mode = "replay"
    else:
        mode = "llm" if _aware(clock()) < next_open(mk, t) else "late"
    late = mode == "late"
    leader = Leader(mk, t, decisions, mode, now=clock, ask=ask, cli_version=cli_version)
    run_at = _aware(clock()).isoformat(timespec="seconds")
    n_rec0 = len(decisions)

    # 3. 트레이너마다 A0 → A1
    try:
        before = clone_states(states, mk)
        after = clone_states(states, mk)
    except H1LogicError as e:
        raise _attach(e, t, None)
    engine_problems = []
    days = {arm: H1Day(mk, arm, idle, leader, start_date=S, prev_cal_date=prev_cal_date, mode=mode, late=late,
                       halted=halted, delist=regs, code_hash=code_hash, env=env, screened=found, run_at=run_at,
                       problems=engine_problems)
            for arm in ARMS}
    caps = main.CONFIG["종목상한"]
    lines = []
    try:
        for tname in TRAINERS:
            for arm in ARMS:
                st = after[arm][tname]
                line, st2 = team.run_trainer(tname, st["start_cash"], caps[tname], CircuitBreaker(*LEDGER_BREAKER),
                                             found.get(tname, []), t, st=st, cache=strict, mk=mk, h1=days[arm])
                if st2 is not st or not st["days"] or st["days"][-1]["date"] != t:
                    engine_problems.append(h1_check.Problem("L", "L16", mk, arm, tname, t,
                                                            f"봉 {t} 하루 기록이 생기지 않음({line})"))
                if st["stopped"]:
                    engine_problems.append(h1_check.Problem("L", "L2", mk, arm, tname, t,
                                                            "장부 서킷이 걸림(끈 서킷이어야 함)"))
                lines.append(f"{arm} {line}")
    except H1LogicError as e:
        raise _attach(e, t, after, engine_problems)

    # 4. 점검
    problems = list(engine_problems)
    problems += h1_check.check_day(mk, t, before, after, cut, idle, calendar, halted, decisions, allowed,
                                   head=head, universe_sha256=universe_sha256,
                                   meta_universe_sha256=meta_universe_sha256)
    new_records = decisions.records()[n_rec0:]
    if late:
        problems.append(h1_check.Problem("W", "W1", mk, None, None, t, "늦은 봉(다음 장 시작 뒤 처리) → 팀장 폴백"))
    for code in sorted(halted):
        problems.append(h1_check.Problem("W", "W2", mk, None, None, t, f"{code} 거래정지"))
    for rec in new_records:
        if rec.get("status") != "ok":
            problems.append(h1_check.Problem("W", "W3", mk, None, rec.get("trainer"), t,
                                             f"팀장 폴백 {rec.get('code')}: {rec.get('status')}"))
    return BarResult(date=t, states=after, problems=problems, lines=lines, found=found, used=used, mode=mode,
                     late=late, llm_calls=leader.llm_calls, late_calls=leader.late_calls, new_records=new_records,
                     fingerprint=_safe_fingerprint(after))
