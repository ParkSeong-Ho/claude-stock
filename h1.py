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
- IdleBar(대기 자산 그날 시가·종가), StrictFrames(없는 종목을 찾으면 바로 L6 오류인 시세 묶음), Fetched(받은 시세 모양 —
  h1_data.py 에 있고 여기서 다시 내보냄)
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

단계 2b-2 "실행기"(이 파일 뒤쪽 '2b-2 실행기' 절): 사람이 치는 명령과 파일 저장.
- 명령: python h1.py start|run|restart|corp-action|amend-rules|status --market us|kr …  (종료 코드는 설계 §3.9)
- 경로(모두 state/h1 아래인지 확인), 잠금(state/h1/h1-<시장>.lock, replay_pass 쓰기는 h1-global.lock, 최대 30분),
  관문(code_hash·env 가 replay_pass.json 에 있나)
- 시세 받기 층은 h1_data.py(fetch·load_idle·fetched_from_raw·DataSource): ⑥-i 로 고칠 수 있는 유일한 코드 파일(단계 4 F-9)
- 자료 점검 D1·D2·D4·D5·D6·D7(D3 는 엔진 run_bar 가 봄), 커밋 지점(HEAD.json)·백업·엄격 읽기·L24
- 일지: runs.jsonl·errors.jsonl·restarts.jsonl·changes.jsonl·<시장>/calendar.jsonl·<시장>/corp_actions.jsonl
- 재현 통과 기록: record_replay_pass(추가만, 봉인 replay_pass.seal.json) — 단계 5 h1_replay.py 는 replay_entry(…) 로 만든
  줄(파일별 sha256·자료 받기 골든 지문 포함)을 이 함수로만 쓴다

단계 4(구현 전체 독립 검토, docs/h1-review-4.md) F-1~F-10 반영
- ⑥ 코드 동결을 실제로 확인(freeze_transition·freeze_window): 창 안 지문이 바뀐 곳마다 파일별 sha256·재현 장부 내용 지문·
  자료 받기 골든·changes 기록. 허용은 h1_data.py·라이브러리 버전(⑥-i), 세율 표 값(⑥-ii), h1_check.py(④ 기록) 뿐.
  관문 run 은 위반이면 종료 코드 3, 보고서 --final·status 는 ⑥ 칸(F-1·F-9)
- 사전 등록 숫자 고정: 첫 start 때 state/h1/prereg_<시장>.json, 그 뒤 모든 판단이 그 값(F-2)
- corp-action --delist 는 --confirm <코드> 와 '거래가 정말 없음' 증거, --cancel-delist 로 정리 전 취소(F-3)
- restart 는 --confirm <시장>, --reason L|backlog|rule-change 와 일지 근거, --note(F-4)
- ④ 자동 기록은 code_hash 가 바뀌었을 때만(F-5), 시장별 잠금·판정 기록·일지 한 번 쓰기(F-7), claude -p 는 빈 폴더에서(F-8)
엔진 부분(run_bar 까지)은 파일을 쓰지 않는다(판정 기록 추가만 예외 — 장부보다 먼저 디스크에 있어야 하므로, 설계 §3.6).

import 관계: h1 → team(그 밖의 운영 모듈) / team 은 h1 을 import 하지 않는다. h1_check 와 h1 은 서로를 모듈째로만
import 한다(모듈을 읽는 순간에는 서로의 이름을 쓰지 않음 → 어느 쪽을 먼저 읽어도 됨). h1_report 는 window_counts
(status·실행 끝 요약의 일지 숫자 — 보고서와 같은 함수, 단계 3) 안에서만 늦게 import 한다.
"""
from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import sys
import time
import traceback
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import analyst
import h1_check
import h1_data
import main
import markets
import screener
import team
from h1_data import DataSource, Fetched, fetch, fetched_from_raw, load_idle   # noqa: F401 (단계 4 F-9: 받기 층)
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
CODE_FILES = ("team.py", "h1.py", "h1_data.py", "h1_check.py", "h1_report.py", "h1_replay.py",
              "main.py", "markets.py", "paper_wallet.py",
              "screener.py", "analyst.py", "risk_guard.py", "metrics.py",
              "marathoner_brain.py", "sprinter_brain.py", "pioneer_brain.py",
              "prompts/마라토너.md", "prompts/스프린터.md", "prompts/파이오니어.md")
# EPS_CASH·EPS_REL 은 h1_check.py 에 있고, rule_constants() 가 함께 적는다(§2.2 ⑩)
ENV_PACKAGES = ("pandas", "numpy", "ta", "FinanceDataReader")   # + python 버전
# ⑥ 코드 동결(단계 4 F-1·F-9): 판정 창 안에서 바뀌어도 되는 코드 파일과 그 조건(freeze_transition 이 확인)
FREEZE_DATA_FILES = ("h1_data.py",)               # ⑥-i 자료 문제 고침: 이 파일만(+ ENV_PACKAGES 버전)
FREEZE_TAX_FILE = "h1.py"                         # ⑥-ii 세율 줄 추가: h1.py 의 KR_SELL_TAX 값만(amend-rules 기록)
FREEZE_CHECK_FILE = "h1_check.py"                 # ④ 점검 함수 거짓 양성 고침: changes.jsonl false_positive 기록이 있을 때만

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
    """실행 거절 → 종료 코드 3·5·6·8 (code 속성). 2b-2 의 관문·잠금·밀린 봉·장부 없음이 쓴다.
    (2b-2 에서 더함) code 9 = 명령 인자 오류·조건 불충족(설계 §3.9 에 없는 번호. 아무것도 바꾸지 않음)."""

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
    """팀장 판정 기록 state/h1/analyst_cache_<시장>.jsonl — 한 줄 = 기록 하나, 추가만 한다(고치기·지우기 없음).

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
                    _fsync_fd(f.fileno())                # 맥이면 F_FULLFSYNC 까지(2b-2 검토 C-14)
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
                _fsync_fd(fd)                        # 줄마다 디스크에 (장부보다 먼저). 맥이면 F_FULLFSYNC 까지(C-14)
                self._add(json.loads(line), line)
        finally:
            os.close(fd)
        if new:                                      # 새 파일이면 폴더 항목도 디스크에
            try:
                dfd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    _fsync_fd(dfd)
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
             "delist_cancel": {"code": (_STR,)},                       # 단계 4 F-3: 상장폐지 등록 취소
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


def active_delists(corp_actions) -> dict:
    """corp_actions 를 순서대로 걸어 지금 살아 있는 상장폐지 등록 {code: 등록 줄}. "delist_cancel" 줄은 그 종목의 앞 등록을
    지운다(단계 4 F-3 — 엔진 a′·D6·L23 모두 취소된 등록을 보지 않는다)."""
    out = {}
    for ca in corp_actions:
        if ca.get("kind") == "delist":
            out[ca["code"]] = ca
        elif ca.get("kind") == "delist_cancel":
            out.pop(ca.get("code"), None)
    return out


def delist_registrations(states) -> dict:
    """장부 corp_actions 의 상장폐지 등록(취소된 것 빼고) → {code: {"last_date", "last_close"}} (2b-1 검토 B-4: 출처는
    이것 하나). 여섯 장부의 등록이 서로 다르면 H1LogicError(code="L23")."""
    seen = None
    for arm, tn, st in _flat(states):
        regs = {}
        for code, ca in active_delists(st["corp_actions"]).items():
            regs[code] = {"last_date": ca["last_date"], "last_close": ca["last_close"]}
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


# =====================================================================================================
# ============================ 2b-2 실행기 (설계 §2.3 준비 1~10, §2.5, §3.3, §3.7, §3.9) ============================
# =====================================================================================================
#
# 사람이 치는 명령(start·run·restart·corp-action·amend-rules·status)과 파일 저장을 맡는다.
# 큰 흐름 (run 한 번)
#   1 잠금 → 2 runs.jsonl 시작 줄 → 3 관문(code_hash·env 가 replay_pass.json 에 있나) → 4 장부 읽기(HEAD 와 sha256 비교,
#   다르면 백업으로 되살림, 그래도 아니면 L24) → 5 대기 자산 시세(D1) → 7 종목 시세(D2·W4·W5) → 6 달력(D4·D5·D7) →
#   8 소급 수정(D6) → 9 처리할 봉 정하기(없으면 0, 5봉 넘으면 6) → 10 봉마다 run_bar → 점검 통과면 커밋(백업 → 장부 6개 → HEAD)
# 운영 장부(state/team_*.json, state/kr/)는 열지 않는다: team._load·team._save·main.load_state_file 을 부르지 않고,
# 모든 경로는 h1_path 가 "H1 폴더 아래인지" 확인한다.
#
# 2b-2 독립 검토(docs/h1-review-2b2.md) C-1~C-18 반영
# - 환경 문제(OSError·MemoryError)는 L 이 아니라 종료 코드 4·kind "ENV", Ctrl-C 는 130, 인자·조건 오류는 9(C-1·C-15)
# - 분할: --date = 효력일(> last_date), 같은 분할 두 번 거절, 지금 D6 이 같은 비율의 분할 모양일 때만, 분수 r,
#   D6 의 ÷r 은 '분할을 장부에 적용하기 전(applied_after 이하) 기록'에만(C-2·C-9·C-16). 정정 확정은 분할 모양 거절(C-10)
# - 일지 start_date 는 장부를 읽기 전에도 채움(못 읽으면 "unknown" → 지금 창으로 셈)(C-3)
# - 종목군 절반 넘게 못 받으면 D2, 확인용 대형주 실패는 "D7 판단 못 함"을 남김(C-4)
# - replay_pass.json 은 record_replay_pass 로만 추가(봉인 파일과 맞춤), 줄거나 바뀌면 관문 3(C-5)
# - restart 는 의도 줄 → 옮김 → 끝 줄(C-6), 일지는 장부·meta 에서 맞춰 채움(C-7), 늦은 start 거절(C-8)
# - corp-action 도 관문·규칙 확인(C-11), 보유·대기 종목 종가·대기 자산 시가·종가 이상 → D3(C-13)
# - 새 폴더·이름 바꾼 파일의 부모 fsync, 맥이면 F_FULLFSYNC(C-14)

EXIT_OK = 0
EXIT_PY = 1             # h1.py 가 직접 돌려주지 않음: cli 에 닿기 전에 파이썬이 죽음(import 실패·설치 문제 등, traceback 있음)
EXIT_LOGIC = 2          # 장부 논리 오류(L1~L24) 또는 코드 버그(예상 밖 예외)
EXIT_GATE = 3           # 재현 미통과 코드·환경(통과 기록이 줄거나 바뀐 것 포함), 또는 규칙 상수가 시작 때와 다름
EXIT_DATA = 4           # 자료 문제(D1~D6), 사전 조건 어긋남(PRE), 환경 문제(ENV: 디스크 가득·권한·입출력·메모리)
EXIT_LOCK = 5           # 잠금 30분 대기 초과
EXIT_BACKLOG = 6        # 밀린 봉 5개 초과 → 창 실패
EXIT_D7 = 7             # 기준 지수 늦음(앞 봉까지는 저장)
EXIT_NO_LEDGER = 8      # 장부 없음(start 필요) / start·restart 거절
EXIT_USAGE = 9          # 명령 인자 오류, corp-action·amend-rules 조건 불충족 → 아무것도 바꾸지 않음 (2b-2 검토 C-15)
EXIT_INTERRUPT = 130    # 사람이 멈춤(Ctrl-C). L 아님 — 저장된 봉까지는 안전, 다음 실행이 이어서(필요하면 백업으로 되살림)
EXIT_TEXT = {0: "정상", 1: "파이썬이 명령 처리 전에 멈춤(설치·코드 문제 — traceback 확인)",
             2: "장부 논리 오류(L) 또는 코드 버그 — 그 봉 저장 안 함, 재시작 대상(코드 버그면 고친 뒤 판단)",
             3: "재현을 통과하지 않은 코드·환경 또는 규칙이 시작 때와 다름 — 저장 안 함",
             4: "자료 문제(D)·환경 문제(ENV) — 그 봉 저장 안 함, 다음 실행이 다시", 5: "다른 H1 명령이 잠금 중(30분 초과)",
             6: "밀린 봉 5개 초과 — 판정 창 실패(재시작 대상)", 7: "기준 지수 늦음(D7) — 처리할 수 있던 봉까지 저장",
             8: "장부 없음(start 필요) 또는 start·restart 거절",
             9: "명령 인자 오류 또는 corp-action·amend-rules 조건 불충족(아무것도 안 바뀜)",
             130: "사람이 멈춤(Ctrl-C) — 저장된 봉까지는 안전"}

LOCK_POLL_S = 5.0                    # 잠금을 다시 시도하는 간격(초)
_lock_clock = time.monotonic         # 잠금 대기 시계 — 시험에서 가짜 시계로 바꿔 끼운다
_lock_sleep = time.sleep             # 잠금 대기 쉬기 — 시험에서 바꿔 끼운다(실제로 기다리지 않게)
DESIGN_DOC = "docs/h1-forward-design.md"
HEAD_KEYS = ("last_date", "files", "meta_sha256", "decision_log", "run_id", "written_at")
META_KEYS = ("market", "start_date", "restart_no", "created_at", "rules", "universe_sha256", "code_hash_at_start",
             "env_at_start", "design_doc_sha256", "ledger_breaker", "shadow_breaker")
LEDGER_RELS = tuple(f"{arm}/team_{tn}.json" for arm in ARMS for tn in TRAINERS)    # 시장 폴더 기준 상대 경로
META_REL = "meta.json"
REPLAY_FILE = "replay_pass.json"          # 재현 통과 기록(추가만, record_replay_pass 로만 씀)
REPLAY_SEAL = "replay_pass.seal.json"     # 통과 기록 줄마다의 지문(지난 줄이 줄거나 바뀌면 관문 거절 3, 2b-2 검토 C-5)
_DIST_NAMES = {"FinanceDataReader": ("finance-datareader", "FinanceDataReader")}


# ============================ 경로 (F1: 모두 H1 폴더 아래) ============================

def _root(root=None) -> Path:
    """H1 폴더. None 이면 H1_DIR(부를 때의 값 — 시험에서 바꿔 끼울 수 있게).
    운영 상태 폴더(team.STATE_DIR) 자체나 그 위 폴더는 받지 않는다(운영 state/kr/ 와 겹치지 않게)."""
    base = Path(H1_DIR if root is None else root)
    rb, op = base.resolve(), Path(team.STATE_DIR).resolve()
    if rb == op or rb in op.parents:
        raise ValueError(f"H1 폴더 {rb} 가 운영 상태 폴더 {op} 와 같거나 그 위예요(설계 F1)")
    return base


def h1_path(root, *parts) -> Path:
    """root/parts… 경로. 조각에 '/'·'..' 이 있거나 (심볼릭 링크 등으로) 결과가 H1 폴더 밖이면 ValueError."""
    base = _root(root)
    for part in parts:
        if not isinstance(part, str) or part in ("", ".", "..") or any(ch in part for ch in "/\\\0"):
            raise ValueError(f"H1 경로 조각이 이상해요: {part!r}")
    p = base.joinpath(*parts)
    rb, rp = base.resolve(), p.resolve()
    if rp != rb and rb not in rp.parents:
        raise ValueError(f"H1 경로 {rp} 가 H1 폴더 {rb} 밖이에요(설계 F1)")
    return p


def _rel_path(root, base_parts, rel) -> Path:
    return h1_path(root, *base_parts, *rel.split("/"))


def market_dir(market, root=None) -> Path:
    """state/h1/<market>/ — 장부 6개·meta·HEAD·calendar.jsonl·corp_actions.jsonl·backup/."""
    return h1_path(root, _mkey(market))


def ledger_path(market, arm, trainer, root=None) -> Path:
    """장부 파일 state/h1/<market>/<A0|A1>/team_<트레이너>.json (F1). 모르는 장부·트레이너·H1 폴더 밖이면 ValueError."""
    if arm not in ARMS:
        raise ValueError(f"모르는 장부 {arm!r}")
    if trainer not in TRAINERS:
        raise ValueError(f"모르는 트레이너 {trainer!r}")
    return h1_path(root, _mkey(market), arm, f"team_{trainer}.json")


def universe_path(market, root=None) -> Path:
    """고정 종목군 파일 state/h1/universe/<market>.json (Q7, 재시작해도 그대로)."""
    return h1_path(root, "universe", f"{_mkey(market)}.json")


def decisions_path(root=None, market=None) -> Path:
    """팀장 판정 기록 state/h1/analyst_cache_<market>.jsonl — 시장별 파일(단계 4 F-7: 두 시장이 잠금을 따로 쓰므로
    HEAD 의 판정 기록 지문(decision_log)도 그 시장 파일 하나로 센다). market 은 꼭 준다."""
    if market is None:
        raise ValueError("decisions_path 에는 시장(market)이 필요해요(시장별 판정 기록, 단계 4 F-7)")
    return h1_path(root, f"analyst_cache_{_mkey(market)}.jsonl")


# ============================ 파일 쓰기·읽기 도움 ============================

def _say(*args, **_kw):
    """화면(launchd 로그) 출력. 출력이 막혀도(BrokenPipe·닫힌 stdout) 명령은 멈추지 않는다(2b-2 검토 C-1)."""
    try:
        print(*args, flush=True)
    except (OSError, ValueError):
        pass


def _fsync_fd(fd) -> None:
    """파일·폴더를 디스크까지. os.fsync 뒤, 맥처럼 fcntl.F_FULLFSYNC 가 있으면 그것도 한다
    (맥의 fsync 는 디스크 캐시까지 비우지 않음, 2b-2 검토 C-14). F_FULLFSYNC 를 못 하는 파일 시스템은 fsync 로 충분."""
    os.fsync(fd)
    full = getattr(fcntl, "F_FULLFSYNC", None)
    if full is not None:
        try:
            fcntl.fcntl(fd, full)
        except OSError:
            pass


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(p) -> str | None:
    """파일 sha256. 파일이 없으면 None. 그 밖의 읽기 오류(권한·입출력)는 그대로 올린다(환경 문제 ENV, C-1)."""
    try:
        return _sha256_bytes(Path(p).read_bytes())
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def _dump(obj) -> bytes:
    """장부·HEAD·meta 파일 글자. float 는 repr 그대로(비트가 같으면 글자도 같음), NaN·inf 는 거절."""
    return (json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=1) + "\n").encode("utf-8")


def _fsync_dir(d) -> None:
    """폴더 항목(새 파일·이름 바꾼 파일·새 하위 폴더)을 디스크에. 폴더 fsync 를 못 하는 파일 시스템이면 조용히 넘어간다."""
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        _fsync_fd(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _mkdirs(d) -> None:
    """없는 폴더를 위에서부터 하나씩 만들고, 새로 만든 폴더마다 그 부모 폴더를 fsync 한다(2b-2 검토 C-14)."""
    d = Path(d)
    missing = []
    p = d
    while not p.exists():
        missing.append(p)
        if p.parent == p:
            break
        p = p.parent
    for q in reversed(missing):
        try:
            q.mkdir()
        except FileExistsError:
            continue
        _fsync_dir(q.parent)


def _write_fsync(path: Path, data: bytes) -> None:
    _mkdirs(path.parent)
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        _fsync_fd(f.fileno())


def _write_atomic(path: Path, data: bytes) -> None:
    """임시 파일(.tmp)에 다 쓰고 fsync → os.replace → 폴더 fsync. 쓰는 중 꺼져도 반쯤 쓴 파일이 남지 않는다."""
    tmp = path.with_name(path.name + ".tmp")
    _write_fsync(tmp, data)
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _clean(obj):
    """일지(JSONL)에 적을 수 있는 값으로: NaN·inf → 글자, 집합 → 정렬 목록, 그 밖의 객체 → 글자."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_clean(v) for v in obj)
    if isinstance(obj, float) and not math.isfinite(obj):
        return repr(obj)
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _append_line(path: Path, rec: dict) -> None:
    """JSONL 한 줄 추가 + fsync (일지용). 새 파일이면 폴더도 fsync.
    한 줄은 O_APPEND 로 연 파일에 **os.write 한 번**으로 쓴다(단계 4 F-7: 두 시장 명령이 runs/errors/restarts/changes.jsonl 을
    잠금 없이 같이 써도 줄이 섞이지 않게). 한 번에 다 쓰지 못하면(디스크 가득 등) OSError → 환경 문제(ENV).
    앞 줄이 반쯤 쓰인 채 꺼졌으면 새 줄에서 시작한다(깨진 줄은 읽을 때 건너뜀)."""
    line = (json.dumps(_clean(rec), ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
    _mkdirs(path.parent)
    new = not path.exists()
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        end = os.lseek(fd, 0, os.SEEK_END)
        if end > 0 and os.pread(fd, 1, end - 1) != b"\n":
            line = b"\n" + line
        n = os.write(fd, line)
        if n != len(line):
            raise OSError(errno.EIO, f"일지 한 줄을 한 번에 다 쓰지 못함({n}/{len(line)}바이트): {path.name}")
        _fsync_fd(fd)
    finally:
        os.close(fd)
    if new:
        _fsync_dir(path.parent)


def _append_log(root, name: str, rec: dict) -> None:
    _append_line(h1_path(root, name), rec)


def read_jsonl(path) -> list:
    """일지 JSONL 읽기(너그럽게: 깨진 줄은 건너뜀 — 장부가 아니라 실행 기록이라서)."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for raw in p.read_bytes().split(b"\n"):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _read_log(root, name):
    return read_jsonl(h1_path(root, name))


def _parse_file(path: Path, what: str):
    """장부·HEAD·meta 파일을 엄격하게 읽는다. 없음·UTF-8 아님·깨진 JSON·NaN → H1LogicError(L24)."""
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise H1LogicError(f"{what} 파일이 없어요 ({path.name})", code="L24")
    except UnicodeDecodeError:
        raise H1LogicError(f"{what} 글자가 깨졌어요(UTF-8 아님)", code="L24")
    try:
        return json_loads_strict(text)
    except H1LogicError as e:
        raise H1LogicError(f"{what}: {e}", code="L24")


def _iso(t) -> str:
    return _aware(t).isoformat(timespec="seconds")


def _norm(obj):
    """JSON 왕복한 모양(튜플 → 목록 등)으로 맞춰 비교하려고."""
    return json.loads(json.dumps(obj, ensure_ascii=False, allow_nan=False))


# ============================ 지문 · 관문 (§2.2 ②-3, §2.3 준비 3) ============================

def code_hash(repo=None, files=CODE_FILES) -> tuple:
    """코드 지문 (합친 sha256, {파일: sha256 또는 None}). 없는 파일은 None 으로 적어 '없다'는 사실도 지문에 들어간다.
    repo 기본은 이 파일이 있는 폴더."""
    base = Path(REPO if repo is None else repo)
    per = {}
    for f in files:
        try:
            per[f] = _sha256_bytes((base / f).read_bytes())
        except FileNotFoundError:
            per[f] = None
    return combine_code_hash(per), per


def combine_code_hash(files: dict) -> str:
    """{파일: sha256 또는 None}(code_hash 의 두 번째 값, 파일 순서 그대로) → 합친 code_hash. code_hash 와 같은 식이라
    재현 통과 기록의 files 로 code_hash 를 다시 계산해 맞는지 볼 수 있다(record_replay_pass, 단계 4 F-1)."""
    blob = json.dumps({"v": 1, "files": [[f, files[f]] for f in files]}, ensure_ascii=False, separators=(",", ":"))
    return _sha256_bytes(blob.encode("utf-8"))


def _without_tax_table(blob: bytes):
    """h1.py 글자에서 KR_SELL_TAX = (…) 의 값 부분만 '<KR_SELL_TAX>' 로 바꾼 글자(⑥-ii: 세율 표 말고는 그대로인지 보려고).
    파이썬으로 읽지 못하거나, KR_SELL_TAX 가 한 번의 글자 그대로(literal) 대입이 아니면 None."""
    import ast
    try:
        tree = ast.parse(blob)
    except (SyntaxError, ValueError):
        return None
    found = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "KR_SELL_TAX"]
    if len(found) != 1:
        return None
    v = found[0].value
    try:
        ast.literal_eval(v)
    except (ValueError, SyntaxError):
        return None
    starts, pos = [], 0                       # 줄마다 시작 바이트(ast 의 col_offset 은 UTF-8 바이트)
    for line in blob.splitlines(keepends=True):
        starts.append(pos)
        pos += len(line)
    a = starts[v.lineno - 1] + v.col_offset
    b = starts[v.end_lineno - 1] + v.end_col_offset
    return blob[:a] + b"<KR_SELL_TAX>" + blob[b:]


def tax_free_sha(repo=None):
    """h1.py 에서 세율 표(KR_SELL_TAX 값)만 뺀 글자의 sha256 (재현 통과 기록 h1_without_tax_table_sha256). 못 구하면 None."""
    try:
        blob = (Path(REPO if repo is None else repo) / "h1.py").read_bytes()
    except OSError:
        return None
    rest = _without_tax_table(blob)
    return None if rest is None else _sha256_bytes(rest)


# ---- 자료 받기 골든(단계 4 F-1·F-9): h1_data.py 를 고쳐도(⑥-i) 이 결과는 바이트까지 같아야 한다 ----
DATA_GOLDEN_DIR = ("tests", "golden_data")


def _golden_frame(spec):
    import pandas as pd
    df = pd.DataFrame([[math.nan if v is None else v for v in row] for row in spec["data"]],
                      index=pd.DatetimeIndex(spec["index"], name="Date"), columns=list(spec["columns"]),
                      dtype="float64")
    for c in spec.get("int_columns") or []:
        df[c] = df[c].astype("int64")
    return df


def _golden_value(v):
    if isinstance(v, float) and math.isnan(v):
        return "nan"
    if hasattr(v, "item"):
        v = v.item()
    return repr(v)


def _golden_df(df):
    if df is None:
        return None
    return {"index": [x.isoformat() for x in df.index], "columns": [str(c) for c in df.columns],
            "dtypes": [str(t) for t in df.dtypes],
            "data": [[_golden_value(v) for v in row] for row in df.itertuples(index=False, name=None)]}


def data_golden_outputs(golden_dir=None) -> bytes:
    """자료 받기 골든 결과 글자: tests/golden_data/cases.json 의 경우마다 가짜 FinanceDataReader(원본 = inputs/*.json,
    "raise" 면 받기 실패, "empty" 면 빈 표)로 h1_data.fetch·load_idle 을 불러 확정 시세 표(float 는 repr)·정지 날짜를
    정렬 JSON 으로. 이 함수(재는 쪽)는 h1.py 에 있어 ⑥-i 로 고칠 수 없다. 시험 tests/test_h1_data.py 가 저장된
    outputs.json 과 바이트 비교하고, 재현 통과 기록의 data_golden_sha256 은 이 글자의 sha256 이다."""
    import types
    gdir = Path(golden_dir) if golden_dir is not None else REPO.joinpath(*DATA_GOLDEN_DIR)
    cases = json.loads((gdir / "cases.json").read_text(encoding="utf-8"))
    out = []
    saved = sys.modules.get("FinanceDataReader", None)
    had = "FinanceDataReader" in sys.modules
    try:
        for case in cases:
            inp = case["input"]

            def reader(code, start, _case=case, _inp=inp):
                if code != _case["code"] or start != team.START:
                    raise RuntimeError(f"골든 경우 {_case['name']}: 다른 코드·시작일을 받으려 함 ({code}, {start})")
                if _inp == "raise":
                    raise ConnectionError("골든: 받기 실패 흉내")
                if _inp == "empty":
                    import pandas as pd
                    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
                return _golden_frame(json.loads((gdir / _inp).read_text(encoding="utf-8")))

            sys.modules["FinanceDataReader"] = types.SimpleNamespace(DataReader=reader)
            now = datetime.fromisoformat(case["now"])
            try:
                if case["kind"] == "fetch":
                    got = h1_data.fetch(case["market"], case["code"], now)
                    res = None if got is None else {"df": _golden_df(got.df), "halt_dates": sorted(got.halt_dates)}
                else:
                    res = {"df": _golden_df(h1_data.load_idle(case["market"], now))}
            except Exception as e:                       # 받기 층이 예외를 내는 것도 결과로 적는다
                res = {"error": type(e).__name__}
            out.append({"name": case["name"], "result": res})
    finally:
        if had:
            sys.modules["FinanceDataReader"] = saved
        else:
            sys.modules.pop("FinanceDataReader", None)
    return (json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def data_golden_digest(golden_dir=None) -> str:
    """자료 받기 골든 결과의 sha256 (재현 통과 기록 data_golden_sha256, ⑥ (c))."""
    return _sha256_bytes(data_golden_outputs(golden_dir))


def _pkg_version(name):
    for dist in _DIST_NAMES.get(name, (name,)):
        try:
            return importlib.metadata.version(dist)
        except Exception:
            pass
    try:
        v = getattr(importlib.import_module(name), "__version__", None)
        return str(v) if v is not None else None
    except Exception:
        return None


def env_info() -> dict:
    """실행 환경 지문 재료: 파이썬 버전 + ENV_PACKAGES(pandas·numpy·ta·FinanceDataReader) 버전(모르면 None)."""
    out = {"python": platform.python_version()}
    for name in ENV_PACKAGES:
        out[name] = _pkg_version(name)
    return out


def _entry_digest(e) -> str:
    return _sha256_bytes(json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8"))


def _read_seal(root):
    p = h1_path(root, REPLAY_SEAL)
    if not p.exists():
        return None
    seal = _parse_file(p, REPLAY_SEAL)
    if not isinstance(seal, dict) or not isinstance(seal.get("digests"), list) \
            or not all(isinstance(x, str) for x in seal["digests"]):
        raise H1LogicError(f"{REPLAY_SEAL} 모양이 달라요", code="L24")
    return seal


def replay_pass_entries(root=None) -> list:
    """state/h1/replay_pass.json 의 통과 기록 목록(없으면 빈 목록).
    봉인(replay_pass.seal.json, 줄마다의 지문)과 맞춰 본다(2b-2 검토 C-5): 지난 줄이 줄었거나 바뀌었거나, 봉인 없이
    더해진 줄이 있으면 H1Refused(3) — 장부 논리 오류(L22)가 아니라 관문 문제로 알린다. 깨진 파일은 H1LogicError(L24).
    record_replay_pass 가 봉인 → 목록 순서로 쓰므로, 목록이 봉인보다 딱 한 줄 짧은 것(그 사이에 꺼짐)은 받아 준다."""
    p = h1_path(root, REPLAY_FILE)
    data = []
    if p.exists():
        data = _parse_file(p, REPLAY_FILE)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
            raise H1LogicError(f"{REPLAY_FILE} 이 통과 기록(dict) 목록이 아니에요", code="L24")
    seal = _read_seal(root)
    if seal is None:
        if data:
            raise H1Refused(EXIT_GATE, f"{REPLAY_FILE} 에 봉인({REPLAY_SEAL})이 없어요 → 통과 기록은 "
                                       "h1.record_replay_pass(재현 h1_replay.py)로만 쓰세요")
        return []
    digs, sealed = [_entry_digest(e) for e in data], seal["digests"]
    if digs != sealed and digs != sealed[:-1]:
        if len(digs) > len(sealed) and digs[:len(sealed)] == sealed:
            why = "봉인 없이 더해진 줄이 있음(손으로 고침?)"
        else:
            why = "지난 통과 기록이 줄었거나 바뀜"
        raise H1Refused(EXIT_GATE, f"{REPLAY_FILE}: {why} → 지난 봉의 지문 확인이 불가능해요. 파일을 되돌리거나 "
                                   "재현을 다시 통과시킨 뒤(record_replay_pass) 실행하세요(장부 논리 오류 아님)")
    return data


REPLAY_REQUIRED = ("code_hash", "files", "env", "data_golden_sha256")


def replay_entry(ledger_fingerprints, **extra) -> dict:
    """재현 통과 기록 한 줄을 지금 코드·환경으로 채운다(단계 5 h1_replay.py 가 record_replay_pass 에 넘김, 단계 4 F-1).
    code_hash·files(파일별 sha256)·env·data_golden_sha256(자료 받기 골든)·h1_without_tax_table_sha256(세율 표만 뺀
    h1.py)·fingerprint_version·ledger_fingerprints(필수 창 장부 내용 지문) + extra(passed_at·report 등)."""
    ch, files = code_hash()
    return {"code_hash": ch, "files": files, "env": env_info(), "data_golden_sha256": data_golden_digest(),
            "h1_without_tax_table_sha256": tax_free_sha(), "fingerprint_version": FINGERPRINT_VERSION,
            "ledger_fingerprints": dict(ledger_fingerprints or {}), **extra}


def _check_replay_entry(entry):
    """record_replay_pass 가 받는 모양(단계 4 F-1): code_hash(글자)·files({파일: sha256 또는 None})·env(dict)·
    data_golden_sha256(글자)가 있고 code_hash == combine_code_hash(files). 아니면 ValueError."""
    if not isinstance(entry, dict):
        raise ValueError("통과 기록은 dict 여야 해요")
    miss = [k for k in REPLAY_REQUIRED if k not in entry]
    if miss:
        raise ValueError(f"통과 기록에 {miss} 가 없어요(h1.replay_entry 로 만드세요 — ⑥ 코드 동결 확인에 필요, 단계 4 F-1)")
    files = entry["files"]
    if not isinstance(entry["code_hash"], str) or not isinstance(entry["env"], dict) \
            or not isinstance(entry["data_golden_sha256"], str) or not entry["data_golden_sha256"]:
        raise ValueError("통과 기록 code_hash·env·data_golden_sha256 모양이 달라요")
    if not isinstance(files, dict) or not files \
            or not all(isinstance(k, str) and (v is None or isinstance(v, str)) for k, v in files.items()):
        raise ValueError("통과 기록 files 는 {파일: sha256 또는 None} 이어야 해요")
    if combine_code_hash(files) != entry["code_hash"]:
        raise ValueError("통과 기록 code_hash 가 files(파일별 sha256)로 계산한 값과 달라요")


def record_replay_pass(entry, root=None) -> int:
    """재현 통과 기록 한 줄 추가(설계 §5.6, 2b-2 검토 C-5). 전역 잠금(h1-global.lock, 단계 4 F-7) 아래에서 추가만 하고
    지난 줄은 고치거나 지우지 않는다. entry 는 replay_entry(…) 모양: code_hash·files·env·data_golden_sha256 필수
    (+ ledger_fingerprints·fingerprint_version·h1_without_tax_table_sha256·passed_at·report). 단계 5 h1_replay.py 는
    이 함수만 쓴다(직접 파일을 쓰지 않는다). 쓰는 순서: 봉인(줄마다 지문) → 목록 → changes.jsonl(바뀐 파일·환경 칸).
    지금 파일이 봉인과 맞지 않으면 H1Refused(3) 로 거절(아무것도 안 씀). 돌려줌: 기록 줄 수."""
    _check_replay_entry(entry)
    entry = _norm(entry)                                # JSON 으로 적을 수 있는지(NaN 없음)
    root = _root(root)
    with h1_lock(root):                                 # market 없음 = 전역 잠금
        old = replay_pass_entries(root)
        new = old + [entry]
        seal = {"v": 1, "count": len(new), "digests": [_entry_digest(e) for e in new]}
        _write_atomic(h1_path(root, REPLAY_SEAL), _dump(seal))
        _write_atomic(h1_path(root, REPLAY_FILE), _dump(new))
        prev = old[-1] if old else None
        pf = (prev or {}).get("files") if isinstance((prev or {}).get("files"), dict) else {}
        pe = (prev or {}).get("env") if isinstance((prev or {}).get("env"), dict) else {}
        fc = sorted(f for f in set(pf) | set(entry["files"]) if pf.get(f) != entry["files"].get(f)) if prev else None
        ec = sorted(k for k in set(pe) | set(entry["env"]) if pe.get(k) != entry["env"].get(k)) if prev else None
        _append_log(root, "changes.jsonl", {"at": _iso(_local_now()), "market": None, "kind": "replay-pass",
                                            "code_hash": entry["code_hash"], "env": entry["env"], "count": len(new),
                                            "files_changed_vs_prev": fc, "env_changed_vs_prev": ec,
                                            "data_golden_sha256": entry["data_golden_sha256"]})
    return len(new)


def check_gate(root=None, ch=None, env=None) -> set:
    """관문(설계 §2.3 준비 3): (code_hash, env_key(env)) 가 replay_pass.json 에 없으면 H1Refused(3).
    통과 기록이 봉인과 맞지 않거나(줄어듦·바뀜) 깨졌어도 3. 통과하면 L22 허용 목록(통과 기록 전부)을 돌려준다."""
    ch = code_hash()[0] if ch is None else ch
    env = env_info() if env is None else env
    try:
        entries = replay_pass_entries(root)
    except H1LogicError as e:
        raise H1Refused(EXIT_GATE, f"재현 통과 기록(replay_pass.json)을 읽지 못함: {e}")
    allowed = {(e.get("code_hash"), env_key(e.get("env"))) for e in entries}
    if (ch, env_key(env)) not in allowed:
        raise H1Refused(EXIT_GATE, f"재현(h1_replay.py)을 통과하지 않은 코드·환경이에요 (code_hash {ch[:12]}…, "
                                   f"python {env.get('python')}, pandas {env.get('pandas')}, "
                                   f"FinanceDataReader {env.get('FinanceDataReader')}) → 재현을 먼저 통과시키세요")
    return allowed


def allowed_fingerprints(root, gate, ch, env) -> set:
    """L22 허용 목록. 관문 실행(gate=True)은 replay_pass 의 통과 기록, gate=False(재현·시험)는 지금 지문 하나(R2-2)."""
    if gate:
        return check_gate(root, ch, env)
    return {(ch, env_key(env))}


def _design_sha():
    return _sha256_file(REPO / DESIGN_DOC)


# ============================ ⑥ 코드 동결 확인 (§2.2 ⑥, 단계 4 F-1) ============================

def _env_dict(e):
    return e if isinstance(e, dict) else {}


def _has_change(changes, **want) -> bool:
    return any(all(c.get(k) == v for k, v in want.items()) for c in changes)


def _freeze_pair(mk, o, n, nc, env_changed, changes, pending) -> dict:
    """재현 통과 줄 둘(o = 바뀌기 전, n = 바뀐 뒤)로 ⑥ 조건 (a)~(d) 를 본다. freeze_transition 의 도움."""
    why, kinds = [], []
    of, nf = o.get("files"), n.get("files")
    files = None
    if not isinstance(of, dict) or not isinstance(nf, dict) or not of or not nf:
        why.append("(a) 재현 통과 기록에 파일별 sha256(files)이 없어 무엇이 바뀌었는지 확인할 수 없음")
    else:
        files = sorted(f for f in set(of) | set(nf) if of.get(f) != nf.get(f))
        for f in files:
            if f in FREEZE_DATA_FILES:
                kinds.append("⑥-i 자료 받기 고침(h1_data.py)")
            elif f == FREEZE_TAX_FILE:
                to, tn = o.get("h1_without_tax_table_sha256"), n.get("h1_without_tax_table_sha256")
                if not (isinstance(to, str) and to and to == tn):
                    why.append(f"{f} 가 세율 표(KR_SELL_TAX) 밖에서도 바뀜 → ⑤-c 재시작 대상")
                elif "amend" in pending or _has_change(changes, kind="amend-rules", status="done", market=mk,
                                                       code_hash=nc):
                    kinds.append("⑥-ii 세율 줄 추가")
                else:
                    why.append("(d) 세율 표만 바뀌었는데 그 코드로 한 amend-rules 기록(changes.jsonl)이 없음")
            elif f == FREEZE_CHECK_FILE:
                if "fp" in pending or _has_change(changes, kind="false_positive", market=mk, code_hash_new=nc):
                    kinds.append("④ 점검 함수 고침")
                else:
                    why.append(f"{f}(점검 함수)가 바뀌었는데 그 코드의 ④ 거짓 양성 기록(false_positive)이 없음 → ⑤-c")
            else:
                why.append(f"{f} 가 바뀜 → ⑥ 이 허용하지 않는 변경(⑤-c 재시작 대상)")
    bad_env = [k for k in env_changed if k not in ENV_PACKAGES]
    if bad_env:
        why.append(f"환경 {bad_env} 이 바뀜 → ⑥ 이 허용하는 것은 {list(ENV_PACKAGES)} 버전뿐(파이썬은 그대로)")
    elif env_changed:
        kinds.append("⑥-i 라이브러리 버전")
    lo, ln = o.get("ledger_fingerprints"), n.get("ledger_fingerprints")
    if not (isinstance(lo, dict) and lo and lo == ln and o.get("fingerprint_version") == n.get("fingerprint_version")):
        why.append("(b) 두 재현 통과 기록의 장부 내용 지문(ledger_fingerprints)이 비었거나 다름 = 장부 계산이 바뀌었을 수 있음")
    go, gn = o.get("data_golden_sha256"), n.get("data_golden_sha256")
    if not (isinstance(go, str) and go and go == gn):
        why.append("(c) 자료 받기 골든(data_golden_sha256)이 없거나 다름")
    if any(k.startswith("⑥-i ") for k in kinds) and not any(
            c.get("kind") == "replay-pass" and c.get("code_hash") == nc and env_key(c.get("env")) == env_key(n.get("env"))
            for c in changes):
        why.append("(d) changes.jsonl 에 바뀐 코드·환경의 재현 통과 기록 줄이 없음")
    return {"ok": not why, "why": why, "files": files, "env": list(env_changed), "kinds": sorted(set(kinds))}


def freeze_transition(market, old, new, entries, changes, pending=()) -> dict:
    """⑥ 코드 동결(단계 4 F-1): 판정 창 안에서 코드·환경 지문이 old → new 로 바뀐 것이 허용되는가.
    old·new = (code_hash, env dict). entries = replay_pass_entries, changes = changes.jsonl 줄.
    pending = 이 명령이 곧 적을 기록("amend" = amend-rules done, "fp" = 아직 판정하지 않은 ④ 후보가 있음).
    허용 조건(모두):
      (a) 두 지문 모두 재현 통과 줄이 있고, 파일별 sha256(files)으로 본 바뀐 파일이
          h1_data.py(⑥-i) / h1.py 의 세율 표 값만(⑥-ii, h1_without_tax_table_sha256 같음 + amend-rules 기록) /
          h1_check.py(④ false_positive 기록) 뿐. 환경은 파이썬 그대로 ENV_PACKAGES 버전만(⑥-i)
      (b) 두 통과 줄의 ledger_fingerprints 가 비어 있지 않고 같음(fingerprint_version 도 같음)
      (c) 두 통과 줄의 data_golden_sha256(자료 받기 골든)이 같음
      (d) changes.jsonl 에 그 변경 기록(⑥-i = 그 지문의 replay-pass 줄, ⑥-ii = amend-rules done, ④ = false_positive)
    한 지문에 통과 줄이 여럿이면 조건을 채우는 짝이 하나라도 있으면 허용.
    돌려줌: {"ok", "why": [어긴 조건…], "files": [바뀐 파일] 또는 None, "env": [바뀐 환경 칸], "kinds": [허용 종류]}"""
    mk = _mkey(market)
    (oc, oe), (nc, ne) = old, new
    oe, ne = _env_dict(oe), _env_dict(ne)
    olds = [e for e in entries if e.get("code_hash") == oc and env_key(e.get("env")) == env_key(oe)]
    news = [e for e in entries if e.get("code_hash") == nc and env_key(e.get("env")) == env_key(ne)]
    env_changed = sorted(k for k in set(oe) | set(ne) if oe.get(k) != ne.get(k))
    if not olds or not news:
        return {"ok": False, "files": None, "env": env_changed, "kinds": [],
                "why": ["(a) " + ("바뀌기 전" if not olds else "바뀐 뒤") + " 코드·환경의 재현 통과 기록이 없음"]}
    best = None
    for o in reversed(olds):
        for n in reversed(news):
            r = _freeze_pair(mk, o, n, nc, env_changed, changes, tuple(pending))
            if r["ok"]:
                return r
            if best is None:
                best = r
    return best


def freeze_window(market, rows, entries, changes) -> list:
    """하루 기록(날짜 순, 한 장부) 중 코드·환경 지문이 바뀐 지점마다 freeze_transition 결과
    [{"date", "from", "to", "ok", "why", "files", "env", "kinds"}]. 보고서 ⑥ 칸·status 가 쓴다."""
    out, prev = [], None
    for r in rows:
        cur = (r.get("code_hash"), _env_dict(r.get("env")))
        if prev is not None and (cur[0], env_key(cur[1])) != (prev[0], env_key(prev[1])):
            t = freeze_transition(market, prev, cur, entries, changes)
            out.append({"date": r.get("date"), "from": prev[0], "to": cur[0], **t})
        prev = cur
    return out


# ============================ 사전 등록 숫자 고정 (§2.2 ⑩, 단계 4 F-2) ============================

TAX_KEY = "stock_sell_tax"


def prereg_path(market, root=None) -> Path:
    """state/h1/prereg_<market>.json — 그 시장 첫 start 때 rule_constants 를 한 번 적는 사전 등록 파일."""
    return h1_path(root, f"prereg_{_mkey(market)}.json")


def read_prereg(market, root=None):
    """사전 등록 파일(없으면 None). 깨졌거나 모양이 다르면 H1Refused(3)(규칙을 확인할 수 없음)."""
    mk = _mkey(market)
    p = prereg_path(mk, root)
    if not p.exists():
        return None
    try:
        d = _parse_file(p, p.name)
    except H1LogicError as e:
        raise H1Refused(EXIT_GATE, f"사전 등록 파일 {p.name} 을 읽지 못함: {e} → 사람이 확인")
    if not isinstance(d, dict) or d.get("market") != mk or not isinstance(d.get("rules"), dict) \
            or not isinstance(d.get("amendments"), list) or not all(isinstance(a, dict) for a in d["amendments"]):
        raise H1Refused(EXIT_GATE, f"사전 등록 파일 {p.name} 모양이 달라요 → 사람이 확인")
    return d


def prereg_rules(pre) -> dict:
    """사전 등록 효력 규칙 = 처음 적은 rules + amend-rules 로 더한 세율 줄(마지막 추가 기록의 new_table)."""
    rules = dict(pre["rules"])
    for a in pre["amendments"]:
        if isinstance(a.get("new_table"), list):
            rules[TAX_KEY] = a["new_table"]
    return rules


def prereg_problems(pre, rules) -> list:
    """rules(창의 meta.rules)가 사전 등록과 맞는가: 세율 표 말고는 처음 값과 같고, 세율 표는 처음 표로 시작해 효력 표
    (처음 표 + 추가 기록 줄)의 앞부분이어야 한다. 돌려줌: 다른 칸 이름 목록(맞으면 빈 목록)."""
    base, eff, r = _norm(pre["rules"]), _norm(prereg_rules(pre)), _norm(rules if isinstance(rules, dict) else {})
    bad = sorted(k for k in set(base) | set(r) if k != TAX_KEY and base.get(k) != r.get(k))
    t, b0, e0 = r.get(TAX_KEY), base.get(TAX_KEY), eff.get(TAX_KEY)
    if not (isinstance(t, list) and isinstance(b0, list) and isinstance(e0, list)
            and t[:len(b0)] == b0 and e0[:len(t)] == t):
        bad.append(TAX_KEY)
    return bad


def _rules_diff(a, b) -> list:
    a, b = _norm(a), _norm(b)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def _prereg_or_refuse(mk, root):
    pre = read_prereg(mk, root)
    if pre is None:
        raise H1Refused(EXIT_GATE, f"사전 등록 파일({prereg_path(mk, root).name})이 없어요 — 첫 start 때 적는 파일이라 "
                                   "시작한 시장에는 있어야 해요 → 지워졌는지 사람이 확인(규칙을 확인할 수 없어 멈춤)")
    return pre


def _check_code_vs_prereg(mk, root, what):
    """지금 코드 상수(rule_constants)가 사전 등록 효력 규칙과 똑같아야 한다(start·restart, 단계 4 F-2). 아니면 3."""
    pre = _prereg_or_refuse(mk, root)
    diff = _rules_diff(rule_constants(mk), prereg_rules(pre))
    if diff:
        raise H1Refused(EXIT_GATE, f"{what}: 지금 코드의 사전 등록 숫자가 첫 start 때 적은 값(prereg_{mk}.json)과 달라요 "
                                   f"{diff} → 사전 등록 숫자는 바꿀 수 없어요(세율 줄 추가는 지금 창에서 amend-rules). "
                                   "코드 상수를 되돌리세요")
    return pre


def _write_prereg(mk, root, at, run_id):
    """첫 start: 사전 등록 파일을 한 번 쓴다(임시 파일 → fsync → 이름 바꾸기 → 폴더 fsync). 이미 있으면 쓰지 않는다."""
    p = prereg_path(mk, root)
    if p.exists():
        return False
    _write_atomic(p, _dump({"v": 1, "market": mk, "rules": rule_constants(mk), "design_doc_sha256": _design_sha(),
                            "written_at": at, "first_start_run_id": run_id, "amendments": []}))
    return True


# ============================ 시세 받기 (§3.3 fetch, F4 대기 자산 — h1_data.py, 단계 4 F-9) ============================
# 받기 층(fetch·load_idle·fetched_from_raw·Fetched·DataSource)은 h1_data.py 에 있다(⑥-i 로 고칠 수 있는 유일한 코드 파일).
# 위 import 로 h1.fetch 처럼 그대로 부를 수 있다. 시계(_local_now)는 늦은 봉 판단에 쓰이므로 여기(h1.py)에 둔다.

def live_source(market) -> DataSource:
    """운영 자료: h1_data 의 대기 자산·fetch, 미국 screener.universe(40) / 국내 KR_UNIVERSE, 이 컴퓨터 시계(_local_now)."""
    return h1_data.live_source(_mkey(market), N_UNIVERSE, _local_now)


# ============================ 잠금 (§2.3 준비 1) ============================

def lock_name(market=None) -> str:
    """잠금 파일 이름(단계 4 F-7): 시장 명령 = h1-<market>.lock, 시장이 없는 것(replay_pass.json·봉인 쓰기, 금리 받기) =
    h1-global.lock. 두 시장은 서로 기다리지 않는다(공용 일지는 한 줄 = O_APPEND 한 번 쓰기, 판정 기록은 시장별 파일)."""
    return "h1-global.lock" if market is None else f"h1-{_mkey(market)}.lock"


class h1_lock:
    """state/h1/h1-<market>.lock (market 없으면 h1-global.lock) 잠금(fcntl.flock, 단계 4 F-7). 못 잡으면 LOCK_POLL_S 마다
    다시 시도하고, 최대 LOCK_WAIT_S(30분) 뒤 H1Refused(5). 기다림·시계는 모듈 변수 _lock_sleep·_lock_clock (시험에서 바꿔 끼움).
    잠그는 순서는 늘 시장 잠금 → 전역 잠금(거꾸로 잡는 곳 없음 → 서로 기다려 멈추지 않음)."""

    def __init__(self, root=None, wait_s=None, market=None):
        self.root = _root(root)
        self.wait_s = LOCK_WAIT_S if wait_s is None else wait_s
        self.name = lock_name(market)
        self.fd = None

    def __enter__(self):
        _mkdirs(self.root)
        path = h1_path(self.root, self.name)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            deadline = _lock_clock() + self.wait_s
            told = False
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                        raise
                if not told:
                    _say(f"  다른 H1 명령이 잠금 중이라 기다려요(최대 {self.wait_s / 60:.0f}분) …")
                    told = True
                left = deadline - _lock_clock()
                if left <= 0:
                    raise H1Refused(EXIT_LOCK, f"다른 H1 명령이 잠금({path.name})을 {self.wait_s / 60:.0f}분 넘게 쥐고 있어요 "
                                               "→ 잠시 뒤 다시. 계속되면 멈춘 python 이 있는지 확인")
                _lock_sleep(min(LOCK_POLL_S, left))
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(self.fd)
        self.fd = None
        return False


def _note_lock_timeout(root, command, market, err):
    """잠금을 못 잡은 명령도 runs.jsonl 에 한 줄 남긴다(한 번의 write 라 다른 명령의 줄과 섞이지 않음)."""
    try:
        _append_log(root, "runs.jsonl", {"event": "lock_timeout", "command": command, "market": market,
                                         "at": _iso(_local_now()), "exit_code": EXIT_LOCK, "message": str(err),
                                         "start_date": _peek_start_date(market, root)})
    except Exception:
        pass
    _say(f"[H1 {market}] {command}: 종료 코드 {EXIT_LOCK} — {err}")


def _peek_start_date(market, root) -> str:
    """일지에 적을 판정 창 S(2b-2 검토 C-3). 장부를 엄격하게 읽기 전에도 채우려고 meta.json → 장부 하나를
    너그럽게(검증 없이) 읽는다. 못 읽으면 "unknown" (status·보고서는 그 시장의 지금 창으로 센다)."""
    try:
        mk = _mkey(market)
        for rel in (META_REL, LEDGER_RELS[0]):
            try:
                d = json.loads(_rel_path(root, (mk,), rel).read_text(encoding="utf-8"))
            except Exception:
                continue
            sd = d.get("start_date") if isinstance(d, dict) else None
            if isinstance(sd, str) and sd:
                return sd
    except Exception:
        pass
    return "unknown"


# ============================ 실행 일지 runs.jsonl · errors.jsonl (§3.7) ============================

def _pdict(p):
    return asdict(p) if hasattr(p, "__dataclass_fields__") else dict(p)


class _RunLog:
    """명령 한 번 = runs.jsonl 의 시작 줄 + 끝 줄 (명령·시장·시각·run_id·code_hash·env·mode·처리한 봉·종료 코드·메시지,
    관문 거절·자료 멈춤·환경 문제·판정 기록 잘림·백업 되살림 포함). start_date 는 시작 줄 전에 너그럽게 채운다(C-3).
    일지를 쓰다 실패해도(디스크 가득 등) 명령 결과는 바뀌지 않는다(화면에만 알림)."""

    def __init__(self, command, market, root, now_fn=None, args=None):
        self.command = command
        self.market = _mkey(market)
        self.root = _root(root)
        self.now_fn = now_fn or _local_now
        t = self.now()
        self.run_id = f"{t.strftime('%Y%m%dT%H%M%S')}-{self.market}-{command}-{uuid.uuid4().hex[:8]}"
        self.args = dict(args or {})
        self.bars, self.late_bars, self.commits = [], [], []
        self.problems, self.notes = [], []
        self.extra = {}
        self.start_date = None
        self.code_hash = self.env = self.mode = None
        self.exit_code = None

    def now(self):
        try:
            return _aware(self.now_fn())
        except Exception:
            return _local_now()

    def _write(self, rec):
        try:
            _append_log(self.root, "runs.jsonl", rec)
        except OSError as e:
            _say(f"  ※ runs.jsonl 에 쓰지 못함({type(e).__name__}: {e})")

    def begin(self, code_hash=None, env=None, mode=None):
        self.code_hash, self.env, self.mode = code_hash, env, mode
        if self.start_date is None:
            self.start_date = _peek_start_date(self.market, self.root)
        self._write({"event": "start", "run_id": self.run_id, "command": self.command, "market": self.market,
                     "at": _iso(self.now()), "start_date": self.start_date, "code_hash": code_hash, "env": env,
                     "mode": mode, "args": self.args})

    def note(self, msg):
        self.notes.append(msg)
        _say(f"  ※ {msg}")

    def end_record(self, exit_code, message) -> dict:
        """끝 줄 모양(쓰지는 않음). end 가 쓰고, 실행 끝 요약이 '곧 쓸 끝 줄'로 미리 센다."""
        return {
            "event": "end", "run_id": self.run_id, "command": self.command, "market": self.market,
            "at": _iso(self.now()), "exit_code": exit_code, "meaning": EXIT_TEXT.get(exit_code), "message": message,
            "start_date": self.start_date, "code_hash": self.code_hash, "env": self.env, "mode": self.mode,
            "bars": list(self.bars), "late_bars": list(self.late_bars), "commits": list(self.commits),
            "problems": [_pdict(p) for p in self.problems], "notes": list(self.notes), **self.extra}

    def end(self, exit_code, message, quiet=False):
        if self.exit_code is not None:
            return
        self.exit_code = exit_code
        self._write(self.end_record(exit_code, message))
        if not quiet:
            _say(f"[H1 {self.market}] {self.command} 끝: 종료 코드 {exit_code} — {EXIT_TEXT.get(exit_code, '?')}"
                 + (f" ({message})" if message and exit_code != EXIT_OK else ""))


def _log_errors(log, date, problems, fingerprint, exc=None, tb=None):
    """errors.jsonl: L 오류 한 건(시장·봉·문제 목록·저장하려던 장부 6개의 내용 지문(참고용)·run_id·창 S)."""
    try:
        _append_log(log.root, "errors.jsonl", {
            "at": _iso(log.now()), "run_id": log.run_id, "command": log.command, "market": log.market,
            "start_date": log.start_date, "date": date,
            "problems": [_pdict(p) for p in problems],
            "fingerprint": fingerprint,
            "fingerprint_note": "참고용: 저장하려던 장부 6개의 내용 지문(ledger_fingerprint, 설계 §2.2 ④-나). "
                                "None 이면 지문 없음",
            "exception": None if exc is None else {"type": type(exc).__name__, "message": str(exc),
                                                   "code": getattr(exc, "code", None)},
            "traceback": tb, "code_hash": log.code_hash, "env": log.env})
    except OSError as e:
        _say(f"  ※ errors.jsonl 에 쓰지 못함({type(e).__name__}: {e}) — 위 화면 기록을 보관하세요")


class _LFound(Exception):
    """봉 처리·장부 읽기에서 찾은 L 오류(Problem 목록) → errors.jsonl·종료 코드 2."""

    def __init__(self, date, problems, fingerprint):
        super().__init__("; ".join(f"{p.code} {p.detail}" for p in h1_check.errors(problems))[:500])
        self.date = date
        self.problems = list(problems)
        self.fingerprint = fingerprint


def _on_error(log, e) -> int:
    """명령 안에서 난 예외 → 종료 코드 (설계 §3.9 + 2b-2 검토 C-1·C-15) + 일지. L 만 errors.jsonl 에도 남긴다.
    환경 문제(OSError: 디스크 가득·권한·입출력, MemoryError)는 L 이 아니다 → 종료 코드 4, runs.jsonl 에 kind "ENV".
    커밋 도중이었어도 다음 실행이 HEAD·백업으로 되살린다. "예상 밖 예외 → 2" 는 그 밖의 예외(코드 버그)에만 쓴다."""
    mk = log.market
    if isinstance(e, H1Refused):
        code, msg = e.code, str(e)
        _say(f"  거절: {msg}")
    elif isinstance(e, H1DataProblem):
        code = EXIT_D7 if e.kind == "D7" else EXIT_DATA
        msg = str(e)
        log.problems.append(h1_check.Problem("D", e.kind, mk, None, None, getattr(e, "date", None), msg))
        _say(f"  자료 문제 {msg} → 그 봉은 저장 안 함(재시작 아님). 다음 실행이 다시 해요")
    elif isinstance(e, H1PreconditionError):
        code, msg = EXIT_DATA, f"사전 조건 어긋남(달력·자료 문제로 봄): {e}"
        log.problems.append(h1_check.Problem("D", "PRE", mk, None, None, getattr(e, "date", None), str(e)))
        _say(f"  {msg} → 저장 안 함, 다음 실행이 다시")
    elif isinstance(e, _LFound):
        code, msg = EXIT_LOGIC, f"장부 논리 오류: {e}"
        _log_errors(log, e.date, e.problems, e.fingerprint)
        _say(f"  장부 논리 오류(L) — 그 봉 {e.date or ''} 은 저장 안 함. 문제:")
        for p in h1_check.errors(e.problems)[:20]:
            _say(f"    {p.code} {p.arm or ''}/{p.trainer or ''} {p.date or ''}: {p.detail}")
    elif isinstance(e, H1LogicError):
        code = EXIT_LOGIC
        msg = f"장부 논리 오류 {e.code or 'L?'}: {e}"
        probs = list(getattr(e, "problems", None) or [])
        probs.append(h1_check.Problem("L", e.code or "L24", mk, None, None, getattr(e, "date", None), str(e)))
        _log_errors(log, getattr(e, "date", None), probs, getattr(e, "fingerprint", None), exc=e)
        _say(f"  {msg} → 저장 안 함. 고치고 재시작 대상(설계 §2.2 ⑤)")
    elif isinstance(e, (OSError, MemoryError)):
        code = EXIT_DATA
        msg = f"환경 문제(ENV) {type(e).__name__}: {e}"
        log.problems.append(h1_check.Problem("D", "ENV", mk, None, None, getattr(e, "date", None), msg))
        _say(f"  {msg} → 저장 안 함(장부 논리 오류 아님, 재시작 아님). 디스크 공간·권한을 확인하면 다음 실행이 "
             "이어서(커밋 도중이었으면 백업으로 되살림)")
    else:
        code = EXIT_LOGIC
        msg = f"예상 밖 오류(코드 버그) {type(e).__name__}: {e}"
        _log_errors(log, getattr(e, "date", None), [h1_check.Problem("L", "L?", mk, None, None, None, msg)], None,
                    exc=e, tb=traceback.format_exc())
        _say(f"  {msg} → 저장 안 함(종료 코드 2, 지문 없음). 로그와 errors.jsonl 을 확인하세요")
        try:
            traceback.print_exc()
        except OSError:
            pass
    log.end(code, msg)
    return code


def _on_interrupt(log) -> int:
    """Ctrl-C(KeyboardInterrupt) → 종료 코드 130. L 이 아니다(errors.jsonl 에 안 씀)."""
    log.end(EXIT_INTERRUPT, "사람이 멈춤(Ctrl-C) — 저장된 봉까지는 안전, 다음 실행이 이어서")
    return EXIT_INTERRUPT


def _count_starts(mk, root) -> int:
    return sum(1 for r in _read_log(root, "runs.jsonl")
               if r.get("event") == "end" and r.get("command") == "start" and r.get("market") == mk
               and r.get("exit_code") == EXIT_OK)


def _restart_records(mk, root) -> list:
    return [r for r in _read_log(root, "restarts.jsonl") if r.get("market") == mk]


def _restart_id(r):
    return r.get("restart_id") or r.get("run_id") or json.dumps(r, sort_keys=True, ensure_ascii=False)


def restart_info(market, root=None, meta=None, lines=None) -> dict:
    """재시작 수(설계 §10.2e R-7, 보수적으로) = 셋 중 가장 큰 값: meta.restart_no(HEAD 로 보호, 시장 폴더가 있을 때),
    restarts.jsonl 의 restart_id 중 'done' 이거나 보관 폴더가 실제로 있는 것, archive/<시장>-* 폴더 수. 셋이 다르면 mismatch.
    지금 창을 옮기려던 'moving' 줄(보관 폴더 없음, 시장 폴더 그대로)은 재시작으로 세지 않고 pending 으로 따로.
    보고서(R-7)·status 머리·restart 상한 확인·start 의 meta.restart_no 가 모두 이 함수 하나를 쓴다(단계 3 검토 반영).
    lines 를 주면 restarts.jsonl 대신 그것을(보고서는 깨진 줄 수를 세며 읽은 목록을 넘긴다)."""
    mk = _mkey(market)
    root = _root(root)
    if lines is None:
        lines = _read_log(root, "restarts.jsonl")
    groups = {}
    for r in lines:
        if r.get("market") != mk:
            continue
        g = groups.setdefault(_restart_id(r), {"recs": []})
        g["recs"].append(r)
        for k in ("at", "reason", "old_start", "old_last", "restart_no", "archive"):
            if g.get(k) is None and r.get(k) is not None:
                g[k] = r.get(k)
    counted, pending = [], []
    for g in groups.values():
        done = any(r.get("status", "done") == "done" for r in g["recs"])
        try:
            arch = bool(g.get("archive")) and _archive_path(root, g).exists()
        except (H1Refused, ValueError):
            arch = False
        g["done"] = done
        (counted if done or arch else pending).append(g)
    adir = h1_path(root, "archive")
    n_arch = sum(1 for x in adir.iterdir() if x.is_dir() and x.name.startswith(f"{mk}-")) if adir.is_dir() else 0
    meta_n = (meta or {}).get("restart_no")
    meta_n = meta_n if isinstance(meta_n, int) and not isinstance(meta_n, bool) else 0
    sources = {"meta.restart_no": meta_n, "restarts.jsonl": len(counted), "archive 폴더": n_arch}
    return {"used": max(sources.values()), "sources": sources, "mismatch": len(set(sources.values())) > 1,
            "list": [{k: g.get(k) for k in ("at", "reason", "old_start", "old_last", "done")} for g in counted],
            "pending": [{k: g.get(k) for k in ("at", "reason", "old_start", "old_last")} for g in pending]}


def _meta_or_none(mk, root):
    """시장 폴더의 meta.json(엄격하게 읽힐 때만) — restart 상한 확인용. 못 읽으면 None(그 출처는 0 으로 셈)."""
    try:
        meta = _parse_file(_rel_path(root, (mk,), META_REL), "meta.json")
        return meta if isinstance(meta, dict) else None
    except Exception:
        return None


def _pending_restarts(mk, root) -> list:
    """의도 줄(status 'moving')만 있고 끝 줄('done')이 없는 재시작(폴더를 옮기다 꺼짐)."""
    recs = _restart_records(mk, root)
    done = {_restart_id(r) for r in recs if r.get("status", "done") == "done"}
    return [r for r in recs if r.get("status") == "moving" and _restart_id(r) not in done]


def _archive_path(root, rec) -> Path:
    rel = rec.get("archive")
    if not isinstance(rel, str) or not rel:
        raise H1Refused(EXIT_NO_LEDGER, "restarts.jsonl 의 보관 경로(archive)가 비었어요 → 사람이 확인")
    return h1_path(root, *rel.split("/"))


# ============================ 고정 종목군 (Q7, §3.7) ============================

def _universe_blob(mk, codes, at, env) -> bytes:
    return _dump({"market": mk, "codes": list(codes), "n": len(codes), "fetched_at": at,
                  "source": f"screener.universe({N_UNIVERSE})" if mk == "us" else "markets.KR_UNIVERSE",
                  "fdr_version": (env or {}).get("FinanceDataReader") if mk == "us" else None})


def _check_codes(mk, codes, what):
    if not isinstance(codes, list) or not codes or len(set(codes)) != len(codes) \
            or not all(isinstance(c, str) and markets.code_ok(mk, c) for c in codes):
        raise ValueError(f"{what} 종목 목록 모양이 이상해요(비었음·중복·다른 시장 코드)")
    return codes


def read_universe(market, root=None):
    """(목록, 파일 sha256) 또는 None(파일 없음). 깨졌거나 모양이 다르면 H1LogicError(L22)."""
    mk = _mkey(market)
    p = universe_path(mk, root)
    if not p.exists():
        return None
    blob = p.read_bytes()
    try:
        d = json_loads_strict(blob.decode("utf-8"))
        if not isinstance(d, dict) or d.get("market") != mk:
            raise ValueError("시장이 다름")
        codes = _check_codes(mk, d.get("codes"), "종목군 파일")
    except (UnicodeDecodeError, ValueError, H1LogicError) as e:
        raise H1LogicError(f"종목군 파일 {p.name} 이 깨졌거나 모양이 달라요: {e}", code="L22")
    return list(codes), _sha256_bytes(blob)


# ============================ 장부 읽기 (엄격) · 커밋 지점 (§2.5) ============================

@dataclass
class Loaded:
    """읽은 한 시장: 장부 6개(메모리 모양)·meta·HEAD. restored = 백업으로 되살렸으면 그 백업 run_id."""
    market: str
    head: dict
    meta: dict
    states: dict
    restored: str | None = None


def _check_head(head):
    if not isinstance(head, dict) or set(head) != set(HEAD_KEYS):
        _bad("HEAD.json 칸이 다름")
    try:
        _check_iso(head["last_date"], "HEAD.last_date")
    except ValueError as e:
        _bad(str(e))
    if not isinstance(head["files"], dict) or set(head["files"]) != set(LEDGER_RELS) \
            or not all(isinstance(v, str) for v in head["files"].values()):
        _bad("HEAD.json files 가 장부 6개와 다름")
    if not isinstance(head["meta_sha256"], str):
        _bad("HEAD.json meta_sha256 모양이 다름")
    dl = head["decision_log"]
    if not isinstance(dl, dict) or set(dl) != {"lines", "prefix_sha256"} or not isinstance(dl["lines"], int) \
            or isinstance(dl["lines"], bool) or dl["lines"] < 0 or not isinstance(dl["prefix_sha256"], str):
        _bad("HEAD.json decision_log 모양이 다름")
    rid = head["run_id"]
    if not isinstance(rid, str) or rid in ("", ".", "..") or any(ch in rid for ch in "/\\\0"):
        _bad("HEAD.json run_id 모양이 다름")
    if not isinstance(head["written_at"], str):
        _bad("HEAD.json written_at 모양이 다름")


def _check_meta(meta, mk):
    if not isinstance(meta, dict) or set(meta) != set(META_KEYS):
        _bad("meta.json 칸이 다름")
    if meta["market"] != mk:
        _bad(f"meta.json 시장 {meta['market']!r} ≠ {mk!r}")
    try:
        _check_iso(meta["start_date"], "meta.start_date")
    except ValueError as e:
        _bad(str(e))
    if not isinstance(meta["rules"], dict) or not isinstance(meta["universe_sha256"], str):
        _bad("meta.json rules·universe_sha256 모양이 다름")


def _mismatched(root, base_parts, head) -> list:
    """base(시장 폴더 또는 백업 폴더)의 장부 6개 + meta 중 HEAD 의 sha256 과 다른(또는 없는) 파일."""
    bad = []
    for rel in LEDGER_RELS + (META_REL,):
        want = head["meta_sha256"] if rel == META_REL else head["files"][rel]
        if _sha256_file(_rel_path(root, base_parts, rel)) != want:
            bad.append(rel)
    return bad


def _head_digest(head):
    return head["decision_log"]["lines"], head["decision_log"]["prefix_sha256"]


def _parse_ledgers(mk, blobs: dict) -> dict:
    states = {arm: {} for arm in ARMS}
    for arm in ARMS:
        for tn in TRAINERS:
            rel = f"{arm}/team_{tn}.json"
            try:
                d = json_loads_strict(blobs[rel].decode("utf-8"))
            except UnicodeDecodeError:
                raise H1LogicError(f"장부 {rel} 글자가 깨졌어요(UTF-8 아님)", code="L24")
            except H1LogicError as e:
                raise H1LogicError(f"장부 {rel}: {e}", code="L24")
            try:
                states[arm][tn] = ledger_from_json(d, mk, arm, tn)
            except H1LogicError as e:
                raise H1LogicError(f"장부 {rel}: {e}", code="L24")
    return states


def load_market(market, root=None, *, repair=True) -> Loaded:
    """한 시장을 엄격하게 읽는다(설계 §2.3 준비 4, §2.5 읽을 때).
    - 시장 폴더가 없으면 H1Refused(8): start 필요.
    - HEAD.json → 장부 6개 + meta.json 의 sha256 을 비교. 다르면(커밋 3과 4 사이에서 꺼짐) backup/<HEAD.run_id>/ 가
      HEAD 와 맞을 때 그것으로 되살린다(repair=True 일 때만, 잠금 아래에서). 그 밖은 H1LogicError(L24).
    - JSON 깨짐·NaN·형식(schema)·칸 모양이 다르면 H1LogicError(L24) — 새 지갑으로 덮지 않는다(할 일 3번).
    - 여섯 장부의 last_date 가 HEAD.last_date 와, start_date 가 meta.start_date 와 같아야 한다(아니면 L24)."""
    mk = _mkey(market)
    mdir = market_dir(mk, root)
    if not mdir.is_dir():
        raise H1Refused(EXIT_NO_LEDGER, f"{mk} 장부가 없어요({mdir}) → 먼저 python h1.py start --market {mk}")
    head = _parse_file(h1_path(root, mk, "HEAD.json"), "HEAD.json")
    _check_head(head)
    restored = None
    bad = _mismatched(root, (mk,), head)
    if bad:
        bparts = (mk, "backup", head["run_id"])
        bdir = h1_path(root, *bparts)
        if repair and bdir.is_dir() and not _mismatched(root, bparts, head):
            for rel in LEDGER_RELS + (META_REL,):
                _write_atomic(_rel_path(root, (mk,), rel), _rel_path(root, bparts, rel).read_bytes())
            restored = head["run_id"]
            _say(f"  장부 파일 {len(bad)}개가 HEAD 와 달라(앞 실행이 커밋 도중 꺼짐) backup/{head['run_id']}/ 로 되살렸어요",
                  flush=True)
        else:
            raise H1LogicError(f"장부 파일 손상: {bad} 가 HEAD.json 과 다르고 backup/{head['run_id']}/ 도 HEAD 와 맞지 않음",
                               code="L24")
    if repair:                                      # 커밋 도중 남은 .tmp 정리(잠금 아래)
        for tmp in list(mdir.glob("*.tmp")) + list(mdir.glob("A*/*.tmp")):
            try:
                tmp.unlink()
            except OSError:
                pass
    blobs = {rel: _rel_path(root, (mk,), rel).read_bytes() for rel in LEDGER_RELS}
    states = _parse_ledgers(mk, blobs)
    meta = _parse_file(_rel_path(root, (mk,), META_REL), "meta.json")
    _check_meta(meta, mk)
    for arm, tn, st in _flat(states):
        if st["last_date"] != head["last_date"]:
            _bad(f"{arm}/{tn} last_date {st['last_date']} ≠ HEAD.last_date {head['last_date']}")
        if st["start_date"] != meta["start_date"]:
            _bad(f"{arm}/{tn} start_date {st['start_date']} ≠ meta.start_date {meta['start_date']}")
    return Loaded(mk, head, meta, states, restored)


def _prune_backups(root, mk, keep: Path):
    bk = h1_path(root, mk, "backup")
    dirs = [d for d in bk.iterdir() if d.is_dir() and not d.name.endswith(".tmp")]
    dirs.sort(key=lambda d: (d.stat().st_mtime_ns, d.name))
    extra = len(dirs) - BACKUPS_KEEP
    for d in dirs:
        if extra <= 0:
            break
        if d.resolve() == keep.resolve():
            continue
        shutil.rmtree(d, ignore_errors=True)
        extra -= 1


def _backup(root, mk, head) -> bool:
    """커밋 2단계: 지금 장부 6개 + meta(= HEAD 상태)를 backup/<HEAD.run_id>/ 에 복사. 이미 있고 HEAD 와 맞으면 건너뜀.
    임시 폴더에 다 쓰고(파일·새 하위 폴더 fsync) 이름을 바꾸므로 반쯤 만든 백업은 남지 않는다. 최근 BACKUPS_KEEP(10)개."""
    rid = head["run_id"]
    bparts = (mk, "backup", rid)
    bdir = h1_path(root, *bparts)
    if bdir.is_dir() and not _mismatched(root, bparts, head):
        return False
    tparts = (mk, "backup", rid + ".tmp")
    tdir = h1_path(root, *tparts)
    if tdir.exists():
        shutil.rmtree(tdir)
    for rel in LEDGER_RELS + (META_REL,):
        _write_fsync(_rel_path(root, tparts, rel), _rel_path(root, (mk,), rel).read_bytes())
    for sub in sorted({rel.split("/")[0] for rel in LEDGER_RELS}):
        _fsync_dir(h1_path(root, *tparts, sub))          # 새 하위 폴더(A0·A1)의 파일 항목
    _fsync_dir(tdir)
    if bdir.exists():
        shutil.rmtree(bdir)
    os.replace(tdir, bdir)
    _fsync_dir(bdir.parent)
    _prune_backups(root, mk, bdir)
    return True


def _write_set(root, base_parts, blobs: dict) -> None:
    """커밋 3단계: 파일들을 .tmp 로 다 쓰고 fsync 한 뒤 하나씩 os.replace (그다음 폴더 fsync)."""
    pairs = []
    for rel, blob in blobs.items():
        p = _rel_path(root, base_parts, rel)
        tmp = p.with_name(p.name + ".tmp")
        _write_fsync(tmp, blob)
        pairs.append((tmp, p))
    for tmp, p in pairs:
        os.replace(tmp, p)
    for d in sorted({str(p.parent) for _, p in pairs}):
        _fsync_dir(d)


def _ledger_blobs(states, mk) -> dict:
    return {f"{arm}/team_{tn}.json": _dump(ledger_to_json(states[arm][tn], mk)) for arm in ARMS for tn in TRAINERS}


def _new_head(states, blobs, meta_blob, decisions, run_id, written_at) -> dict:
    lasts = {st["last_date"] for _, _, st in _flat(states)}
    if len(lasts) != 1:
        raise H1LogicError(f"여섯 장부의 last_date 가 다름 {sorted(map(str, lasts))}", code="L16")
    n, sha = decisions.prefix_digest()
    return {"last_date": lasts.pop(), "files": {rel: _sha256_bytes(b) for rel, b in blobs.items()},
            "meta_sha256": _sha256_bytes(meta_blob), "decision_log": {"lines": n, "prefix_sha256": sha},
            "run_id": run_id, "written_at": written_at}


def commit(root, market, states, meta, decisions, run_id, written_at, head_old) -> tuple:
    """커밋 순서(설계 §2.5): 1 판정 기록은 이미 디스크에(엔진이 묻는 순간 append) → 2 backup/<옛 HEAD.run_id>/ →
    3 장부 6개(+ 바뀐 meta) .tmp → fsync → os.replace → 4 HEAD.json(.tmp → fsync → replace). 4 에서 그 봉이 저장된다.
    돌려줌: (새 HEAD, 장부 6개 파일 글자)."""
    mk = _mkey(market)
    if head_old is not None:
        _backup(root, mk, head_old)
    blobs = _ledger_blobs(states, mk)
    meta_blob = _dump(meta)
    files = dict(blobs)
    if _sha256_file(_rel_path(root, (mk,), META_REL)) != _sha256_bytes(meta_blob):
        files[META_REL] = meta_blob
    _write_set(root, (mk,), files)
    head = _new_head(states, blobs, meta_blob, decisions, run_id, written_at)
    _write_atomic(h1_path(root, mk, "HEAD.json"), _dump(head))
    return head, blobs


# ============================ 자료 점검 D1·D4·D5·D6·D7 (§4 D) ============================

_D45_HINT = ("제공처가 고치면 다음 실행이 이어서 해요. 제공처가 고치지 않으면 1차 출처(거래소 휴장일·지수 발표)를 "
             "확인한 뒤 ⑦-3 재시작 대상(2b-2 검토 C-12)")


def _settle_time(mk, day: str) -> datetime:
    """봉 day 의 대기 자산 확정 시각(국내 KS200 22:30 KST, 미국 SPY 16:15 ET)."""
    m = markets.MARKETS[mk]
    hh, mm = (int(x) for x in (m.bench_cutoff or m.close_cutoff).split(":"))
    d = _date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo(m.tz))


def calendar_check(market, cal_all, states, fetched, universe, now, prev_line=None) -> tuple:
    """준비 6 달력 점검. cal_all = 대기 자산 확정 시세 날짜 전부(오름차순). states None 이면 start(S = 마지막 봉).
    돌려줌: (이번 달력 = S 전 거래일 ~ 마지막 봉, W 경고 목록, D7 Problem 또는 None). D4·D5 는 H1DataProblem.
    - D4 달력 줄어듦: 이미 처리한 날짜(하루 기록 날짜와 그 prev_cal_date, calendar.jsonl 마지막 정상 줄 중 last_date 이하)가
      새 달력에 없음. 또 이미 처리한 구간 S 전 거래일 ~ last_date 에 새 날짜가 끼어듦(설계 D4 를 넓혀 해석 — 보고서 참고)
    - D5 달력 구멍: (last_date, 마지막 봉] 에 달력에 없는 날인데 받은 종목군의 절반 이상이 거래함
    - D7 기준 지수 늦음: 확인용 대형주의 최신 확정 봉 > 달력 마지막 봉, 그리고 지금이 그 봉의 기준 지수 확정 시각 뒤
    - W5 확인용 대형주 시세를 못 받음(D7 판단 불가)"""
    mk = _mkey(market)
    warns = []
    if states is None:
        if len(cal_all) < 2:
            raise H1DataProblem("D1", f"대기 자산 {idle_code(mk)} 확정 봉이 2개보다 적어요(S 전 거래일 없음)")
        cal = list(cal_all[-2:])
        last = cal[0]
    else:
        st0 = states["A0"][TRAINERS[0]]
        days, last = st0["days"], st0["last_date"]
        prev_s = days[0]["prev_cal_date"]
        ref = {prev_s} | {r["date"] for r in days} | {r["prev_cal_date"] for r in days if r["prev_cal_date"]}
        if prev_line:
            ref |= {d for d in prev_line.get("dates", []) if isinstance(d, str) and d <= last}
        have = set(cal_all)
        missing = sorted(d for d in ref if d not in have)
        if missing:
            raise H1DataProblem("D4", f"달력 줄어듦: 이미 처리한 날짜 {missing[:5]}{' …' if len(missing) > 5 else ''} 가 "
                                      f"새로 받은 {idle_code(mk)} 시세에 없음(FDR 연도 파일 누락 등). {_D45_HINT}")
        cal = list(cal_all[cal_all.index(prev_s):])
        done = [prev_s] + [r["date"] for r in days]
        head_part = [d for d in cal if d <= last]
        if head_part != done:
            extra = sorted(set(head_part) - set(done))
            raise H1DataProblem("D4", f"달력 바뀜: 이미 처리한 구간 {prev_s}~{last} 에 새 날짜 {extra[:5]} 가 생김. "
                                      f"{_D45_HINT}")
    # D5
    have = set(cal)
    lo, hi = last, cal[-1]
    uni = [c for c in universe if fetched.get(c) is not None]
    if uni and hi > lo:
        counts = Counter()
        for c in uni:
            for d in _dates_of(fetched[c].df):
                if lo < d <= hi and d not in have:
                    counts[d] += 1
        holes = sorted(d for d, n in counts.items() if n >= CAL_HOLE_RATIO * len(uni))
        if holes:
            raise H1DataProblem("D5", f"달력 구멍: {holes[:5]} 에 종목군 {len(uni)}개 중 절반 이상이 거래했는데 "
                                      f"{idle_code(mk)} 시세에 그 날이 없음. {_D45_HINT}")
    # D7
    d7 = None
    probes = CAL_PROBE[mk]
    got = {c: fetched.get(c) for c in probes}
    for c in probes:
        if got[c] is None:
            warns.append(h1_check.Problem("W", "W5", mk, None, None, None,
                                          f"확인용 대형주 {c} 시세를 못 받음 → 기준 지수 늦음(D7) 판단 불가"))
    lasts = [_dates_of(f.df)[-1] for f in got.values() if f is not None]
    if lasts:
        latest = max(lasts)
        if latest > cal[-1] and _aware(now) >= _settle_time(mk, latest):
            d7 = h1_check.Problem("D", "D7", mk, None, None, latest,
                                  f"기준 지수 늦음: 확인용 대형주에 {latest} 확정 봉이 있는데 {idle_code(mk)} 마지막 봉은 "
                                  f"{cal[-1]} (확정 시각 {_settle_time(mk, latest).isoformat(timespec='minutes')} 지남)")
    return cal, warns, d7


def _open_on(df, d):
    if df is None:
        return None
    row = _row_at(df, d)
    if row is None:
        return None
    try:
        v = float(row["Open"])
    except (KeyError, TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _close_on(df, d):
    if df is None:
        return None
    row = _row_at(df, d)
    if row is None:
        return None
    try:
        v = float(row["Close"])
    except (KeyError, TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _last_close_le(df, d):
    """그 날짜 이하 마지막 확정 종가(정지일이면 정지 전 마지막 종가)."""
    if df is None:
        return None
    cut = cut_frame(df, d)
    if cut is None or len(cut) == 0:
        return None
    v = float(cut["Close"].iloc[-1])
    return v if math.isfinite(v) else None


def _adjusted(corp_actions, code, d, field, value):
    """장부에 적힌 값 → 기업 행위를 반영한 '지금 시세에서 기대하는 값'(설계 D6).
    corp_actions 를 적힌 순서대로:
    - 분할: 그 기록 날짜 ≤ 분할을 장부에 적용한 때(applied_after = 그때 last_date)이면 ÷ r.
      적용 뒤에 처리한 봉은(효력일 전 날짜라도) 이미 고쳐진 새 시세로 기록했으므로 나누지 않는다.
      효력일(date)은 늘 applied_after 보다 뒤라(명령이 확인) 효력일 전 기록 = 적용 전 기록이다(2b-2 검토 C-2·C-9).
    - 정정 확정: 같은 날짜·칸이면 적어 둔 새 값."""
    for ca in corp_actions:
        if ca.get("code") != code:
            continue
        if ca.get("kind") == "split" and d <= ca.get("applied_after", ""):
            value = value / ca["r"]
        elif ca.get("kind") == "correction":
            for it in ca.get("items") or []:
                if it.get("date") == d and it.get("field") == field:
                    value = it.get("new")
    return value


def retro_compare(market, states, dfs: dict, idle_df, codes=None) -> list:
    """소급 수정 비교 목록(설계 §4 D6). 비교 하나 = {code, date, field, old(장부에서 기대), new(새 시세), where, same}.
    - 보유 종목(상장폐지 등록 제외): 지금 보유의 매수 체결가(fills.price) vs 새 시세의 그 날짜 Open(field "open"),
      최근 RETRO_DAYS(5)일 하루 기록 marks vs 새 시세의 그 날짜 이하 마지막 확정 종가(field "close")
    - 대기 자산: 최근 5일 하루 기록 idle_open·idle_close vs 새 시세의 그 날짜 Open·Close(field "open"·"close")
    - 비교 전에 기업 행위(분할·정정 확정)를 반영한다. codes 를 주면 그 종목만."""
    mk = _mkey(market)
    idle = idle_code(mk)
    regs = delist_registrations(states)
    seen = {}

    def add(code, d, field, old, new, where):
        key = (code, d, field)
        if key in seen:
            return
        same = (old is not None and new is not None and _isnum(old)
                and abs(old - new) <= RETRO_TOL * max(abs(old), abs(new)))
        seen[key] = {"code": code, "date": d, "field": field, "old": old, "new": new, "where": where, "same": same}

    for arm, tn, st in _flat(states):
        cas = st["corp_actions"]
        for code in st["positions"]:
            if code in regs or code == idle or (codes is not None and code not in codes):
                continue
            df = dfs.get(code)
            buys = [f for f in st["fills"] if f["code"] == code and f["kind"] == "stock" and f["side"] == "buy"]
            if buys:
                f = buys[-1]
                add(code, f["date"], "open", _adjusted(cas, code, f["date"], "open", f["price"]),
                    _open_on(df, f["date"]), f"{arm}/{tn} 매수 체결가")
            for row in st["days"][-RETRO_DAYS:]:
                if code in row["marks"]:
                    add(code, row["date"], "close", _adjusted(cas, code, row["date"], "close", row["marks"][code]),
                        _last_close_le(df, row["date"]), f"{arm}/{tn} 평가 종가(marks)")
    if codes is None or idle in codes:
        st0 = states["A0"][TRAINERS[0]]
        cas = st0["corp_actions"]
        for row in st0["days"][-RETRO_DAYS:]:
            d = row["date"]
            add(idle, d, "open", _adjusted(cas, idle, d, "open", row["idle_open"]), _open_on(idle_df, d), "대기 자산 시가")
            add(idle, d, "close", _adjusted(cas, idle, d, "close", row["idle_close"]), _close_on(idle_df, d),
                "대기 자산 종가")
    return sorted(seen.values(), key=lambda c: (c["code"], c["date"], c["field"]))


def split_ratio(comps):
    """한 종목의 비교 목록이 '모든 칸이 같은 비율로 다름'(분할·병합 모양)이면 그 비율 r(= 장부 값 ÷ 새 값), 아니면 None.
    비교가 2개 미만이면 판단하지 않는다(None)."""
    if len(comps) < 2 or any(c["same"] for c in comps):
        return None
    if not all(_isnum(c["old"]) and _isnum(c["new"]) and c["new"] and c["old"] for c in comps):
        return None
    ratios = [c["old"] / c["new"] for c in comps]
    lo, hi = min(ratios), max(ratios)
    if lo > 0 and (hi - lo) <= RETRO_TOL * hi:
        return (lo + hi) / 2
    return None


def retro_problem(comps):
    """비교 목록 → D6 H1DataProblem 또는 None. 한 종목의 모든 비교가 같은 비율로 다르면 '분할 의심(비율 r)'."""
    bad = [c for c in comps if not c["same"]]
    if not bad:
        return None
    msgs = []
    for code in sorted({c["code"] for c in bad}):
        mine = [c for c in comps if c["code"] == code]
        diff = [c for c in mine if not c["same"]]
        r = split_ratio(mine)
        hint = (f" — 분할 의심(비율 r={r:.6g}): 1차 출처 확인 뒤 corp-action --split {r:.6g} --date <효력일>"
                if r is not None else " — 1차 출처 확인 뒤 기다림(⑦-1) 또는 corp-action --accept-correction(⑦-5)")
        c0 = diff[0]
        msgs.append(f"{code} {len(diff)}곳 다름(예: {c0['date']} {c0['field']} 장부 {c0['old']!r} → 새 시세 {c0['new']!r},"
                    f" {c0['where']}){hint}")
    return H1DataProblem("D6", "소급 수정: " + "; ".join(msgs))


# ============================ 실행 공통 도움 ============================

def _good_px(v) -> bool:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0


def _idle_bar(mk, idle_df, t) -> IdleBar:
    """그날 대기 자산 봉. 행이 없으면 D1, 시가·종가가 NaN·inf·0 이하이면 D3(자료 미준비, 2b-2 검토 C-13)."""
    row = _row_at(idle_df, t)
    if row is None:
        raise H1DataProblem("D1", f"대기 자산 {idle_code(mk)} 에 {t} 행이 없어요")
    try:
        o, c = row["Open"], row["Close"]
    except KeyError as e:
        raise H1DataProblem("D1", f"대기 자산 {idle_code(mk)} {t} 시가·종가 칸이 없음 ({e})")
    if not (_good_px(o) and _good_px(c)):
        raise H1DataProblem("D3", f"대기 자산 {idle_code(mk)} {t} 시가·종가가 이상함(시가 {o!r}, 종가 {c!r}) — 자료 미준비")
    return IdleBar(idle_code(mk), t, float(o), float(c))


def _bar_data_check(mk, t, states, frames, halted):
    """봉 t 를 엔진에 넘기기 전 자료 확인(2b-2 검토 C-13): 보유·대기 종목(상장폐지 정리 대상·정지 제외)의 t 행 종가는
    유한한 양수여야 한다. 아니면 D3(자료 미준비 → 종료 코드 4, 다음 실행이 다시). 행이 없음·시가 없음은 엔진이 D2·D3 로 본다."""
    regs = delist_registrations(states)
    gone = {c for c, v in regs.items() if t > v["last_date"]}
    for _, _, st in _flat(states):
        for code in sorted((set(st["positions"]) | {o["code"] for o in st["pending"]}) - gone - set(halted)):
            df = frames.get(code)
            row = _row_at(df, t) if df is not None else None
            if row is None:
                continue
            close = row.get("Close") if hasattr(row, "get") else None
            if not _good_px(close):
                raise H1DataProblem("D3", f"보유·대기 종목 {code} 의 {t} 종가가 이상함({close!r}) — 자료 미준비")


def _bench(mk, source, now):
    """준비 5: 대기 자산 확정 시세. 못 받거나(None·빈 자료·예외) → H1DataProblem D1."""
    try:
        df = source.benchmark(now)
    except Exception as e:
        _say(f"    (대기 자산 {idle_code(mk)} 시세 받기 실패: {type(e).__name__}: {e})")
        df = None
    if df is None or len(df) == 0:
        raise H1DataProblem("D1", f"대기 자산 {idle_code(mk)} 시세를 못 받음")
    return df


def _fetch_all(mk, source, now, universe, need, probes) -> dict:
    """준비 7: 종목군 + 보유·대기 종목 + 확인용 대형주를 한 번씩만 받는다. {code: Fetched 또는 None}."""
    out = {}
    for code in dict.fromkeys(list(universe) + sorted(need) + list(probes)):
        try:
            f = source.fetch(code, now)
        except Exception as e:
            _say(f"    ({code} 시세 받기 실패: {type(e).__name__}: {e})")
            f = None
        if f is not None and (getattr(f, "df", None) is None or len(f.df) == 0):
            f = None
        out[code] = f
    return out


def _halted_on(fetched, codes, t) -> frozenset:
    return frozenset(c for c in codes if fetched.get(c) is not None and t in fetched[c].halt_dates)


def _universe_check(mk, codes, fetched, need, skip, log):
    """준비 7(2b-2 검토 C-4): 고정 종목군(상장폐지 등록 종목 제외) 중 시세를 못 받은 종목이 절반(CAL_HOLE_RATIO)을
    넘으면 D2 — 받기 제한(429)·형식 변경 같은 대량 실패로 보고 그 봉을 처리하지 않는다(다음 실행이 다시).
    그보다 적으면 종목군에만 있는 종목은 W4 로 남기고 건너뛴다(skip = 상장폐지 등록 종목은 비율에서만 뺀다)."""
    base = [c for c in codes if c not in skip]
    failed = [c for c in base if fetched.get(c) is None]
    if base and len(failed) > CAL_HOLE_RATIO * len(base):
        raise H1DataProblem("D2", f"고정 종목군 {len(base)}개 중 {len(failed)}개 시세를 못 받음(절반 넘음: 받기 제한·형식 "
                                  f"변경 의심) — 빈 스캔으로 처리하지 않고 멈춤, 다음 실행이 다시")
    for c in codes:                              # 상장폐지 등록 종목도 W4 로는 남긴다(비율에서만 뺌)
        if fetched.get(c) is None and c not in need:
            log.problems.append(h1_check.Problem("W", "W4", mk, None, None, None, f"종목군 {c} 시세 못 받음 → 건너뜀"))


def _probe_note(mk, warns, log):
    """확인용 대형주를 못 받았으면(W5) D7 을 판단하지 못했다는 사실을 일지·화면에 분명히 남긴다(C-4)."""
    miss = [p for p in warns if p.code == "W5"]
    if not miss:
        log.extra["d7_checked"] = True
        return
    log.extra["d7_checked"] = len(miss) < len(CAL_PROBE[mk])
    log.note(f"확인용 대형주 {len(miss)}/{len(CAL_PROBE[mk])}개 시세를 못 받아 기준 지수 늦음(D7)을 "
             + ("판단하지 못했어요" if not log.extra["d7_checked"] else "남은 종목으로만 판단했어요"))


CLAUDE_CWD = "claude_cwd"


def _leader_ask(root, leader_mode):
    """llm 모드의 팀장 묻기 함수: analyst.analyze_logged 를 빈 전용 작업 폴더 state/h1/claude_cwd/ 에서 부른다(단계 4 F-8 —
    부르는 쪽 폴더·worktree 의 CLAUDE.md·설정이 팀장 입력에 섞이지 않게). 함수는 부를 때 analyst 에서 찾는다(시험의 가짜 팀장).
    replay 모드는 묻지 않으므로 None."""
    if leader_mode != "llm":
        return None
    cwd = h1_path(root, CLAUDE_CWD)
    _mkdirs(cwd)

    def ask(trainer, todo, **kw):
        return analyst.analyze_logged(trainer, todo, cwd=cwd, **kw)
    return ask


def _check_mode(leader_mode):
    if leader_mode not in ("llm", "replay"):
        raise ValueError(f"leader_mode 는 'llm'(운영) 또는 'replay'(재현) (받은 값 {leader_mode!r})")


def _cli_version_once(leader_mode):
    """`claude --version` 은 실행마다 한 번, llm 모드일 때만(재현은 부르지 않음)."""
    if leader_mode != "llm":
        return None
    try:
        return analyst.claude_cli_version()
    except Exception:
        return None


def _absorb(log, res):
    """봉 결과의 경고(W)·팀장 방식을 일지에 모은다(L 은 errors.jsonl 몫)."""
    log.problems += [p for p in res.problems if p.level == "W"]
    log.extra.setdefault("bar_modes", {})[res.date] = {"mode": res.mode, "late": res.late, "llm_calls": res.llm_calls,
                                                       "late_calls": res.late_calls}
    if res.late:
        log.late_bars.append(res.date)


def _print_bar(res):
    w = Counter(p.code for p in res.problems if p.level == "W")
    wtxt = ", ".join(f"{k} {v}" for k, v in sorted(w.items())) or "없음"
    _say(f"  봉 {res.date} ({'늦은 봉 · 팀장 폴백' if res.late else res.mode}) · 스크리너 {res.used}종목 · "
          f"팀장 LLM 호출 {res.llm_calls}번 · L {len(res.errors)} · 경고 {wtxt}")
    for line in res.lines:
        _say(f"    {line}")


def _calendar_line(cal_dates, processed, check, run_id, at, command, fetched_at=None):
    """calendar.jsonl 한 줄: 받은 시각, 달력(S 전 거래일 ~ 마지막 봉) 날짜 목록 전체·그 sha256, 처리한 날짜,
    check = "ok" | "D7"(달력은 정상, 기준 지수만 늦음) | "D4"·"D5"(이 줄의 달력은 기준으로 쓰지 않음) | "stopped"."""
    blob = json.dumps(list(cal_dates), separators=(",", ":"))
    return {"at": at, "fetched_at": fetched_at or at, "run_id": run_id, "command": command, "dates": list(cal_dates),
            "sha256": _sha256_bytes(blob.encode("utf-8")), "processed": list(processed), "check": check}


def _last_ok_calendar_line(root, mk):
    """calendar.jsonl 의 마지막 '정상'(check 가 ok·D7) 줄. D4·D5 로 멈춘 실행의 줄은 기준으로 쓰지 않는다."""
    lines = read_jsonl(h1_path(root, mk, "calendar.jsonl"))
    for rec in reversed(lines):
        if rec.get("check") in ("ok", "D7"):
            return rec
    return None


def _at_or_after(a, b) -> bool:
    """시각 글자 a ≥ b (못 읽으면 True — 보수적으로 지금 창에 넣음)."""
    try:
        return datetime.fromisoformat(a) >= datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return True


def _in_window(rec, S, created_at=None) -> bool:
    """일지 줄이 판정 창 S 의 것인가(2b-2 검토 C-3, 2c 검토 R-1).
    start_date 가 S 이거나 S 를 몰라 "unknown"(또는 옛 None)으로 적힌 줄 중, 그 창이 만들어진 뒤(meta.created_at 이후,
    created_at 을 모르면 늘)의 줄만 지금 창으로 센다. start_date == S 여도 창이 만들어지기 전 줄(S 를 정한 뒤 실패한 start,
    같은 S 로 다시 시작하기 전 옛 창의 줄)은 어느 창에도 넣지 않는다. 시각을 못 읽으면 보수적으로 지금 창에 넣는다.
    status·실행 끝 요약(window_counts)·보고서(h1_report)가 모두 이 함수를 쓴다."""
    sd = rec.get("start_date")
    if sd != S and sd not in (None, "unknown"):
        return False
    return created_at is None or _at_or_after(rec.get("at"), created_at)


def window_counts(market, root=None, *, loaded=None, decisions=None, exclude_run_ids=(), extra_runs=()) -> dict:
    """status·실행 끝 요약의 판정 창 숫자(L 오류·거짓 양성·자료 멈춤·관문 거절·늦은 봉·한 번에 따라잡은 봉·팀장 수).
    **보고서와 같은 함수**(h1_report.window_counts → _journal_counts, 보고서 --final 과 같은 범위)를 그대로 부른다
    (설계 §10.2e 'status 와 보고서', 단계 3). 그래서 errors.jsonl ∪ runs.jsonl 종료 코드 2 를 run_id 로 합쳐 세고,
    사전 등록 ④ false_positive 판정은 빼고 따로 돌려준다. loaded 를 안 주면 HEAD 로 엄격하게 읽는다(되살리기 없음).
    exclude_run_ids = runs.jsonl 에서 뺄 실행(status 자기 시작 줄), extra_runs = 아직 안 쓴 줄을 더해 셈(실행 끝 요약의 끝 줄).
    h1_report 는 여기서만 늦게 import 한다(모듈을 읽을 때는 h1 → h1_report 의존이 없음)."""
    import h1_report                              # 늦은 import: h1_report 가 h1 을 import 한다
    mk = _mkey(market)
    root = _root(root)
    if loaded is None:
        loaded = load_market(mk, root, repair=False)
    return h1_report.window_counts(mk, root, loaded, decisions=decisions, exclude_run_ids=exclude_run_ids,
                                   extra_runs=extra_runs)


def _print_summary(mk, root, states, decisions, meta, head=None, log=None, exit_code=None, message=""):
    """실행 끝 요약(설계 §3.3 요약 예). 숫자는 status·보고서와 같은 window_counts. 이 명령은 아직 끝 줄을 쓰기 전이므로
    곧 쓸 끝 줄(exit_code·message, log.end 와 같은 모양)을 미리 넣고 센다 — 그래서 종료 코드 7(D7)로 끝나는 실행의 요약도
    status 처럼 자료 멈춤에 D7 을 센다(단계 3 검토 T-6)."""
    try:
        loaded = Loaded(market=mk, head=head, meta=meta, states=states)
        extra = () if log is None or exit_code is None else (log.end_record(exit_code, message),)
        n = window_counts(mk, root, loaded=loaded, decisions=decisions, extra_runs=extra)
        for line in summary_lines(mk, states, errors=n["l_errors"], data_stops=n["data_stops"], counts=n):
            _say(line)
    except Exception as e:                       # 요약은 보조 출력 — 실패해도 결과는 그대로
        _say(f"  (요약 출력 실패: {type(e).__name__}: {e})")


# ============================ start (§2.5 새 시작) ============================

def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


_JOURNAL_EXTRA = ("run_id", "recovered", "recovered_by")


def _sync_journals(mk, root, states, meta, log) -> int:
    """일지 맞추기(2b-2 검토 C-7). 기업 행위·세율 줄 추가의 원본은 장부(corp_actions)·meta 다. 일지는 HEAD 뒤에 쓰므로
    그 사이에 꺼지면 빠질 수 있다 → 잠금 아래에서 명령이 시작할 때 장부에는 있는데 일지에는 없는 줄을 채운다.
    - 장부 corp_actions 의 줄마다 <시장>/corp_actions.jsonl 과 changes.jsonl("corp-action:<종류>")에 같은 내용이 있어야 함
    - changes.jsonl 의 amend-rules 'pending' 줄에 'done'·'abandoned' 가 없으면: meta.rules 세율 표가 그 줄의
      new_table 과 같으면 done(커밋은 됨), 아니면 abandoned(커밋 전에 꺼짐)
    채운 줄에는 recovered: true. 돌려줌: 채운 줄 수."""
    added = 0
    at = _iso(log.now())
    ca_path = h1_path(root, mk, "corp_actions.jsonl")
    strip = lambda r: {k: v for k, v in r.items() if k not in _JOURNAL_EXTRA}   # noqa: E731
    have_ca = {_canon(strip(r)) for r in read_jsonl(ca_path)}
    changes = _read_log(root, "changes.jsonl")
    have_ch = {_canon(r.get("entry")) for r in changes
               if r.get("market") == mk and str(r.get("kind", "")).startswith("corp-action:")}
    for ca in states["A0"][TRAINERS[0]]["corp_actions"]:
        key = _canon(ca)
        if key not in have_ca:
            _append_line(ca_path, {**ca, "run_id": None, "recovered": True, "recovered_by": log.run_id})
            have_ca.add(key)
            added += 1
        if key not in have_ch:
            _append_log(root, "changes.jsonl", {"at": ca.get("at"), "market": mk, "kind": f"corp-action:{ca.get('kind')}",
                                                "entry": ca, "run_id": None, "recovered": True,
                                                "recovered_by": log.run_id})
            have_ch.add(key)
            added += 1
    amend = [r for r in changes if r.get("market") == mk and r.get("kind") == "amend-rules"]
    closed = {r.get("run_id") for r in amend if r.get("status") in ("done", "abandoned")}
    for r in amend:
        if r.get("status") == "pending" and r.get("run_id") not in closed:
            ok = _norm((meta.get("rules") or {}).get("stock_sell_tax")) == _norm(r.get("new_table"))
            _append_log(root, "changes.jsonl", {**{k: v for k, v in r.items() if k not in ("status", "at")},
                                                "at": at, "status": "done" if ok else "abandoned", "recovered": True,
                                                "recovered_by": log.run_id})
            closed.add(r.get("run_id"))
            added += 1
    if added:
        log.extra["journal_recovered"] = added
        log.note(f"장부에는 있는데 일지(corp_actions.jsonl·changes.jsonl)에 없던 줄 {added}개를 채웠어요(앞 명령이 커밋 뒤 꺼짐)")
    return added


def start(market, root=None, source=None, leader_mode="llm", gate=True) -> int:
    """새 판정 창 시작(설계 §2.5): S = 대기 자산 확정 시세의 마지막 봉. S 는 입금만(종가 판단·다음 시가 주문).
    모든 파일(meta·장부 6개·HEAD·calendar)을 state/h1/<m>.starting/ 에 다 쓴 뒤 os.replace 로 <m>/ 로 바꾼다.
    거절: 시장 폴더가 이미 있음(8) / 성공한 start 흔적이 있는데 재시작 기록 없이 폴더가 없음(8) / D7(7) / 관문(3) /
    D1·D2·D5(4). 남은 <m>.starting/ 은 지우고 처음부터(재시작으로 세지 않음). 종료 코드를 돌려준다."""
    mk = _mkey(market)
    root = _root(root)
    _check_mode(leader_mode)
    source = source if source is not None else live_source(mk)
    try:
        with h1_lock(root, market=mk):
            return _start_locked(mk, root, source, leader_mode, gate)
    except H1Refused as e:
        if e.code != EXIT_LOCK:
            raise
        _note_lock_timeout(root, "start", mk, e)
        return EXIT_LOCK


def _finish_moved_restarts(mk, root, log):
    """start 가 시작할 때: 폴더는 이미 보관 폴더로 옮겨졌는데 끝 줄('done')이 없는 재시작이 있으면 끝 줄을 채운다(C-6).
    보관 폴더도 없으면 사람이 확인해야 하므로 거절(8)."""
    for rec in _pending_restarts(mk, root):
        dest = _archive_path(root, rec)
        if not dest.exists():
            raise H1Refused(EXIT_NO_LEDGER, f"끝나지 않은 재시작 기록(보관 {rec.get('archive')})이 있는데 보관 폴더가 없어요 "
                                            "→ 사람이 먼저 확인")
        _append_log(root, "restarts.jsonl", {"status": "done", "restart_id": _restart_id(rec), "market": mk,
                                             "at": _iso(log.now()), "archive": rec.get("archive"), "recovered": True,
                                             "recovered_by": log.run_id})
        log.note(f"끝나지 않았던 재시작 기록(보관 {rec.get('archive')})을 마저 적었어요")


def _start_locked(mk, root, source, leader_mode, gate) -> int:
    log = _RunLog("start", mk, root, source.now, {"leader_mode": leader_mode, "gate": gate})
    try:
        ch, _ = code_hash()
        env = env_info()
        log.begin(ch, env, leader_mode)
        _say(f"[H1 {mk}] start · {_iso(log.now())} · 실행 {log.run_id}")
        allowed = allowed_fingerprints(root, gate, ch, env)                        # 3 관문
        mdir = market_dir(mk, root)
        if mdir.exists():
            hint = (" (끝나지 않은 restart 기록이 있어요 → restart 를 다시 치면 마저 옮김)"
                    if _pending_restarts(mk, root) else "")
            raise H1Refused(EXIT_NO_LEDGER, f"{mk} 장부 폴더가 이미 있어요({mdir}). 새로 시작하려면 먼저 "
                                            f"python h1.py restart --market {mk} --confirm {mk} --reason …{hint}")
        _finish_moved_restarts(mk, root, log)
        n_restarts = restart_info(mk, root)["used"]                                 # 보고서 R-7 과 같은 규칙
        if _count_starts(mk, root) > n_restarts:
            raise H1Refused(EXIT_NO_LEDGER, "runs.jsonl 에 성공한 start 기록이 있는데 장부 폴더가 없고 그 뒤 재시작 기록도 "
                                            "없어요 → 실수로 지운 것인지 사람이 먼저 확인(설계 §2.5)")
        pre = read_prereg(mk, root)                                                 # 사전 등록 숫자(단계 4 F-2)
        if pre is None and (_count_starts(mk, root) or n_restarts):
            raise H1Refused(EXIT_NO_LEDGER, f"이 시장을 시작한 흔적(성공한 start·재시작)이 있는데 사전 등록 파일 "
                                            f"prereg_{mk}.json 이 없어요 → 지워졌는지 사람이 먼저 확인")
        if pre is not None:
            _check_code_vs_prereg(mk, root, "start")
            pmax = pre["rules"].get("max_restarts")
            if isinstance(pmax, int) and n_restarts > pmax:
                raise H1Refused(EXIT_NO_LEDGER, f"재시작 {n_restarts}번 — 사전 등록 상한 {pmax}번을 넘어 새 창을 열 수 없어요")
        sdir = h1_path(root, f"{mk}.starting")
        if sdir.exists():
            shutil.rmtree(sdir)
            _fsync_dir(root)
            log.note(f"끝나지 않은 start 폴더({sdir.name})를 지우고 처음부터 해요(재시작으로 세지 않음)")
        now = _aware(source.now())
        idle_df = _bench(mk, source, now)                                            # 5 대기 자산
        cal_all = _dates_of(idle_df)
        got = read_universe(mk, root)
        if got is not None:
            codes, u_sha = got
            u_blob = None
            _say(f"  종목군: 이미 있는 고정 목록 {len(codes)}종목(universe/{mk}.json, 재시작해도 그대로)")
        else:
            try:
                codes = _check_codes(mk, list(source.universe()), "받은 종목군")
            except Exception as e:
                raise H1DataProblem("D2", f"종목군 목록을 받지 못함({type(e).__name__}: {e})")
            u_blob = _universe_blob(mk, codes, _iso(now), env)
            u_sha = _sha256_bytes(u_blob)
            _say(f"  종목군: 새로 받은 {len(codes)}종목을 고정(universe/{mk}.json)")
        fetched = _fetch_all(mk, source, now, codes, set(), CAL_PROBE[mk])           # 7 종목 시세
        _universe_check(mk, codes, fetched, set(), set(), log)
        cal, warns, d7 = calendar_check(mk, cal_all, None, fetched, codes, now)       # 6 달력
        log.problems += warns
        _probe_note(mk, warns, log)
        if d7 is not None:
            raise H1DataProblem("D7", d7.detail + " → 시작 거절(기준 지수가 따라온 뒤 다시 start)")
        prev_s, S = cal
        log.start_date = S
        if now >= next_open(mk, S):                                                  # 2b-2 검토 C-8
            raise H1Refused(EXIT_NO_LEDGER, f"지금({_iso(now)})은 S 봉 {S} 의 다음 장 시작({next_open(mk, S).isoformat()}) "
                                            "뒤라 S 봉이 늦은 봉이 돼요(첫 판단이 팀장 폴백) → 장 마감 뒤 ~ 다음 장 시작 전에 "
                                            "다시 start (국내 22:30 KST 뒤 ~ 다음날 09:00 전, 미국 07:10 KST 무렵)")
        states = new_ledgers(mk, S, restart_no=n_restarts, code_hash=ch, env=env, updated_at=_iso(now))
        decisions = DecisionLog(decisions_path(root, mk))
        if decisions.truncated:
            log.extra["decision_log_truncated"] = decisions.truncated
            log.note(f"판정 기록 마지막 줄이 반쯤 쓰여 잘라 냈어요({decisions.truncated['bytes']}바이트)")
        frames = {c: (fetched[c].df if fetched.get(c) is not None else None) for c in codes}
        _say(f"  시작 봉 S = {S} (S 전 거래일 {prev_s}) · S 는 입금만, 매매는 S+1 시가부터")
        res = run_bar(mk, S, states, frames, codes, _idle_bar(mk, idle_df, S), decisions=decisions,
                      leader_mode=leader_mode, halted=_halted_on(fetched, codes, S), prev_cal_date=prev_s,
                      calendar=cal, now=source.now, ask=_leader_ask(root, leader_mode),
                      cli_version=_cli_version_once(leader_mode), code_hash=ch, env=env,
                      allowed=allowed, head=None, universe_sha256=u_sha, meta_universe_sha256=u_sha)
        _absorb(log, res)
        _print_bar(res)
        if not res.ok:
            raise _LFound(S, res.problems, res.fingerprint)
        at = _iso(log.now())
        meta = {"market": mk, "start_date": S, "restart_no": n_restarts, "created_at": at, "rules": rule_constants(mk),
                "universe_sha256": u_sha, "code_hash_at_start": ch, "env_at_start": env,
                "design_doc_sha256": _design_sha(), "ledger_breaker": "off", "shadow_breaker": list(SHADOW_BREAKER)}
        if pre is not None and _rules_diff(meta["rules"], prereg_rules(pre)):           # 한 번 더(같은 함수라 늘 같음)
            raise H1Refused(EXIT_GATE, "새 창의 meta.rules 가 사전 등록과 달라요 → 시작 거절")
        sparts = (f"{mk}.starting",)
        blobs = _ledger_blobs(res.states, mk)
        meta_blob = _dump(meta)
        _write_set(root, sparts, {**blobs, META_REL: meta_blob})
        head = _new_head(res.states, blobs, meta_blob, decisions, log.run_id, at)
        _write_atomic(h1_path(root, *sparts, "HEAD.json"), _dump(head))
        _append_line(h1_path(root, *sparts, "calendar.jsonl"),
                     _calendar_line(cal, [S], "ok", log.run_id, at, "start", _iso(now)))
        for sub in sorted({rel.split("/")[0] for rel in LEDGER_RELS}):
            _fsync_dir(h1_path(root, *sparts, sub))
        _fsync_dir(sdir)
        if u_blob is not None:
            _write_atomic(universe_path(mk, root), u_blob)
        if pre is None and _write_prereg(mk, root, at, log.run_id):                  # 첫 start: 사전 등록 숫자를 한 번
            log.note(f"사전 등록 숫자를 prereg_{mk}.json 에 적었어요(이 시장의 모든 창·판정이 이 값을 씀, 바꾸지 않음)")
        os.replace(sdir, mdir)                                                      # 여기서 시작이 "있는 것"이 된다
        _fsync_dir(root)
        log.bars.append(S)
        log.commits.append(log.run_id)
        _print_summary(mk, root, res.states, decisions, meta, head, log, EXIT_OK, f"시작 S={S}")
        log.end(EXIT_OK, f"시작 S={S}")
        return EXIT_OK
    except KeyboardInterrupt:
        return _on_interrupt(log)
    except Exception as e:
        return _on_error(log, e)


# ============================ run (§2.3 준비 1~10) ============================

def run(market, root=None, source=None, leader_mode="llm", gate=True) -> int:
    """매일 실행(설계 §2.3): 새 확정 봉을 오래된 것부터 하나씩 처리하고, 점검을 통과한 봉마다 커밋한다.
    처리할 봉이 없으면 0(D7 이었으면 7). 5봉 넘게 밀리면 6. 자료 문제 4·7, 장부 논리 오류 2, 관문·규칙 3, 장부 없음 8."""
    mk = _mkey(market)
    root = _root(root)
    _check_mode(leader_mode)
    source = source if source is not None else live_source(mk)
    try:
        with h1_lock(root, market=mk):
            return _run_locked(mk, root, source, leader_mode, gate)
    except H1Refused as e:
        if e.code != EXIT_LOCK:
            raise
        _note_lock_timeout(root, "run", mk, e)
        return EXIT_LOCK


def _run_locked(mk, root, source, leader_mode, gate) -> int:
    log = _RunLog("run", mk, root, source.now, {"leader_mode": leader_mode, "gate": gate})
    cal_rec = {"dates": None, "processed": [], "check": None, "fetched_at": None}
    try:
        ch, _ = code_hash()
        env = env_info()
        log.begin(ch, env, leader_mode)
        _say(f"[H1 {mk}] run · {_iso(log.now())} · 실행 {log.run_id}")
        return _run_body(mk, root, source, leader_mode, gate, log, ch, env, cal_rec)
    except KeyboardInterrupt:
        return _on_interrupt(log)
    except Exception as e:
        return _on_error(log, e)
    finally:
        if cal_rec["dates"] is not None:
            try:
                _append_line(h1_path(root, mk, "calendar.jsonl"),
                             _calendar_line(cal_rec["dates"], cal_rec["processed"], cal_rec["check"] or "stopped",
                                            log.run_id, _iso(log.now()), "run", cal_rec["fetched_at"]))
            except Exception as e:
                _say(f"  (calendar.jsonl 기록 실패: {type(e).__name__}: {e})")


def _check_rules(meta, mk, root):
    """규칙 확인(설계 §2.3 준비 4, ⑩) — 하나라도 아니면 H1Refused(3):
    1 사전 등록 파일(prereg_<m>.json, 첫 start 때 적음)이 있고 이 창의 meta.rules 가 그것과 맞음(단계 4 F-2:
      세율 표 말고는 처음 값 그대로, 세율 표는 처음 표 + amend-rules 로 더한 줄의 앞부분)
    2 meta.rules == 지금 코드 상수(rule_constants)"""
    pre = _prereg_or_refuse(mk, root)
    bad = prereg_problems(pre, meta["rules"])
    if bad:
        raise H1Refused(EXIT_GATE, f"이 창의 규칙(meta.rules)이 사전 등록(prereg_{mk}.json)과 달라요 {bad} → 사전 등록 "
                                   "숫자는 바꿀 수 없어요(사람이 확인, 재시작 대상)")
    if _norm(meta["rules"]) != _norm(rule_constants(mk)):
        now_rules = rule_constants(mk)
        diff = sorted(k for k in set(meta["rules"]) | set(now_rules)
                      if _norm(meta["rules"].get(k)) != _norm(now_rules.get(k)))
        raise H1Refused(EXIT_GATE, f"규칙 상수가 시작 때(meta.rules)와 달라요: {diff} → 세율 줄 추가면 "
                                   f"python h1.py amend-rules --market {mk} --source URL, 아니면 재시작 대상")


def _check_past_fingerprints(states, allowed):
    """관문 실행: 지난 봉을 처리한 (code_hash, env) 가 모두 지금 통과 기록에 있어야 한다. 없으면 장부 논리 오류(L22)가
    아니라 관문 문제(종료 코드 3) — 통과 기록이 지워진 것이다(2b-2 검토 C-5)."""
    used = {(row.get("code_hash"), env_key(row.get("env"))) for _, _, st in _flat(states) for row in st["days"]}
    miss = used - set(allowed)
    if miss:
        rows = sorted({row["date"] for _, _, st in _flat(states) for row in st["days"]
                       if (row.get("code_hash"), env_key(row.get("env"))) in miss})
        raise H1Refused(EXIT_GATE, f"지난 봉 {len(rows)}개({rows[0]}~{rows[-1]})를 처리한 코드·환경 지문 {len(miss)}개가 "
                                   "replay_pass.json 에 없어요 → 통과 기록이 지워졌는지 확인(통과 기록은 "
                                   "h1.record_replay_pass 로만 추가). 장부 논리 오류 아님")


def _has_l(rec) -> bool:
    return any(isinstance(p, dict) and p.get("level") == "L" for p in rec.get("problems") or [])


def _pending_l_records(root, mk, S, created_at, bars) -> dict:
    """사전 등록 ④ 후보(2c 검토 R-4): 같은 창 errors.jsonl 의 L 기록 중 봉 날짜가 bars 에 있고 아직 거짓 양성 판정
    (changes.jsonl kind "false_positive")이 없는 것 → {봉: [기록…]}."""
    done = {(r.get("error_run_id"), r.get("bar")) for r in _read_log(root, "changes.jsonl")
            if r.get("kind") == "false_positive" and r.get("market") == mk}
    out = {}
    for r in _read_log(root, "errors.jsonl"):
        if r.get("market") == mk and (bars is None or r.get("date") in bars) and _in_window(r, S, created_at) \
                and _has_l(r) and (r.get("run_id"), r.get("date")) not in done:
            out.setdefault(r["date"], []).append(r)
    return out


def _false_positive_check(root, mk, t, recs, res, ch, log) -> int:
    """사전 등록 ④ 점검 함수 거짓 양성 판단(설계 §2.2 ④, 2c 검토 R-4). 봉 t 를 다시 처리해 ok 인 결과 res 를 커밋하기 전에 부른다.
    recs = 같은 창 errors.jsonl 의 봉 t L 기록(그때 '저장하려던 장부 6개의 내용 지문' F, 그때 code_hash H_old).
    (나) 이번 결과가 ok 이고 내용 지문 == F
    (가) replay_pass.json 에 H_old 의 통과 줄과 지금 code_hash(ch)의 통과 줄이 모두 있고 둘의 ledger_fingerprints 가 같음
         (= 점검만 바뀌고 장부 계산은 안 바뀜)
    둘 다 맞으면 커밋 전에 changes.jsonl 에 {"kind": "false_positive", …} 한 줄(보고서 ②-1 이 그 L 오류를 빼고 셈).
    하나라도 안 맞으면 기록하지 않고 알리기만 한다 — 그 L 오류는 그대로(재시작 대상). 처리·커밋은 어느 쪽이든 평소대로.
    그동안 처리하지 못한 봉은 늦은 봉으로 이미 센다(하루 기록 late). 돌려줌: 기록한 줄 수."""
    try:
        entries = replay_pass_entries(root)
    except (H1Refused, H1LogicError):
        entries = []
    news = [e.get("ledger_fingerprints") for e in entries if e.get("code_hash") == ch]
    n = 0
    for rec in recs:
        F, h_old, rid = rec.get("fingerprint"), rec.get("code_hash"), rec.get("run_id")
        if h_old == ch:                                   # 단계 4 F-5: 같은 코드에서 L 이 사라짐 = 비결정 → 기록 안 함
            log.note(f"④ 기록 안 함: 봉 {t} 의 L 기록(실행 {rid})은 지금과 같은 코드(code_hash {str(ch)[:12]}…)에서 났어요. "
                     "같은 코드에서 결과가 달라짐(비결정) → L 그대로(재시작 대상)")
            continue
        cond_b = res.ok and F is not None and res.fingerprint == F
        olds = [e.get("ledger_fingerprints") for e in entries if e.get("code_hash") == h_old]
        cond_a = any(isinstance(o, dict) and o and o == nw for o in olds for nw in news)
        if cond_a and cond_b:
            _append_log(root, "changes.jsonl", {
                "kind": "false_positive", "market": mk, "bar": t, "error_run_id": rid, "fingerprint": F,
                "code_hash_old": h_old, "code_hash_new": ch, "replay_fingerprints_equal": True,
                "at": _iso(log.now()), "run_id": log.run_id})
            log.extra.setdefault("false_positive", []).append({"bar": t, "error_run_id": rid})
            log.note(f"사전 등록 ④ 점검 함수 거짓 양성: 봉 {t} 의 L 기록(실행 {rid})은 (가)(나) 가 모두 맞아 재시작하지 "
                     "않아요 → changes.jsonl 에 false_positive 로 적고 커밋")
            n += 1
            continue
        why = []
        if not cond_b:
            why.append("(나) 그때 저장하려던 내용 지문이 없음(예외로 끝난 봉)" if F is None
                       else "(나) 다시 처리한 장부 내용 지문이 그때 저장하려던 지문과 다름")
        if not cond_a:
            why.append("(가) replay_pass.json 에 옛 code_hash·지금 code_hash 의 통과 줄이 다 있고 재현 내용 지문이 같아야 함")
        log.note(f"④ 조건 안 맞음 → 그 L 오류는 그대로(재시작 대상): 봉 {t} 실행 {rid} — {'; '.join(why)}")
    return n


def _window_fp_rows(states):
    """창의 하루 기록(한 장부 — 여섯 장부의 봉마다 지문은 같음)."""
    return states["A0"][TRAINERS[0]]["days"]


def _check_freeze_now(mk, root, meta, states, ch, env, log, pending=()):
    """관문 실행의 ⑥ 코드 동결 확인(단계 4 F-1): 지금 코드·환경이 이 창의 마지막 봉 지문과 다르면 freeze_transition 으로
    허용되는 변경(⑥-i h1_data.py·라이브러리 버전 / ⑥-ii 세율 줄 / ④ 점검 고침)인지 본다. 아니면 H1Refused(3) —
    되돌리거나 재시작(restart --reason rule-change). 돌려줌: 허용된 변경 결과(같으면 None)."""
    rows = _window_fp_rows(states)
    last = rows[-1]
    old = (last.get("code_hash"), _env_dict(last.get("env")))
    if (old[0], env_key(old[1])) == (ch, env_key(env)):
        return None
    try:
        entries = replay_pass_entries(root)
    except H1LogicError as e:
        raise H1Refused(EXIT_GATE, f"재현 통과 기록을 읽지 못함: {e}")
    r = freeze_transition(mk, old, (ch, env), entries, _read_log(root, "changes.jsonl"), pending)
    if not r["ok"]:
        raise H1Refused(EXIT_GATE, f"⑥ 코드 동결: 이 창의 마지막 봉({last.get('date')})을 처리한 코드·환경과 지금이 달라요"
                                   f"(바뀐 파일 {r['files']}, 바뀐 환경 {r['env']}) — 허용되지 않음: {'; '.join(r['why'])} "
                                   f"→ 코드를 되돌리거나 python h1.py restart --market {mk} --confirm {mk} "
                                   "--reason rule-change (⑤-c)")
    log.extra["freeze_change"] = {"from": old[0], "to": ch, "kinds": r["kinds"], "files": r["files"], "env": r["env"]}
    log.note(f"⑥ 허용 변경으로 확인: {', '.join(r['kinds']) or '(종류 없음)'} (바뀐 파일 {r['files']}, 환경 {r['env']})")
    return r


def _run_body(mk, root, source, leader_mode, gate, log, ch, env, cal_rec) -> int:
    allowed = allowed_fingerprints(root, gate, ch, env)                               # 3 관문
    loaded = load_market(mk, root, repair=True)                                       # 4 장부 읽기
    meta, head, states = loaded.meta, loaded.head, loaded.states
    log.start_date = meta["start_date"]
    if loaded.restored:
        log.extra["restored_from_backup"] = loaded.restored
    if gate:
        _check_past_fingerprints(states, allowed)
    decisions = DecisionLog(decisions_path(root, mk))
    if decisions.truncated:
        log.extra["decision_log_truncated"] = decisions.truncated
        log.note(f"판정 기록 마지막 줄이 반쯤 쓰여 잘라 냈어요({decisions.truncated['bytes']}바이트, 아직 장부에 안 쓰인 줄)")
    _sync_journals(mk, root, states, meta, log)                                      # 일지 맞추기(C-7)
    l18 = h1_check.check_decisions(mk, decisions, _head_digest(head))
    if l18:
        raise _LFound(None, l18, _safe_fingerprint(states))
    _check_rules(meta, mk, root)
    if gate:                                                                          # ⑥ 코드 동결(단계 4 F-1)
        # 이번에 다시 처리할 봉(마지막 저장 봉 뒤)의 L 기록이 아직 ④ 판정 전이면 점검 고침(h1_check.py)을 잠정 허용 —
        # ④ 기록이 남지 않으면 보고서·status 의 ⑥ 칸이 위반으로 본다
        pend = _pending_l_records(root, mk, meta["start_date"], meta.get("created_at"), None)
        pend_fp = ("fp",) if any(d is not None and d > head["last_date"] for d in pend) else ()
        _check_freeze_now(mk, root, meta, states, ch, env, log, pend_fp)
    got = read_universe(mk, root)
    if got is None:
        raise _LFound(None, [h1_check.Problem("L", "L22", mk, None, None, None, f"종목군 파일 universe/{mk}.json 이 없음")],
                      _safe_fingerprint(states))
    codes, u_sha = got
    if u_sha != meta["universe_sha256"]:
        raise _LFound(None, [h1_check.Problem("L", "L22", mk, None, None, None,
                                              "종목군 파일 지문 ≠ meta.universe_sha256 (파일이 바뀜)")],
                      _safe_fingerprint(states))
    regs = delist_registrations(states)
    last, S = head["last_date"], meta["start_date"]
    now = _aware(source.now())
    _say(f"  시작 S {S} · 마지막 처리 봉 {last}")

    idle_df = _bench(mk, source, now)                                                  # 5 대기 자산
    cal_all = _dates_of(idle_df)
    prev_s = states["A0"][TRAINERS[0]]["days"][0]["prev_cal_date"]
    cal_rec["dates"] = [d for d in cal_all if d >= prev_s]
    cal_rec["fetched_at"] = _iso(now)

    need = set()                                                                       # 7 종목 시세
    for _, _, st in _flat(states):
        need |= set(st["positions"]) | {o["code"] for o in st["pending"]}
    need -= set(regs)
    fetched = _fetch_all(mk, source, now, codes, need, CAL_PROBE[mk])
    miss = sorted(c for c in need if fetched.get(c) is None)
    if miss:
        raise H1DataProblem("D2", f"보유·대기 종목 {miss} 시세를 못 받음(인수·상장폐지 의심이면 설계 §2.2 ⑦)")
    _universe_check(mk, codes, fetched, need, set(regs), log)

    try:                                                                               # 6 달력
        cal, warns, d7 = calendar_check(mk, cal_all, states, fetched, codes, now, _last_ok_calendar_line(root, mk))
    except H1DataProblem as e:
        cal_rec["check"] = e.kind
        raise
    cal_rec["dates"] = list(cal)
    cal_rec["check"] = "D7" if d7 is not None else "ok"
    log.problems += warns
    _probe_note(mk, warns, log)
    if d7 is not None:
        log.problems.append(d7)
        _say(f"  {d7.detail} → 처리할 수 있는 봉까지만 하고 종료 코드 7")

    dfs = {c: f.df for c, f in fetched.items() if f is not None}                       # 8 소급 수정
    prob = retro_problem(retro_compare(mk, states, dfs, idle_df))
    if prob is not None:
        raise prob

    todo = [d for d in cal if d > last]                                                # 9 처리할 봉
    if not todo:
        code = EXIT_D7 if d7 is not None else EXIT_OK
        _say(f"  새 확정 봉 없음 — 이미 처리됨({last}). 스캔·팀장 호출 없이 끝")
        msg = "이미 처리됨" if code == EXIT_OK else d7.detail
        _print_summary(mk, root, states, decisions, meta, head, log, code, msg)
        log.end(code, msg)
        return code
    if len(todo) > MAX_LATE_BATCH:
        raise H1Refused(EXIT_BACKLOG, f"밀린 봉 {len(todo)}개({todo[0]}~{todo[-1]}) > {MAX_LATE_BATCH} → 판정 창 실패"
                                      f"(사전 등록 ②-2). python h1.py restart --market {mk} → start")
    _say(f"  처리할 봉 {len(todo)}개: {', '.join(todo)}")

    fp_cands = _pending_l_records(root, mk, S, meta.get("created_at"), set(todo))     # ④ 거짓 양성 후보(2c R-4)
    cli_version = _cli_version_once(leader_mode)                                       # 10 봉마다
    ask = _leader_ask(root, leader_mode)
    frame_codes = list(dict.fromkeys(list(codes) + sorted(need)))
    frames = {c: (fetched[c].df if fetched.get(c) is not None else None) for c in frame_codes}
    for k, t in enumerate(todo, 1):
        halted = _halted_on(fetched, frame_codes, t)
        idle = _idle_bar(mk, idle_df, t)
        _bar_data_check(mk, t, states, frames, halted)
        res = run_bar(mk, t, states, frames, codes, idle, decisions=decisions,
                      leader_mode=leader_mode, halted=halted,
                      prev_cal_date=cal[cal.index(t) - 1], calendar=cal, now=source.now, ask=ask, cli_version=cli_version,
                      code_hash=ch, env=env, allowed=allowed, head=_head_digest(head), universe_sha256=u_sha,
                      meta_universe_sha256=meta["universe_sha256"])
        _absorb(log, res)
        _print_bar(res)
        if not res.ok:
            raise _LFound(t, res.problems, res.fingerprint)
        if fp_cands.get(t):                              # 이 봉에서 전에 난 L 기록 → 사전 등록 ④ 판단(커밋 전에 기록)
            _false_positive_check(root, mk, t, fp_cands[t], res, ch, log)
        at = _iso(log.now())
        for _, _, st in _flat(res.states):
            st["h1"].update({"code_hash": ch, "env": dict(env), "updated_at": at})
        commit_id = log.run_id if k == 1 else f"{log.run_id}.{k}"
        head, blobs = commit(root, mk, res.states, meta, decisions, commit_id, at, head)
        states = _parse_ledgers(mk, blobs)              # 디스크에 쓴 글자 그대로 다시 읽어 다음 봉에(저장 → 읽기와 같은 길)
        log.bars.append(t)
        log.commits.append(commit_id)
        cal_rec["processed"].append(t)
        _say(f"  봉 {t} 저장 완료(HEAD {commit_id})")
    code, msg = (EXIT_D7, d7.detail) if d7 is not None else (EXIT_OK, f"{len(todo)}봉 처리")
    _print_summary(mk, root, states, decisions, meta, head, log, code, msg)
    log.end(code, msg)
    return code


# ============================ restart (§2.2 ⑤, §2.5) ============================

RESTART_REASONS = {"L": "창 안의 장부 논리 오류(④ 로 빠지지 않은 L)",
                   "backlog": "밀린 봉 초과(종료 코드 6)·늦은 봉 상한 초과",
                   "rule-change": "⑥ 이 허용하지 않는 코드·환경 변경(⑤-c) 또는 ⑦-3 기업 행위(D6·D4·D5 자료 멈춤)"}


def restart(market, reason, root=None, *, confirm=None, note=None) -> Path:
    """재시작(설계 §2.2 ⑤): 잠금 아래에서 state/h1/<m>/ 를 state/h1/archive/<m>-<시각>/ 로 옮긴다(판정 기록·일지·고정 종목군
    ·사전 등록은 그대로). 단계 4 F-4 확인:
    - confirm == market(같은 시장을 --confirm 으로 다시 침)이 아니면 9.
    - reason 은 사유 코드 셋 중 하나(RESTART_REASONS): "L" / "backlog" / "rule-change". 그 근거가 일지(errors·runs·changes
      .jsonl)·지금 코드에 없으면 9(무엇이 없는지 알림). note = 사람이 적는 설명(restarts.jsonl 에 같이 남음).
    - 지금 코드의 사전 등록 숫자가 prereg_<m>.json 과 다르면 3(F-2). 재시작 상한·마감은 사전 등록 값으로(8).
    - 옮기기 전에 S·처리한 봉 수·L 오류·남은 재시작을 화면에 보여 준다.
    기록 순서(2b-2 검토 C-6): restarts.jsonl 에 의도 줄(status "moving", 보관 경로) + fsync → 폴더 옮김 → 끝 줄("done").
    앞 restart 가 중간에 꺼졌으면(의도 줄만 있음) 이번 restart 는 새 재시작을 하지 않고 그것을 마저 끝낸다(횟수는 한 번,
    confirm 은 필요). 옮긴 폴더 경로를 돌려준다. 거절은 H1Refused: 9 확인·사유·근거 / 8 시장 폴더 없음·상한·마감 /
    3 사전 등록 숫자 다름 / 5 잠금."""
    mk = _mkey(market)
    root = _root(root)
    if confirm != mk:
        raise H1Refused(EXIT_USAGE, f"재시작은 시장을 한 번 더 쳐야 해요: --market {mk} --confirm {mk} (받은 --confirm "
                                    f"{confirm!r}) — 잘못 친 시장의 창을 옮기지 않게(단계 4 F-4)")
    if reason not in RESTART_REASONS:
        raise H1Refused(EXIT_USAGE, f"재시작 사유(--reason)는 {list(RESTART_REASONS)} 중 하나예요(받은 값 {reason!r}). "
                                    "설명은 --note \"…\" 로")
    try:
        lock = h1_lock(root, market=mk)
        lock.__enter__()
    except H1Refused as e:
        _note_lock_timeout(root, "restart", mk, e)
        raise
    try:
        log = _RunLog("restart", mk, root, None, {"reason": reason, "note": note, "confirm": confirm})
        try:
            log.begin(code_hash()[0], env_info(), None)
            return _restart_locked(mk, root, reason, log, note)
        except KeyboardInterrupt:
            _on_interrupt(log)
            raise
        except H1Refused as e:
            _say(f"  거절: {e}")
            log.end(e.code, str(e))
            raise
        except Exception as e:
            _on_error(log, e)
            raise
    finally:
        lock.__exit__(None, None, None)


def _lenient_meta(mk, root) -> dict:
    try:
        d = json.loads(_rel_path(root, (mk,), META_REL).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _restart_evidence(mk, root, reason, loaded, pre, log) -> list:
    """재시작 사유 코드의 근거(단계 4 F-4). 돌려줌: 근거 글 목록(비면 근거 없음 → 부르는 쪽이 9).
    장부를 읽었으면 status·보고서와 같은 함수(window_counts·freeze_window)로 센다. 장부를 못 읽으면(L24) 일지만 너그럽게 본다."""
    ev = []
    if loaded is not None:
        w = window_counts(mk, root, loaded=loaded, exclude_run_ids=(log.run_id,))
        if reason == "L":
            if w["l_errors"]:
                ev.append(f"창 안 L 오류 {w['l_errors']}건 {w['l_codes']}(④ 거짓 양성으로 뺀 것 제외)")
        elif reason == "backlog":
            cap_total = pre["rules"].get("max_late_total", MAX_LATE_TOTAL)
            cap_batch = pre["rules"].get("max_late_batch", MAX_LATE_BATCH)
            if w["backlog_fail"]:
                ev.append(f"밀린 봉 초과로 멈춤(종료 코드 6) {w['backlog_fail']}번")
            if len(w["late"]) > cap_total:
                ev.append(f"늦은 봉 {len(w['late'])}개 > 사전 등록 상한 {cap_total}")
            if w["batch_max"] > cap_batch:
                ev.append(f"한 번에 따라잡은 봉 {w['batch_max']} > 사전 등록 상한 {cap_batch}")
        else:
            states, meta = loaded.states, loaded.meta
            try:
                entries = replay_pass_entries(root)
            except (H1Refused, H1LogicError):
                entries = []
            changes = _read_log(root, "changes.jsonl")
            rows = _window_fp_rows(states)
            last = (rows[-1].get("code_hash"), _env_dict(rows[-1].get("env")))
            ch, env = code_hash()[0], env_info()
            if (ch, env_key(env)) != (last[0], env_key(last[1])):
                r = freeze_transition(mk, last, (ch, env), entries, changes)
                if not r["ok"]:
                    ev.append(f"지금 코드·환경이 창의 마지막 봉({rows[-1]['date']}) 지문과 다르고 ⑥ 이 허용하지 않음"
                              f"(바뀐 파일 {r['files']}, 환경 {r['env']}): {'; '.join(r['why'])}")
            for t in freeze_window(mk, rows, entries, changes):
                if not t["ok"]:
                    ev.append(f"창 안 {t['date']} 에 ⑥ 이 허용하지 않는 코드·환경 변경: {'; '.join(t['why'])}")
            seen = set()
            for c in changes:
                if c.get("kind") != "replay-pass" or not _at_or_after(c.get("at"), meta.get("created_at") or ""):
                    continue
                key = (c.get("code_hash"), env_key(c.get("env")))
                if key in seen or key == (last[0], env_key(last[1])):
                    continue
                seen.add(key)
                r = freeze_transition(mk, last, (c.get("code_hash"), _env_dict(c.get("env"))), entries, changes)
                if not r["ok"]:
                    ev.append(f"창이 만들어진 뒤 재현을 통과한 코드 {str(c.get('code_hash'))[:12]}… 가 창의 지문에서 ⑥ 허용 밖"
                              f"(바뀐 파일 {r['files']}): {'; '.join(r['why'][:2])}")
            for k in ("D6", "D4", "D5"):
                if w["data_kinds"].get(k):
                    ev.append(f"자료 멈춤 {k} {w['data_kinds'][k]}번(⑦-3: 공식으로 이어 갈 수 없는 기업 행위·제공처가 고치지 "
                              "않는 달력 문제일 때)")
        return ev
    # 장부를 못 읽음: 일지만 너그럽게(지금 창 = 시장 폴더 meta 의 S·created_at 을 너그럽게 읽은 값)
    lm = _lenient_meta(mk, root)
    S, created = lm.get("start_date") or _peek_start_date(mk, root), lm.get("created_at")
    errs = [r for r in _read_log(root, "errors.jsonl") if r.get("market") == mk and _in_window(r, S, created)]
    ends = [r for r in _read_log(root, "runs.jsonl") if r.get("market") == mk and r.get("event") == "end"
            and _in_window(r, S, created)]
    if reason == "L":
        n = len({r.get("run_id") for r in errs if _has_l(r)} | {r.get("run_id") for r in ends
                                                                  if r.get("exit_code") == EXIT_LOGIC})
        if n:
            ev.append(f"장부를 읽지 못함 — 일지의 L 오류(errors.jsonl·종료 코드 2) {n}건")
    elif reason == "backlog":
        n = sum(1 for r in ends if r.get("exit_code") == EXIT_BACKLOG)
        if n:
            ev.append(f"장부를 읽지 못함 — 일지의 밀린 봉 초과(종료 코드 6) {n}번")
    else:
        n = sum(1 for r in ends if r.get("exit_code") == EXIT_GATE and "⑥" in str(r.get("message")))
        d = sum(1 for r in ends if r.get("exit_code") == EXIT_DATA and any(
            isinstance(p, dict) and p.get("code") in ("D6", "D4", "D5") for p in r.get("problems") or []))
        if n:
            ev.append(f"장부를 읽지 못함 — 일지의 ⑥ 코드 동결 거절(종료 코드 3) {n}번")
        if d:
            ev.append(f"장부를 읽지 못함 — 일지의 D6·D4·D5 자료 멈춤 {d}번(⑦-3)")
    return ev


def _restart_locked(mk, root, reason, log, note=None) -> Path:
    mdir = market_dir(mk, root)
    pend = _pending_restarts(mk, root)
    if pend:                                                    # 앞 restart 가 옮기다 꺼짐 → 마저 끝냄
        rec = pend[-1]
        dest = _archive_path(root, rec)
        if mdir.is_dir() and dest.exists():
            raise H1Refused(EXIT_NO_LEDGER, f"시장 폴더와 보관 폴더({rec.get('archive')})가 둘 다 있어요 → 사람이 확인")
        if mdir.is_dir():
            _mkdirs(dest.parent)
            os.replace(mdir, dest)
            _fsync_dir(dest.parent)
            _fsync_dir(root)
        elif not dest.exists():
            raise H1Refused(EXIT_NO_LEDGER, f"끝나지 않은 재시작 기록의 보관 폴더({rec.get('archive')})도 시장 폴더도 없어요 "
                                            "→ 사람이 확인")
        _append_log(root, "restarts.jsonl", {"status": "done", "restart_id": _restart_id(rec), "market": mk,
                                             "at": _iso(log.now()), "archive": rec.get("archive"), "recovered": True,
                                             "recovered_by": log.run_id})
        log.start_date = rec.get("old_start") or log.start_date
        pre = read_prereg(mk, root)
        cap = (pre or {}).get("rules", {}).get("max_restarts", MAX_RESTARTS)
        msg = (f"끝나지 않았던 재시작({rec.get('reason')!r}, 보관 {rec.get('archive')})을 마저 끝냈어요 — 이번 명령은 "
               f"새 재시작을 하지 않았어요(횟수 {restart_info(mk, root)['used']}/{cap}). 다음: start")
        _say(f"[H1 {mk}] {msg}")
        log.end(EXIT_OK, msg)
        return dest
    if not mdir.is_dir():
        raise H1Refused(EXIT_NO_LEDGER, f"{mk} 장부 폴더가 없어요 — 재시작할 것이 없음")
    pre = _check_code_vs_prereg(mk, root, "restart")                  # 단계 4 F-2: 사전 등록 숫자 그대로인지
    cap = pre["rules"].get("max_restarts", MAX_RESTARTS)
    deadline = pre["rules"].get("deadline", DEADLINE)
    n = restart_info(mk, root, _meta_or_none(mk, root))["used"]       # 보고서 R-7 과 같은 규칙(세 출처 중 큰 값)
    if n >= cap:
        raise H1Refused(EXIT_NO_LEDGER, f"{mk} 재시작을 이미 {n}번 했어요(사전 등록 상한 {cap}, ⑤) → "
                                        "'H1 포워드 실패(운영 기준 미충족)'로 보고하고 멈춤")
    today = log.now().date().isoformat()
    if today > str(deadline):
        raise H1Refused(EXIT_NO_LEDGER, f"마감 {deadline} 이 지났어요(오늘 {today}) → 'H1 포워드 실패(운영 기준 미충족)'로 "
                                        "보고하고 멈춤(재시작해도 판정 창을 끝낼 수 없음)")
    loaded = None
    try:                                                        # 옮기기 전에 일지를 장부와 맞춘다(읽히면)
        loaded = load_market(mk, root, repair=True)
        _sync_journals(mk, root, loaded.states, loaded.meta, log)
    except (H1LogicError, H1Refused) as e:
        log.note(f"장부를 읽지 못해 일지 맞추기는 건너뜀({getattr(e, 'code', '')} {e}) — 근거는 일지만으로 봄")
        loaded = None
    evidence = _restart_evidence(mk, root, reason, loaded, pre, log)    # 단계 4 F-4
    if not evidence:
        raise H1Refused(EXIT_USAGE, f"재시작 사유 {reason!r}({RESTART_REASONS[reason]})의 근거가 이 창의 일지·코드에 없어요 "
                                    "→ 재시작하지 않음(창은 그대로). 사유가 맞는지 python h1.py status 와 보고서로 확인")
    lm = _lenient_meta(mk, root)
    old_start = lm.get("start_date")
    old_last = None
    try:
        old_last = json.loads(h1_path(root, mk, "HEAD.json").read_text("utf-8")).get("last_date")
    except Exception:
        pass
    n_bars = len(_window_fp_rows(loaded.states)) if loaded is not None else None
    wb = pre["rules"].get("window_bars", WINDOW_BARS)
    _say(f"[H1 {mk}] 재시작 전 확인: 창 S {old_start} · 마지막 처리 봉 {old_last} · 처리한 봉 "
         f"{'?' if n_bars is None else n_bars}/{wb} · 재시작 {n}/{cap} → 이번이 {n + 1}번째(뒤에 남는 재시작 {cap - n - 1}번) · "
         f"마감 {deadline}")
    _say(f"  사유 {reason}({RESTART_REASONS[reason]}) 근거: " + " / ".join(evidence[:5]))
    if note:
        _say(f"  설명: {note}")
    stamp = log.now().strftime("%Y%m%d-%H%M%S")
    dest = h1_path(root, "archive", f"{mk}-{stamp}")
    i = 2
    while dest.exists():
        dest = h1_path(root, "archive", f"{mk}-{stamp}-{i}")
        i += 1
    rel = "/".join(dest.relative_to(root).parts)
    rid = log.run_id
    _append_log(root, "restarts.jsonl", {"status": "moving", "restart_id": rid, "at": _iso(log.now()), "market": mk,
                                         "old_start": old_start, "old_last": old_last, "reason": reason, "note": note,
                                         "evidence": evidence, "bars": n_bars, "archive": rel, "run_id": rid,
                                         "restart_no": n + 1})
    _mkdirs(dest.parent)
    os.replace(mdir, dest)
    _fsync_dir(dest.parent)
    _fsync_dir(root)
    _append_log(root, "restarts.jsonl", {"status": "done", "restart_id": rid, "at": _iso(log.now()), "market": mk,
                                         "archive": rel, "run_id": rid})
    _say(f"[H1 {mk}] 재시작 {n + 1}/{cap}: 옛 장부(S {old_start} ~ {old_last})를 {dest} 로 옮겼어요. "
         f"다음: python h1.py start --market {mk}")
    log.end(EXIT_OK, f"보관 {dest.name}")
    return dest


# ============================ corp-action (§2.2 ⑦) ============================

def corp_action(market, code, *, split=None, date=None, delist=False, last_date=None, last_close=None,
                accept_correction=False, source=None, root=None, source_data=None, gate=True, confirm=None,
                cancel_delist=False) -> int:
    """기업 행위 적용(설계 §2.2 ⑦). 넷 중 하나만: split(⑦-2) / delist(⑦-4) / accept_correction(⑦-5) /
    cancel_delist(상장폐지 등록 취소, 단계 4 F-3).
    delist·cancel_delist 는 confirm == code(같은 종목코드를 --confirm 으로 다시 침)여야 한다(아니면 9, 오타 방지).
    delist 는 그 종목이 정말 거래되지 않을 때만 받는다(단계 4 F-3): 지금 시세를 받을 수 없거나(D2), 받은 확정 시세의
    마지막 거래일이 --last-date 이하(그 뒤 거래 행 없음 — 국내 거래량 0 정지 행은 확정 시세에서 이미 빠짐). 그 뒤에 거래한
    행이 있으면 "아직 거래 중"으로 거절(9). 등록에 registered_after(그때 장부 마지막 처리 봉)를 같이 적는다.
    cancel_delist 는 아직 정리하지 않은 등록만(등록 뒤 봉을 처리하지 않았고 정리 체결이 없음) 취소한다: 장부 corp_actions 에
    {"kind": "delist_cancel"} 줄을 더하고(엔진·L23 은 취소된 등록을 보지 않음) 일지에도 남긴다.
    source = 1차 출처(URL 등 글자), source_data = 지금 시세를 받는 DataSource(기본 live_source, 시험·재현은 가짜 —
    split·accept_correction 이 쓰고, 기록 시각도 그 시계로 적는다).
    split: r 은 2·0.5 뿐 아니라 "1/3"·"3:1"(새 주식 3 : 옛 주식 1 → r=3) 도 받는다(정확한 분수로 정수 확인, C-16).
      date = 새 주식 수로 거래되는 첫 날(효력일). 장부 last_date 보다 뒤여야 하고, 같은 종목·같은 효력일 분할이 이미 있으면
      거절, 지금 D6 이 그 종목을 같은 비율 r 의 '분할 의심'으로 보고 있을 때만 받는다(C-2·C-9).
    accept_correction: 차이가 모든 칸에서 같은 비율(분할 모양)이면 거절 → split 을 쓰라고 안내(C-10).
    관문(재현 통과 지문)과 meta.rules 확인을 거친다(C-11). run 과 같은 잠금·커밋 순서(백업 → 장부 6개 → HEAD, 새 run_id)로
    쓰고, 그 뒤 corp_actions.jsonl·changes.jsonl 에 남긴다(빠지면 다음 명령이 장부에서 채움, C-7).
    종료 코드: 0 적용 / 9 인자·조건이 맞지 않음(아무것도 안 바뀜) / 3 관문·규칙 / 2 장부 손상(L24) / 4 시세 못 받음·환경 /
    5 잠금 / 8 장부 없음."""
    mk = _mkey(market)
    root = _root(root)
    try:
        with h1_lock(root, market=mk):
            return _corp_locked(mk, root, code, split, date, delist, last_date, last_close, accept_correction,
                                source, source_data, gate, confirm, cancel_delist)
    except H1Refused as e:
        if e.code != EXIT_LOCK:
            raise
        _note_lock_timeout(root, "corp-action", mk, e)
        return EXIT_LOCK


def parse_ratio(v):
    """분할 비율 r(= 새 주식 수 ÷ 옛 주식 수)을 정확한 분수로. "2"·"0.5"·"1/3"·"3:1"(새 3 : 옛 1 → 3)·숫자를 받는다.
    0 이하·1·모양이 이상하면 ValueError."""
    from fractions import Fraction
    if isinstance(v, bool):
        raise ValueError(f"분할 비율이 이상해요: {v!r}")
    if isinstance(v, Fraction):
        r = v
    elif isinstance(v, int):
        r = Fraction(v)
    elif isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError(f"분할 비율이 이상해요: {v!r}")
        r = Fraction(repr(v))
    elif isinstance(v, str):
        t = v.strip()
        try:
            if ":" in t:
                a, b = t.split(":")
                r = Fraction(a.strip()) / Fraction(b.strip())
            else:
                r = Fraction(t)
        except (ValueError, ZeroDivisionError):
            raise ValueError(f"분할 비율 {v!r} 을 읽지 못함(예: 2, 0.5, 1/3, 3:1)")
    else:
        raise ValueError(f"분할 비율이 이상해요: {v!r}")
    if r <= 0 or r == 1:
        raise ValueError(f"분할 비율 r 은 1 이 아닌 양수여야 해요(받은 값 {v!r})")
    return r


def _marks_last(states, code):
    """장부들의 그 종목 마지막 marks (날짜, 값). 없으면 None. 같은 날짜에 값이 다르면 ValueError."""
    best = None
    for _, _, st in _flat(states):
        for row in reversed(st["days"]):
            if code in row["marks"]:
                cand = (row["date"], row["marks"][code])
                if best is None or cand[0] > best[0]:
                    best = cand
                elif cand[0] == best[0] and cand[1] != best[1]:
                    raise ValueError(f"{code} 같은 날 {cand[0]} marks 가 장부마다 다름")
                break
    return best


def _corp_fetch(mk, sd, code, now):
    """정정 확정·분할 확인용: 그 종목(또는 대기 자산)의 지금 시세 → (dfs, idle_df)."""
    if code == idle_code(mk):
        return {}, _bench(mk, sd, now)
    f = _fetch_all(mk, sd, now, [code], set(), ())[code]
    if f is None:
        raise H1DataProblem("D2", f"{code} 시세를 못 받음")
    return {code: f.df}, None


def _corp_locked(mk, root, code, split, date, delist, last_date, last_close, accept_correction, source, source_data,
                 gate, confirm=None, cancel_delist=False):
    args = {"code": code, "split": None if split is None else str(split), "date": date, "delist": bool(delist),
            "last_date": last_date, "last_close": last_close, "accept_correction": bool(accept_correction),
            "cancel_delist": bool(cancel_delist), "confirm": confirm, "source": source, "gate": gate}
    now_fn = source_data.now if source_data is not None else None
    log = _RunLog("corp-action", mk, root, now_fn, args)
    try:
        ch, _ = code_hash()
        env = env_info()
        log.begin(ch, env, None)
        kinds = [split is not None, bool(delist), bool(accept_correction), bool(cancel_delist)]
        if sum(kinds) != 1:
            raise H1Refused(EXIT_USAGE, "--split · --delist · --accept-correction · --cancel-delist 중 하나만 고르세요")
        if not isinstance(source, str) or not source.strip():
            raise H1Refused(EXIT_USAGE, "1차 출처(--source, 거래소 공시·회사 발표 주소)를 적어 주세요")
        if not isinstance(code, str) or not code:
            raise H1Refused(EXIT_USAGE, "--code 가 필요해요")
        if (delist or cancel_delist) and confirm != code:                            # 단계 4 F-3: 오타 방지
            raise H1Refused(EXIT_USAGE, f"상장폐지 {'취소' if cancel_delist else '등록'}은 같은 종목코드를 한 번 더 쳐야 해요: "
                                        f"--code {code} --confirm {code} (받은 --confirm {confirm!r})")
        idle = idle_code(mk)
        if code != idle and not markets.code_ok(mk, code):
            raise H1Refused(EXIT_USAGE, f"{code} 는 이 시장({mk}) 종목코드가 아니에요")
        allowed_fingerprints(root, gate, ch, env)                                   # 관문(C-11)
        loaded = load_market(mk, root, repair=True)
        log.start_date = loaded.meta["start_date"]
        states, head, meta = loaded.states, loaded.head, loaded.meta
        _sync_journals(mk, root, states, meta, log)                                  # 일지 맞추기(C-7)
        _check_rules(meta, mk, root)                                                       # 규칙 상수(C-11)
        decisions = DecisionLog(decisions_path(root, mk))
        l18 = h1_check.check_decisions(mk, decisions, _head_digest(head))
        if l18:
            raise _LFound(None, l18, _safe_fingerprint(states))
        regs = delist_registrations(states)
        at = _iso(log.now())
        if split is not None:
            new, what = _corp_split(mk, root, states, head, code, split, date, source, at, source_data, regs, log)
        elif delist:
            new, what = _corp_delist(mk, states, head, code, last_date, last_close, source, at, regs, source_data)
        elif cancel_delist:
            new, what = _corp_cancel_delist(mk, states, head, code, source, at, regs)
        else:
            new, what = _corp_correction(mk, states, code, source, at, source_data, log)
        for _, _, st in _flat(new):
            st["h1"]["updated_at"] = at
        entry = new["A0"][TRAINERS[0]]["corp_actions"][-1]                       # 일지에는 장부에 적힌 줄 그대로
        head2, _ = commit(root, mk, new, meta, decisions, log.run_id, at, head)
        log.commits.append(log.run_id)
        _append_line(h1_path(root, mk, "corp_actions.jsonl"), {**entry, "run_id": log.run_id})
        _append_log(root, "changes.jsonl", {"at": at, "market": mk, "kind": f"corp-action:{entry['kind']}",
                                            "entry": entry, "run_id": log.run_id, "ledger_last_date": head2["last_date"]})
        _say(f"[H1 {mk}] 기업 행위 적용: {what}")
        log.end(EXIT_OK, what)
        return EXIT_OK
    except KeyboardInterrupt:
        return _on_interrupt(log)
    except Exception as e:
        return _on_error(log, e)


def _corp_split(mk, root, states, head, code, split, date, source, at, source_data, regs, log):
    """⑦-2 순수 분할·병합. 확인 순서: 비율(정확한 분수) → 효력일 > last_date → 같은 분할 없음 → 보유 장부 있음 →
    주식 수 × r 이 정수(부동소수점 곱도 정확히 같은 정수) → 지금 시세로 D6 이 같은 비율의 '분할 의심'을 봄 →
    적용한 뒤 D6 비교가 깨끗함. 하나라도 아니면 H1Refused(9)(아무것도 안 바뀜)."""
    idle = idle_code(mk)
    try:
        r_exact = parse_ratio(split)
    except ValueError as e:
        raise H1Refused(EXIT_USAGE, str(e))
    r = float(r_exact)
    try:
        _check_iso(date, "--date(효력일)")
    except ValueError as e:
        raise H1Refused(EXIT_USAGE, str(e))
    last = head["last_date"]
    if code == idle:
        raise H1Refused(EXIT_USAGE, "대기 자산(지수)에는 분할을 적용하지 않아요")
    if code in regs:
        raise H1Refused(EXIT_USAGE, f"{code} 는 상장폐지로 등록된 종목이에요")
    if not date > last:
        raise H1Refused(EXIT_USAGE, f"효력일 --date {date} 가 장부 마지막 처리 봉 {last} 보다 뒤가 아니에요. --date 는 새 주식 "
                                    "수로 거래되는 첫 날이에요. 이미 처리한 봉에 걸친 분할은 공식으로 이어 갈 수 없어요 → "
                                    "⑦-3 재시작 또는(분할이 아니면) 정정 확정 대상")
    dup = [ca for ca in states["A0"][TRAINERS[0]]["corp_actions"]
           if ca.get("kind") == "split" and ca.get("code") == code and ca.get("date") == date]
    if dup:
        raise H1Refused(EXIT_USAGE, f"{code} 효력일 {date} 분할은 이미 적용돼 있어요(r={dup[0].get('r')}) — 다시 적용하지 않음")
    holders = [(arm, tn, st) for arm, tn, st in _flat(states) if code in st["positions"]]
    if not holders:
        raise H1Refused(EXIT_USAGE, f"{code} 를 보유한 장부가 없어 분할을 적용할 것이 없어요(대기 주문은 새 시세로 체결되므로 "
                                    "그대로 둠)")
    for arm, tn, st in holders:
        q = st["positions"][code]["shares"] * r_exact
        qf = st["positions"][code]["shares"] * r
        if q.denominator != 1:
            raise H1Refused(EXIT_USAGE, f"{arm}/{tn}: {code} {st['positions'][code]['shares']}주 × {r_exact} = {q} 가 정수가 "
                                        "아님 → 공식 적용 불가(⑦-3 재시작 대상)")
        if not (float(qf).is_integer() and int(qf) == q.numerator):
            raise H1Refused(EXIT_USAGE, f"{arm}/{tn}: 비율 {r_exact} 을 부동소수점으로 곱하면 정확히 {q} 가 되지 않음 → "
                                        "공식 적용 불가(⑦-3 재시작 대상)")
    sd = source_data if source_data is not None else live_source(mk)
    now = _aware(sd.now())
    dfs, _ = _corp_fetch(mk, sd, code, now)
    comps = retro_compare(mk, states, dfs, None, codes={code})
    seen = split_ratio(comps)
    if seen is None:
        nd = sum(1 for c in comps if not c["same"])
        raise H1Refused(EXIT_USAGE, f"지금 D6 이 {code} 를 분할 모양으로 보지 않아요(비교 {len(comps)}곳 중 다름 {nd}곳) → "
                                    "제공처가 지난 시세를 아직 고치지 않았거나 분할이 아님. 분할을 적용하지 않음")
    if abs(seen - r) > RETRO_TOL * max(abs(seen), abs(r)):
        raise H1Refused(EXIT_USAGE, f"D6 이 보는 비율 {seen:.6g} ≠ --split {r_exact}({r:.6g}) → 1차 출처의 비율을 다시 확인")
    try:
        new = apply_split(states, code, r, date, source, at)
    except ValueError as e:
        raise H1Refused(EXIT_USAGE, f"분할 공식을 적용할 수 없어요: {e} → 설계 §2.2 ⑦-3(재시작) 검토")
    for _, _, st in _flat(new):
        st["corp_actions"][-1]["r_exact"] = str(r_exact)
    after = [c for c in retro_compare(mk, new, dfs, None, codes={code}) if not c["same"]]
    if after:
        raise H1Refused(EXIT_USAGE, f"분할을 적용해도 D6 차이 {len(after)}곳이 남아요(예: {after[0]['date']} "
                                    f"{after[0]['field']}) → 적용하지 않음")
    held = len(holders)
    return new, (f"분할 {code} r={r_exact} (효력일 {date}, 보유 장부 {held}개: 주식 수 ×r·매수가 ÷r, 평가액 그대로, "
                 f"D6 비교가 맞음을 확인)")


def _delist_evidence(mk, code, last_date, source_data):
    """상장폐지 증거(단계 4 F-3): 지금 그 종목 시세를 받아 본다. 못 받음(None·예외 = D2) → 받음.
    받은 확정 시세(국내 거래량 0 정지 행은 확정 시세에서 이미 빠짐)에 --last-date 뒤 행이 있으면 "아직 거래 중" → H1Refused(9).
    돌려줌: 증거 설명 글."""
    sd = source_data if source_data is not None else live_source(mk)
    now = _aware(sd.now())
    try:
        f = sd.fetch(code, now)
    except Exception as e:
        _say(f"    ({code} 시세 받기 실패: {type(e).__name__}: {e})")
        f = None
    if f is None or getattr(f, "df", None) is None or len(f.df) == 0:
        return f"지금 시세를 받을 수 없음(D2, {_iso(now)})"
    dates = _dates_of(f.df)
    after = [d for d in dates if d > last_date]
    if after:
        raise H1Refused(EXIT_USAGE, f"{code} 는 아직 거래 중이에요: 지금 받은 확정 시세에 --last-date {last_date} 뒤 거래한 봉 "
                                    f"{len(after)}개({after[0]}~{after[-1]})가 있어요 → 종목코드·마지막 거래일을 1차 출처로 다시 "
                                    "확인(오타면 아무것도 바뀌지 않았어요). 정말 상장폐지면 거래가 멈춘 뒤 다시 등록")
    return f"지금 받은 확정 시세의 마지막 거래일 {dates[-1]} ≤ --last-date {last_date} (그 뒤 거래 행 없음, {_iso(now)})"


def _corp_delist(mk, states, head, code, last_date, last_close, source, at, regs, source_data=None):
    if code == idle_code(mk):
        raise H1Refused(EXIT_USAGE, "대기 자산(지수)은 상장폐지로 등록할 수 없어요")
    if code in regs:
        raise H1Refused(EXIT_USAGE, f"{code} 는 이미 상장폐지로 등록돼 있어요")
    try:
        _check_iso(last_date, "--last-date")
    except ValueError as e:
        raise H1Refused(EXIT_USAGE, str(e))
    if last_date > head["last_date"]:
        raise H1Refused(EXIT_USAGE, f"--last-date {last_date} 가 장부 마지막 처리 봉 {head['last_date']} 보다 뒤예요"
                                    " → 그 날까지 run 으로 처리한 뒤 등록(2b-1 검토 B-4)")
    how = "command"
    if last_close is None:
        try:
            got = _marks_last(states, code)
        except ValueError as e:
            raise H1Refused(EXIT_USAGE, str(e))
        if got is None:
            raise H1Refused(EXIT_USAGE, f"{code} 의 marks 가 장부에 없어요 → --last-close 를 적어 주세요")
        last_close, how = got[1], f"marks {got[0]}"
    try:
        px = float(last_close)
    except (TypeError, ValueError):
        raise H1Refused(EXIT_USAGE, f"--last-close {last_close!r} 가 숫자가 아니에요")
    if not (math.isfinite(px) and px > 0):
        raise H1Refused(EXIT_USAGE, f"--last-close {px!r} 는 양수여야 해요")
    evidence = _delist_evidence(mk, code, last_date, source_data)                  # 단계 4 F-3
    entry = {"kind": "delist", "code": code, "last_date": last_date, "last_close": px,
             "last_close_from": how, "source": source, "at": at, "registered_after": head["last_date"],
             "evidence": evidence}
    new = clone_states(states, mk)
    for _, _, st in _flat(new):
        st["corp_actions"].append(dict(entry))
    held = [f"{arm}/{tn}" for arm, tn, st in _flat(states) if code in st["positions"]]
    return new, (f"상장폐지 {code} 마지막 거래 {last_date} 종가 {px!r}({how}) — 다음 처리 봉 시가 맨 앞에서 전량 정리"
                 f"(보유 장부 {held or '없음'}), 대기 주문 dropped · 증거: {evidence} · 정리 전이면 취소: "
                 f"python h1.py corp-action --market {mk} --code {code} --cancel-delist --confirm {code} --source …")


def _corp_cancel_delist(mk, states, head, code, source, at, regs):
    """상장폐지 등록 취소(단계 4 F-3): 아직 정리하지 않은 등록만. 등록 뒤 봉을 이미 처리했거나(정리·대기 주문 지움이 장부에
    반영됨) 정리 체결이 있으면 거절(9)."""
    if code not in regs:
        raise H1Refused(EXIT_USAGE, f"{code} 는 상장폐지로 등록돼 있지 않아요 — 취소할 것이 없음")
    reg = active_delists(states["A0"][TRAINERS[0]]["corp_actions"])[code]
    fills = [f for _, _, st in _flat(states) for f in st["fills"] if f["code"] == code and f["purpose"] == "delist"]
    if fills:
        raise H1Refused(EXIT_USAGE, f"{code} 는 이미 상장폐지 정리 체결이 있어요({fills[0]['date']}) → 취소할 수 없음")
    after = reg.get("registered_after")
    if not isinstance(after, str) or head["last_date"] > after:
        raise H1Refused(EXIT_USAGE, f"{code} 상장폐지 등록 뒤 봉을 이미 처리했어요(등록 때 마지막 봉 {after}, 지금 "
                                    f"{head['last_date']}) — 정리·대기 주문 지움이 장부에 반영돼 취소할 수 없음")
    entry = {"kind": "delist_cancel", "code": code, "cancels_at": reg.get("at"), "source": source, "at": at,
             "registered_after": after}
    new = clone_states(states, mk)
    for _, _, st in _flat(new):
        st["corp_actions"].append(dict(entry))
    return new, f"상장폐지 등록 취소 {code} (등록 {reg.get('at')}, 마지막 거래일 {reg.get('last_date')}) — 장부는 그대로"


def _corp_correction(mk, states, code, source, at, source_data, log):
    sd = source_data if source_data is not None else live_source(mk)
    now = _aware(sd.now())
    dfs, idle_df = _corp_fetch(mk, sd, code, now)
    comps = retro_compare(mk, states, dfs, idle_df, codes={code})
    diffs = [c for c in comps if not c["same"]]
    if not diffs:
        raise H1Refused(EXIT_USAGE, f"{code} 는 지금 D6(소급 수정) 차이가 없어요 — 정정 확정할 것이 없음")
    if any(c["new"] is None for c in diffs):
        raise H1Refused(EXIT_USAGE, f"{code} 새 시세에 값이 없는 날짜가 있어요 → 정정 확정 불가(⑦-1 기다림 또는 ⑦-3)")
    r = split_ratio(comps)
    if r is not None:                                                           # 2b-2 검토 C-10
        if code == idle_code(mk):
            raise H1Refused(EXIT_USAGE, f"대기 자산 {code} 의 지난 시가·종가가 모두 같은 비율({r:.6g})로 바뀌었어요 → 정정 "
                                        "확정으로 받을 수 없음(지수 기준 변경이면 ⑦-3 재시작 대상)")
        raise H1Refused(EXIT_USAGE, f"{code} 차이가 모든 칸에서 같은 비율({r:.6g})이라 분할·병합 모양이에요 → 정정 확정이 "
                                    f"아니라 1차 출처 확인 뒤 corp-action --split {r:.6g} --date <효력일> 을 쓰세요")
    items = [{"date": c["date"], "field": c["field"], "old": c["old"], "new": c["new"]} for c in diffs]
    entry = {"kind": "correction", "code": code, "items": items, "source": source, "at": at}
    new = clone_states(states, mk)
    for _, _, st in _flat(new):
        st["corp_actions"].append(json.loads(json.dumps(entry)))
    return new, f"정정 확정 {code} {len(items)}칸(장부 그대로, 다음부터 D6 은 새 값과 비교)"


# ============================ amend-rules (§2.2 ⑥-ii) ============================

def amend_rules(market, source, root=None, gate=True) -> int:
    """국내 매도세 표에 줄 추가(설계 §2.2 ⑥-ii): 지금 코드 상수의 세율 표가 meta.rules 의 표 + 뒤에 더한 줄
    (시행일 > 장부 마지막 처리 봉, 날짜 오름차순)이고 나머지 규칙은 같을 때만 meta.rules 를 지금 상수로 바꾼다.
    관문(재현 통과)을 거치고, 커밋 순서(백업 → 장부 6개 → meta → HEAD)로 쓰고, changes.jsonl 에 남긴다.
    종료 코드: 0 반영(또는 이미 같음) / 3 관문 또는 '줄 추가'가 아닌 규칙 변경(재시작 대상) / 9 출처 없음 / 2·4·5·8.
    출처는 커밋 전에 changes.jsonl 에 'pending' 줄로, 커밋 뒤 'done' 줄로 남긴다(사이에 꺼지면 다음 명령이 맞춤, C-7)."""
    mk = _mkey(market)
    root = _root(root)
    try:
        with h1_lock(root, market=mk):
            return _amend_locked(mk, root, source, gate)
    except H1Refused as e:
        if e.code != EXIT_LOCK:
            raise
        _note_lock_timeout(root, "amend-rules", mk, e)
        return EXIT_LOCK


def _amend_locked(mk, root, source, gate):
    log = _RunLog("amend-rules", mk, root, None, {"source": source, "gate": gate})
    try:
        ch, _ = code_hash()
        env = env_info()
        log.begin(ch, env, None)
        if not isinstance(source, str) or not source.strip():
            raise H1Refused(EXIT_USAGE, "법령 1차 출처(--source)를 적어 주세요")
        allowed_fingerprints(root, gate, ch, env)
        loaded = load_market(mk, root, repair=True)
        log.start_date = loaded.meta["start_date"]
        meta, head = loaded.meta, loaded.head
        _sync_journals(mk, root, loaded.states, meta, log)
        old, new = _norm(meta["rules"]), _norm(rule_constants(mk))
        if old == new:
            _say(f"[H1 {mk}] 규칙이 이미 지금 코드와 같아요 — 바꿀 것 없음")
            log.end(EXIT_OK, "이미 같음")
            return EXIT_OK
        others = sorted(k for k in set(old) | set(new) if k != "stock_sell_tax" and old.get(k) != new.get(k))
        if others:
            raise H1Refused(EXIT_GATE, f"세율 표 말고도 규칙이 달라요 {others} → amend-rules 로 고칠 수 없음(재시작 대상 ⑤-c)")
        if mk != "kr":
            raise H1Refused(EXIT_GATE, "세율 표 줄 추가는 국내(kr)만 해당해요")
        o, n = old["stock_sell_tax"], new["stock_sell_tax"]
        if len(n) <= len(o) or n[:len(o)] != o:
            raise H1Refused(EXIT_GATE, "세율 표가 '앞줄 그대로 + 뒤에 줄 추가'가 아니에요(앞줄이 바뀜·줄어듦) → 재시작 대상")
        added = n[len(o):]
        dates = [row[0] for row in n]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise H1Refused(EXIT_GATE, "세율 표 날짜가 오름차순이 아니에요")
        for d, _r in added:
            if not d > head["last_date"]:
                raise H1Refused(EXIT_GATE, f"더한 줄의 시행일 {d} 이 마지막 처리 봉 {head['last_date']} 보다 뒤가 아니에요"
                                           "(지난 체결을 바꾸게 됨) → 재시작 대상")
        pre = _prereg_or_refuse(mk, root)                                              # 단계 4 F-2
        bad = prereg_problems(pre, meta["rules"])
        if bad:
            raise H1Refused(EXIT_GATE, f"이 창의 meta.rules 가 사전 등록과 달라요 {bad} → amend-rules 로 고칠 수 없음")
        pb = _norm(pre["rules"])
        others_pre = sorted(k for k in set(pb) | set(new) if k != TAX_KEY and pb.get(k) != new.get(k))
        if others_pre:
            raise H1Refused(EXIT_GATE, f"세율 표 말고도 사전 등록과 규칙이 달라요 {others_pre} → 재시작 대상 ⑤-c")
        if gate:                                                                       # ⑥: 세율 표 값만 바뀐 코드인지
            _check_freeze_now(mk, root, meta, loaded.states, ch, env, log, ("amend",))
        decisions = DecisionLog(decisions_path(root, mk))
        l18 = h1_check.check_decisions(mk, decisions, _head_digest(head))
        if l18:
            raise _LFound(None, l18, _safe_fingerprint(loaded.states))
        at = _iso(log.now())
        meta2 = dict(meta)
        meta2["rules"] = rule_constants(mk)
        line = {"market": mk, "kind": "amend-rules", "added_rows": added, "new_table": n, "source": source,
                "run_id": log.run_id, "code_hash": ch, "env": env, "ledger_last_date": head["last_date"]}
        _append_log(root, "changes.jsonl", {"at": at, **line, "status": "pending"})   # 출처를 커밋 전에 남김(C-7)
        if _norm(prereg_rules(pre).get(TAX_KEY)) != _norm(n):                          # 사전 등록에 '추가 기록'(F-2)
            pre2 = dict(pre)
            pre2["amendments"] = list(pre["amendments"]) + [{"at": at, "added_rows": added, "new_table": n,
                                                              "source": source, "run_id": log.run_id}]
            _write_atomic(prereg_path(mk, root), _dump(pre2))
        commit(root, mk, loaded.states, meta2, decisions, log.run_id, at, head)
        log.commits.append(log.run_id)
        _append_log(root, "changes.jsonl", {"at": _iso(log.now()), **line, "status": "done"})
        _say(f"[H1 {mk}] 국내 매도세 표에 줄 {added} 를 더했어요(meta.rules 갱신, 지난 체결은 그대로)")
        log.end(EXIT_OK, f"세율 줄 추가 {added}")
        return EXIT_OK
    except KeyboardInterrupt:
        return _on_interrupt(log)
    except Exception as e:
        return _on_error(log, e)


# ============================ status · 요약 (§3.3, §8.2) ============================

def status(market, root=None) -> list:
    """상태 줄들(읽기만: 백업 되살리기·판정 기록 자르기 없음). S·판정 창 진행·마지막 봉·L·자료 멈춤·늦은 봉·
    재시작·마감·장부 파일 상태 + 요약. 잠금은 잡는다(다른 명령이 쓰는 중에 반쯤 바뀐 파일을 읽지 않게)."""
    mk = _mkey(market)
    root = _root(root)
    try:
        lock = h1_lock(root, market=mk)
        lock.__enter__()
    except H1Refused as e:
        _note_lock_timeout(root, "status", mk, e)
        raise
    try:
        log = _RunLog("status", mk, root, None)
        log.begin(None, None, None)
        lines = _status_lines(mk, root, log)
        log.end(EXIT_OK if market_dir(mk, root).is_dir() else EXIT_NO_LEDGER, "상태 보기", quiet=True)
        return lines
    finally:
        lock.__exit__(None, None, None)


def _prereg_soft(mk, root):
    """(사전 등록 dict 또는 None, 못 읽은 이유 또는 None) — status·보고서용(거절하지 않음)."""
    try:
        pre = read_prereg(mk, root)
    except H1Refused as e:
        return None, str(e)
    return pre, (None if pre is not None else f"사전 등록 파일 prereg_{mk}.json 없음")


def _restart_line(mk, root, meta):
    """status 의 재시작·마감 줄. 재시작 수는 보고서 R-7 과 같은 restart_info(세 출처 중 큰 값), 상한·마감은 사전 등록 값
    (단계 4 F-2, 파일이 없으면 코드 상수 + 알림)."""
    rs = restart_info(mk, root, meta)
    n = rs["used"]
    pre, why = _prereg_soft(mk, root)
    rules = pre["rules"] if pre is not None else {}
    cap, deadline = rules.get("max_restarts", MAX_RESTARTS), str(rules.get("deadline", DEADLINE))
    days_left = (_date.fromisoformat(deadline) - _local_now().date()).days
    line = f"  재시작 {n}/{cap} (남은 {max(0, cap - n)}) · 마감 {deadline} 까지 {days_left}일"
    if why:
        line += f" · ※ {why}(상한·마감은 코드 상수로 보임)"
    if rs["mismatch"]:
        line += " · 재시작 수의 출처가 서로 다름(" + ", ".join(f"{k} {v}" for k, v in rs["sources"].items()) + " → 큰 값)"
    if rs["pending"]:
        line += f" · 끝나지 않은 restart 기록 {len(rs['pending'])}개(재시작으로 안 셈, restart 를 다시 치면 마저)"
    return line


def _status_lines(mk, root, log) -> list:
    out = []
    mdir = market_dir(mk, root)
    tail = _restart_line(mk, root, None)
    if not mdir.is_dir():
        out.append(f"[H1 {mk} 상태] 장부 없음 → python h1.py start --market {mk}")
        out.append(tail)
        return out
    try:
        loaded = load_market(mk, root, repair=False)
    except (H1LogicError, H1Refused) as e:
        out.append(f"[H1 {mk} 상태] 장부를 읽지 못함: {getattr(e, 'code', '')} {e}")
        out.append("  다음 run 이 백업으로 되살릴 수 있으면 되살리고, 아니면 L24(종료 코드 2) → 재시작 대상")
        out.append(tail)
        return out
    meta, head, states = loaded.meta, loaded.head, loaded.states
    S = meta["start_date"]
    log.start_date = S
    tail = _restart_line(mk, root, meta)
    days = states["A0"][TRAINERS[0]]["days"]
    n = len(days)
    try:
        decisions = DecisionLog(decisions_path(root, mk), read_only=True)
        dec_err = None
    except H1LogicError as e:                    # 판정 기록 손상(L18·L24) — 다음 run 이 종료 코드 2 로 멈춤
        decisions, dec_err = None, f"{e.code} {e}"
    # 일지 숫자는 보고서와 같은 함수·같은 범위(window_counts → h1_report._journal_counts, 설계 §10.2e, 단계 3):
    # L 오류 = errors.jsonl ∪ runs.jsonl 종료 코드 2(run_id 로 한 번), ④ false_positive 는 빼고 따로, 창 = _in_window
    w = window_counts(mk, root, loaded=loaded, decisions=decisions, exclude_run_ids=(log.run_id,))
    wb = w["window_bars"]                         # 판정 창 크기는 meta.rules 값(시작 때 고정, 보고서와 같음)
    out.append(f"[H1 {mk} 상태] 시작 S {S} · 마지막 처리 봉 {head['last_date']} · 판정 창 {min(n, wb)}/{wb}"
               + (f" (연장 {n - wb}봉)" if n > wb else f" (남은 {wb - n}봉)"))
    out.append(f"  장부 파일: HEAD 와 같음 (HEAD {head['run_id']}, {head['written_at']})")
    ktxt = ", ".join(f"{k} {v}" for k, v in w["data_kinds"].items())
    extra = []
    if w["l_false_positive"]:
        extra.append(f"④ 거짓 양성으로 뺀 {w['l_false_positive']}건 따로")
    if w["l_runs_only"]:
        extra.append(f"그중 errors.jsonl 기록 없이 종료 코드 2 만 {w['l_runs_only']}건")
    out.append(f"  L 오류 {w['l_errors']}" + (f" ({'; '.join(extra)})" if extra else "")
               + f" · 자료 멈춤 {w['data_stops']}" + (f" ({ktxt})" if ktxt else "")
               + f" · 관문 거절 {w['gate_refused']} · 늦은 봉 {len(w['late'])}/{w['max_late_total']}"
               + f" · 한 번에 따라잡은 최대 {w['batch_max']}봉")
    more = []
    if w["backlog_fail"]:
        more.append(f"밀린 봉 초과(종료 코드 6) {w['backlog_fail']}번")
    if w["no_end"]:
        more.append(f"끝 기록 없는 실행 {w['no_end']}번(판정에는 안 씀)")
    if w["ext_l_errors"]:
        more.append(f"연장 구간(S+62 뒤) L 오류 {w['ext_l_errors']}건(판정에는 안 씀)")
    if w["outside"]:
        more.append(f"창 밖 기록 {w['outside']}줄")
    if w["broken"]:
        more.append("읽지 못한 일지 줄 " + ", ".join(f"{k} {v}" for k, v in w["broken"].items()))
    if more:
        out.append("  " + " · ".join(more))
    out.append("  (일지 숫자 — L·④ 거짓 양성·자료 멈춤·관문 거절·늦은 봉·한 번에 따라잡은 봉·팀장 폴백 — 는 보고서 --final 과 "
               "같은 규칙·같은 범위(창이 다 찼으면 S~S+62, 덜 찼으면 지금까지). 저장 자료로 다시 점검한 L·빠진 날·다른 지문(②-3)은 "
               "보고서에서: python h1_report.py --market " + mk + " --final)")
    out += _freeze_status_lines(mk, root, meta, states)
    out.append(tail)
    if dec_err:
        out.append(f"  판정 기록을 읽지 못함: {dec_err} — 다음 run 은 종료 코드 2(장부 논리 오류)로 멈춤")
    elif decisions.truncated:
        out.append(f"  판정 기록 마지막 줄이 반쯤 쓰여 있음({decisions.truncated['bytes']}바이트) — 다음 run 이 잘라 냄")
    out += summary_lines(mk, states, errors=w["l_errors"], data_stops=w["data_stops"], counts=w)
    return out


def _freeze_status_lines(mk, root, meta, states) -> list:
    """status 의 ⑩ 사전 등록·⑥ 코드 동결 줄(단계 4 F-1·F-2). 보고서 ⑥ 칸과 같은 함수(prereg_problems·freeze_window)."""
    out = []
    pre, why = _prereg_soft(mk, root)
    if pre is None:
        out.append(f"  ⑩ 사전 등록: ※ {why} → 다음 run 은 종료 코드 3")
    else:
        r = pre["rules"]
        bad = prereg_problems(pre, meta["rules"])
        out.append(f"  ⑩ 사전 등록(prereg_{mk}.json, {pre.get('written_at')}): 창 {r.get('window_bars')}봉 · 늦은 봉 "
                   f"{r.get('max_late_total')}·한 번에 {r.get('max_late_batch')} · 재시작 {r.get('max_restarts')} · 마감 "
                   f"{r.get('deadline')} · 세율 줄 추가 {len(pre['amendments'])}번 · 이 창 meta.rules "
                   + ("와 맞음" if not bad else f"와 **다름** {bad}(판정 실패)"))
    try:
        entries = replay_pass_entries(root)
    except (H1Refused, H1LogicError) as e:
        out.append(f"  ⑥ 코드 동결: 재현 통과 기록을 읽지 못함({e})")
        return out
    changes = _read_log(root, "changes.jsonl")
    rows = _window_fp_rows(states)
    tr = freeze_window(mk, rows, entries, changes)
    badt = [t for t in tr if not t["ok"]]
    line = f"  ⑥ 코드 동결: 창 안 코드·환경 지문 변경 {len(tr)}번"
    if tr:
        line += f"(허용 {len(tr) - len(badt)} · **위반 {len(badt)}**)" if badt else " (모두 ⑥ 허용)"
    for t in badt[:3]:
        line += f" · {t['date']}: {'; '.join(t['why'][:2])}"
    ch, env = code_hash()[0], env_info()
    last = (rows[-1].get("code_hash"), _env_dict(rows[-1].get("env")))
    if (ch, env_key(env)) == (last[0], env_key(last[1])):
        line += " · 지금 코드·환경 = 마지막 봉과 같음"
    else:
        r2 = freeze_transition(mk, last, (ch, env), entries, changes)
        line += (" · 지금 코드·환경이 마지막 봉과 다름: " + ("⑥ 허용 " + ", ".join(r2["kinds"]) if r2["ok"]
                                                       else f"**⑥ 허용 안 됨** → 다음 run 은 종료 코드 3 ({'; '.join(r2['why'][:2])})"))
    out.append(line)
    return out


def window_decision_keys(states, start=None, upto=None) -> set:
    """이 창이 실제로 쓴 판정 기록 열쇠 = 두 장부 하루 기록(start ~ upto)의 팀장 칸(leader)에 적힌 열쇠.
    보고서 ⑧ 폴백 비율의 분모(h1_report._window_keys)가 쓴다 — status·실행 끝 요약의 '팀장 LLM / 폴백' 도 window_counts 를
    거쳐 같은 것을 쓴다(설계 §10.2e '폴백 비율 분모')."""
    return {e.get("key") for arm in ARMS for tn in TRAINERS for r in states[arm][tn]["days"]
            if (start is None or r["date"] >= start) and (upto is None or r["date"] <= upto)
            for e in r.get("leader") or [] if e.get("key")}


def summary_lines(market, states, *, errors=None, data_stops=None, counts=None) -> list:
    """두 장부 요약(설계 §3.3 요약 예 모양). errors·data_stops 는 일지에서 센 값(모르면 '?').
    counts(window_counts 결과)를 주면 판정 창 크기(meta.rules)·늦은 봉·거짓 양성 수·팀장 LLM/폴백 수(보고서 ⑧ 과 같은 분모)도
    거기서 쓴다(status·실행 끝 요약은 늘 counts 를 준다). 없으면 판정 창은 코드 상수, 팀장 수는 '?'. 지수 단위는 소수 6자리."""
    mk = _mkey(market)
    m = main.mkt(mk)
    idle = idle_code(mk)
    st0 = states["A0"][TRAINERS[0]]
    days = st0["days"]
    if not days:
        return [f"[H1 {mk}] 아직 처리한 봉이 없어요"]
    S, last = st0["start_date"], days[-1]["date"]
    n = len(days)
    start_total = sum(states["A0"][tn]["start_cash"] for tn in TRAINERS)

    def total(arm):
        return sum(states[arm][tn]["days"][-1]["value"] for tn in TRAINERS)

    def pct(v):
        return f"{(v / start_total - 1) * 100:+.2f}%"

    v0, v1 = total("A0"), total("A1")
    units = 0.0
    for tn in TRAINERS:
        w = _plain_wallet(states["A1"][tn]["wallet"])
        h = w["holdings"].get(idle)
        if h is not None:
            units += float(h.shares if isinstance(h, Holding) else h["shares"])
    if n >= 2:
        q = days[1]["idle_open"]
        bh_units = start_total / (q * (1 + m.slippage) * (1 + m.fee_rate))
        bh = f"{(bh_units * days[-1]['idle_close'] / start_total - 1) * 100:+.2f}%"
    else:
        bh = "아직 없음(S+1 시가에 시작)"
    wb = counts["window_bars"] if counts is not None else WINDOW_BARS
    cut = days[min(n, wb) - 1]["date"]                           # 판정 창 끝(S+62, 덜 찼으면 마지막 봉)
    late = len(counts["late"]) if counts is not None else sum(1 for r in days if r["late"] and r["date"] <= cut)
    n_llm = n_fb = None
    if counts is not None and counts.get("leader_n") is not None:
        n_fb = counts["leader_fallback"]
        n_llm = counts["leader_n"] - n_fb
    fp = counts.get("l_false_positive") if counts is not None else None
    firsts = []
    for arm in ARMS:
        for tn in TRAINERS:
            for r in states[arm][tn]["days"]:
                if any(e.get("kind") == "shadow_breaker" and e.get("first") for e in r.get("events") or []):
                    firsts.append(f"{arm}/{tn} {r['date']}")
    q = lambda v: "?" if v is None else str(v)   # noqa: E731
    window = f"{min(n, wb)}/{wb}" + (f" (+연장 {n - wb})" if n > wb else "")
    return [
        f"[H1 {mk}] 기준 봉 {last} · 시작 {S} · 판정 창 {window}",
        f"  A0 쉬는 돈=현금  {main.fmt(m, start_total, False)} → {main.fmt(m, v0, False)} ({pct(v0)})",
        f"  A1 쉬는 돈={idle:<5} {main.fmt(m, start_total, False)} → {main.fmt(m, v1, False)} ({pct(v1)})"
        f" · {idle} {fmt_units(units)}단위",
        f"  A1−A0 {main.fmt(m, v1 - v0)} · {idle} 들고 있기(S+1 시가 시작, 소수 단위) {bh}",
        f"  점검 L {q(errors)}" + (f" (④ 거짓 양성 {fp}건 뺌)" if fp else "")
        + f" · 자료 멈춤 {q(data_stops)} · 늦은 봉 {late} · 팀장 LLM {q(n_llm)} / 폴백 {q(n_fb)} · "
        f"그림자 서킷 {', '.join(firsts) if firsts else '없음'}",
        "  ※ 3개월은 판단하기에 너무 짧다 — 숫자는 기록용(사전 등록). A0 는 운영 장부가 아니다",
    ]


# ============================ 명령줄 (cli) ============================

class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """argparse 기본 오류 종료 코드 2 는 '장부 논리 오류'와 겹쳐서, 인자 오류는 1 로 돌려준다."""

    def error(self, message):
        raise _UsageError(message)


def _parser():
    p = _Parser(prog="h1.py", description="H1 포워드 모의매매 실행기 (진짜 돈·진짜 주문 없음, 장부만). "
                                          "종료 코드: " + " / ".join(f"{k} {v}" for k, v in EXIT_TEXT.items()))
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    for name, helptext in (("start", "새 판정 창 시작(S 는 입금만)"), ("run", "매일 실행(새 확정 봉 처리)"),
                           ("restart", "시장 폴더를 보관하고 재시작 기록"),
                           ("corp-action", "분할·상장폐지(등록·취소)·정정 확정"),
                           ("amend-rules", "국내 매도세 표 줄 추가 반영"), ("status", "상태 보기")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--market", required=True, choices=("us", "kr"))
        if name == "restart":
            sp.add_argument("--confirm", required=True, help="같은 시장을 한 번 더(예: --market kr --confirm kr)")
            sp.add_argument("--reason", required=True, choices=tuple(RESTART_REASONS),
                            help="사유 코드: " + " / ".join(f"{k} = {v}" for k, v in RESTART_REASONS.items()))
            sp.add_argument("--note", default=None, help="사람이 적는 설명(restarts.jsonl 에 같이 남음)")
        if name == "corp-action":
            sp.add_argument("--code", required=True)
            sp.add_argument("--split", default=None,
                            help="비율 r = 새 주식 수 ÷ 옛 주식 수. 예: 2, 0.5, 1/3, 3:1(새 3 : 옛 1 → r=3)")
            sp.add_argument("--date", default=None,
                            help="분할 효력일 YYYY-MM-DD = 새 주식 수로 거래되는 첫 날(변경상장일·ex-date). "
                                 "신주배정 기준일이 아님. 장부 마지막 처리 봉보다 뒤여야 함")
            sp.add_argument("--delist", action="store_true",
                            help="상장폐지 등록(--confirm <같은 코드> 필요, 지금 시세에 --last-date 뒤 거래가 없어야 함)")
            sp.add_argument("--cancel-delist", action="store_true",
                            help="아직 정리하지 않은 상장폐지 등록 취소(--confirm <같은 코드> 필요)")
            sp.add_argument("--confirm", default=None, help="--delist·--cancel-delist 때 같은 종목코드를 한 번 더")
            sp.add_argument("--last-date", default=None, help="상장폐지 마지막 거래일 YYYY-MM-DD")
            sp.add_argument("--last-close", type=float, default=None, help="마지막 거래 종가(비우면 장부 marks)")
            sp.add_argument("--accept-correction", action="store_true")
            sp.add_argument("--source", required=True, help="1차 출처(거래소 공시·회사 발표 주소)")
        if name == "amend-rules":
            sp.add_argument("--source", required=True, help="법령 1차 출처")
    return p


def cli(argv=None) -> int:
    """python h1.py start|run|restart|corp-action|amend-rules|status --market us|kr … → 종료 코드(설계 §3.9 + 9·130).
    모든 예외를 잡는다: 인자 오류 9, 거절 그 코드, Ctrl-C 130, 환경 문제(OSError·MemoryError) 4, 그 밖(코드 버그) 2.
    1 은 h1.py 가 직접 돌려주지 않는다(파이썬이 여기 닿기 전에 죽음 = import 실패 등)."""
    try:
        a = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    except _UsageError as e:
        _say(f"h1.py: 명령 인자 오류 — {e}  (python h1.py -h 로 사용법)")
        return EXIT_USAGE
    try:
        if a.cmd == "start":
            return start(a.market)
        if a.cmd == "run":
            return run(a.market)
        if a.cmd == "restart":
            restart(a.market, a.reason, confirm=a.confirm, note=a.note)
            return EXIT_OK
        if a.cmd == "corp-action":
            return corp_action(a.market, a.code, split=a.split, date=a.date, delist=a.delist, last_date=a.last_date,
                               last_close=a.last_close, accept_correction=a.accept_correction, source=a.source,
                               confirm=a.confirm, cancel_delist=a.cancel_delist)
        if a.cmd == "amend-rules":
            return amend_rules(a.market, a.source)
        if a.cmd == "status":
            lines = status(a.market)
            for line in lines:
                _say(line)
            return EXIT_OK if market_dir(a.market).is_dir() else EXIT_NO_LEDGER
    except H1Refused as e:
        return e.code
    except KeyboardInterrupt:
        _say("h1.py: 사람이 멈춤(Ctrl-C)")
        return EXIT_INTERRUPT
    except (OSError, MemoryError) as e:          # 잠금 파일·폴더를 만들지 못함 등(일지보다 앞에서 난 환경 문제)
        _say(f"h1.py: 환경 문제(ENV) {type(e).__name__}: {e} — 디스크 공간·권한 확인")
        return EXIT_DATA
    except Exception as e:                       # 코드 버그(일지에는 명령이 이미 남김)
        _say(f"h1.py: 예상 밖 오류 {type(e).__name__}: {e}")
        return EXIT_LOGIC
    return EXIT_USAGE


if __name__ == "__main__":
    # `python h1.py …` 로 돌 때 이 파일은 __main__ 이고, h1_check 가 `import h1` 로 같은 파일을 한 번 더 읽는다.
    # 예외 클래스·설정이 두 벌이 되지 않게 명령은 import 한 h1 모듈 쪽에서 돈다.
    import h1 as _h1
    sys.exit(_h1.cli())
