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
- 상수(§3.3), 예외 3종, idle_code·kr_sell_tax·rule_constants·next_open·ledger_fingerprint·decision_key·env_key
- IdleBar(대기 자산 그날 시가·종가), StrictFrames(없는 종목을 찾으면 바로 오류인 시세 묶음), Fetched(받은 시세 모양)
- DecisionLog: 팀장 판정 기록(추가만 하는 JSONL, 줄마다 fsync)
- Leader: 판정 기록을 거쳐 팀장(claude)에게 묻는 창구(기록에 없는 후보만, 묻기 직전마다 시각 재확인)
- 새 장부 만들기·장부 ↔ JSON dict 바꾸기(엄격)
- H1Day: team.run_trainer(h1=…) 에 넘기는 하루 처리기(시가 체결 a~e, 팀장 결과 버퍼, 종가 기록)
- run_bar: 봉 하나를 장부 6개(A0·A1 × 트레이너 3명)에 처리하고 h1_check 로 점검한 결과를 돌려준다

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
    - 없는 종목을 꺼내면 H1LogicError (그날 받아 둔 종목만 쓴다)."""

    def __contains__(self, key):
        return True

    def __missing__(self, key):
        raise H1LogicError(f"엄격 시세 묶음에 없는 종목 {key!r} 을 찾았어요(받아 둔 종목만 쓸 수 있음)")


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
    - 마지막 줄만 반쯤 쓰임(줄바꿈으로 끝나지 않음 = 쓰는 중 꺼짐) → 그 부분을 파일에서 잘라 내고
      self.truncated 에 {"bytes", "preview"} 로 남긴다(2b-2 가 runs.jsonl 에 적음). 그 줄은 아직 어느 장부에도 안 쓰였다.
    append(records): 줄마다 쓰기 + fsync. 이미 있는 열쇠면 H1LogicError(L18) — 아무것도 쓰지 않는다.
    prefix_digest(n): (줄 수, 앞 n 줄 sha256). HEAD 에 적어 두고 다음 실행에서 지난 줄이 바뀌었는지 본다(L18)."""

    def __init__(self, path):
        self.path = Path(path)
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
            keep = len(data) - len(tail)
            with open(self.path, "r+b") as f:
                f.truncate(keep)
                f.flush()
                os.fsync(f.fileno())
            self.truncated = {"bytes": len(tail), "preview": tail[:200].decode("utf-8", "replace")}

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
                "conviction": team.to_conviction(item.get("conviction")) if item is not None else None,
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


def ledger_from_json(d, market, arm=None, trainer=None) -> dict:
    """JSON dict → 메모리 장부(엄격). schema·칸·모양이 틀리면 H1LogicError(code="L24") — 새 지갑으로 덮지 않는다.
    보유는 Holding(**v) 로 그대로 만든다 → 정수 주식은 int 그대로, 지수 단위는 float 비트 그대로."""
    mk = _mkey(market)
    if not isinstance(d, dict):
        _bad("장부가 dict 가 아님")
    if set(d) != set(LEDGER_KEYS):
        _bad(f"장부 칸이 다름: 빠짐 {sorted(set(LEDGER_KEYS) - set(d))} / 남음 {sorted(set(d) - set(LEDGER_KEYS))}")
    if d["schema"] != SCHEMA[mk]:
        _bad(f"장부 형식 {d['schema']!r} ≠ {SCHEMA[mk]!r}")
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
    for k in ("positions",):
        if not isinstance(d[k], dict):
            _bad(f"{k} 가 dict 가 아님")
    for k in ("pending", "orders", "fills", "skips", "corp_actions", "days"):
        if not isinstance(d[k], list):
            _bad(f"{k} 가 목록이 아님")
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


# ============================ 하루 처리기 (H1Day) ============================

class H1Day:
    """team.run_trainer(h1=…) 에 넘기는 하루 처리기. 장부(arm) 하나에 하나, 트레이너 셋이 같이 쓴다.

    속성(설계 §3.3): market, arm, idle(IdleBar), leader(판정 기록 팀장 — 부르면 Leader 를 부르고 late_calls 를 셈),
    late(봉 시작 때 늦었나), mode, start_date(S), halted(그날 정지 종목), delist({code: {last_date, last_close}}),
    code_hash, env, screened({트레이너: 스크리너 후보 목록}), prev_cal_date(달력의 바로 앞 거래일), run_at.

    fill: 시가 단계 a~e (아래 docstring). note_leader: 팀장 결과를 버퍼에만. close_day: marks·평가·그림자 서킷·
    새 주문·팀장 결과(skips·leader·over_slots)·하루 기록 1줄."""

    def __init__(self, market, arm, idle: IdleBar, leader, *, start_date, prev_cal_date=None, mode="llm",
                 late=False, halted=frozenset(), delist=None, code_hash="", env=None, screened=None, run_at=None):
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
        self._leader_buf = {}
        self._late_calls = {}

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

    def _sell(self, st, code, kind, px, qty, t, tax_rate, *, purpose, order_id=None, need=None, short=None):
        w = st["wallet"]
        cb, ub = w.cash, self._units(w)
        if not w.sell(code, px, qty, t, tax_rate=tax_rate):
            raise H1LogicError(f"{w.name} {code} 매도 실패 qty={qty!r}", code="L2")
        exec_price = px * (1 - w.slippage)          # PaperWallet.sell 과 같은 계산 순서
        proceeds = exec_price * qty
        fee = proceeds * w.fee_rate
        tax = proceeds * tax_rate
        self._fill_row(st, t=t, code=code, kind=kind, side="sell", qty=qty, price=px, exec_price=exec_price,
                       fee=fee, slip_cost=qty * px * w.slippage, tax=tax, cash_delta=proceeds - fee - tax,
                       cash_before=cb, units_before=ub, purpose=purpose, order_id=order_id, need=need, short=short)

    def _sweep(self, st, t, purpose) -> bool:
        """남은 현금을 전부 지수로(소수 단위, 남는 돈 < 1) — R2 _sweep_to_index 그대로.
        현금 < SWEEP_MIN 이면 아무것도 안 함. 줄임 1e-12 → 1e-9 → 1e-6 중 처음 성공하는 값. 셋 다 실패면 오류."""
        w = st["wallet"]
        if w.cash < SWEEP_MIN:
            return False
        px = self.idle.open
        unit = px * (1 + w.slippage) * (1 + w.fee_rate)
        for shrink in SWEEP_SHRINK:
            u = w.cash / unit * (1 - shrink)
            if self._buy(st, self.idle.code, "idle", px, u, t, purpose=purpose):
                return True
        raise H1LogicError(f"{w.name}: 지수 매수 실패(쓸어 담기, 현금 {w.cash!r})", code="L11")

    def _skip(self, st, t, code, kind, why, *, need=None, avail=None, order_id=None, price=None):
        st["wallet"].skip(code, why, t)               # team.py·R2 처럼 지갑 기록에도 '보류'
        st["skips"].append({"date": t, "code": code, "kind": kind, "reason": why, "need": need, "avail": avail,
                            "order_id": order_id, "price": price})

    # ---------------- 시가 (G1) ----------------

    def fill(self, st, tname, cap, bar_date, cache, m, logs) -> bool:
        """봉 t 시가 단계 (설계 §2.3 a~e, A0/A1 차이 표). 무엇인가 했으면 True.
        t = S 이면 아무것도 안 한다(입금만, §2.5).
        a  (A1, S+1) 현금 전부 지수(purpose="start")
        a′ (--delist 등록 종목, last_date 뒤 첫 처리 봉) 두 장부 모두 등록 가격으로 전량 정리, 대기 주문 dropped
        b  대기 주문 나누기: t 확정 행이 있고 시가가 있으면 오늘 체결, 정지(halted)면 그대로 둠, 그 밖은 자료 문제(D3)
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
                raise H1LogicError(f"{tname}: 주문 {rec['id']} 은 이미 {rec['status']}", code="L14")
            rec["status"], rec["done_date"], rec["why"] = status, t, why

        # a. A1 첫날(S+1): 주문보다 먼저 현금 전부 지수
        if is_a1 and st["last_date"] == st["start_date"]:
            if self._units(w) != 0.0 or st["fills"]:
                raise H1LogicError(f"{tname}: S+1 인데 이미 지수·체결이 있음", code="L10")
            if not self._sweep(st, t, "start"):
                raise H1LogicError(f"{tname}: S+1 첫 전부 지수를 하지 못함(현금 {w.cash!r})", code="L10")
            logs.append(f"지수 매수 {self.idle.code} {fmt_units(self._units(w))}단위(첫날 전부)")
            changed = True

        # a′. 상장폐지 정리 (§2.2 ⑦-4)
        for code in sorted(self.delist):
            reg = self.delist[code]
            if t <= reg["last_date"]:
                continue
            if code in positions:
                pos = positions.pop(code)
                px = float(reg["last_close"])
                self._sell(st, code, "stock", px, pos["shares"], t, stock_sell_tax(self.market, t), purpose="delist")
                logs.append(f"상장폐지 정리 {code}@{px}")
                changed = True
            keep = []
            for o in st["pending"]:
                if o["code"] == code:
                    rec = by_id.get(order_id(o))
                    if rec is None:
                        raise H1LogicError(f"{tname}: 대기 주문 {order_id(o)} 의 주문 기록이 없음", code="L14")
                    finish(rec, "dropped", "delist")
                    changed = True
                else:
                    keep.append(o)
            st["pending"] = keep

        # b. 대기 주문 나누기
        todo, still = [], []
        for o in st["pending"]:
            rec = by_id.get(order_id(o))
            if rec is None or rec["status"] != "pending":
                raise H1LogicError(f"{tname}: 대기 주문 {order_id(o)} 의 주문 기록이 없거나 pending 이 아님", code="L14")
            code = o["code"]
            if code in self.halted:
                still.append(o)                        # 정지 중: 다음 거래된 봉 시가로 (STAGE0 A5)
                continue
            df = cache[code]
            if df is None:
                raise H1DataProblem("D2", f"대기 주문 종목 {code} 시세 없음")
            row = _row_at(df, t)
            px = main.open_price(row) if row is not None else None
            if px is None:
                raise H1DataProblem("D3", f"대기 주문 종목 {code} 의 {t} 확정 행·시가 없음")
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
            pos = positions.pop(code)
            self._sell(st, code, "stock", px, pos["shares"], t, stock_sell_tax(self.market, t),
                       purpose="order", order_id=rec["id"])
            finish(rec, "filled")
            logs.append(f"매도 {code}{team._at(m, px)}({o.get('reason', '')})")

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
            if short_of_cash:                          # A1 은 지수를 팔지 않고 보류 (R2 I2·R6)
                why = f"현금 부족 (필요 {main.fmt(m, px * n, False)}, 보유 {main.fmt(m, avail, False)})"
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
                        self._sell(st, self.idle.code, "idle", self.idle.open, u, t, 0.0,
                                   purpose=f"fund:{code}", need=need, short=short)
                        sold_idle = True
                        logs.append(f"지수 매도 {self.idle.code} {fmt_units(u)}단위({code} 자금)")
                else:
                    short = 0.0
            if not self._buy(st, code, "stock", px, n, t, purpose="order", order_id=rec["id"], need=need,
                             short=short):
                if sold_idle:
                    raise H1LogicError(f"{tname}: 지수를 판 뒤 {code} 매수 실패(일어날 수 없게 만든 길)", code="L11")
                raise H1LogicError(f"{tname}: 필요 금액 ≤ 현금인데 {code} 매수 실패", code="L12")
            positions[code] = {"buy_price": px, "days_held": 0, "shares": n, "buy_date": t}
            finish(rec, "filled")
            tip = f" 팀장:{o['note']}" if o.get("note") else ""
            logs.append(f"매수 {code}x{n}{team._at(m, px)}{tip}")

        # e. A1 쓸어 담기 (매도 대금·남은 돈 → 지수)
        if is_a1 and self._sweep(st, t, "sweep"):
            logs.append(f"지수 매수 {self.idle.code} → 보유 {fmt_units(self._units(w))}단위(쓸어 담기)")
            changed = True
        return changed

    # ---------------- 팀장 결과 (G4) ----------------

    def note_leader(self, st, tname, bar_date, cands0, analysis, kept, slots) -> None:
        """team ④ 가 주문을 다 낸 뒤 부른다. 장부는 고치지 않고 트레이너별 버퍼에만 담는다(close_day 가 씀)."""
        self._leader_buf[tname] = {"date": bar_date, "cands0": [dict(c) for c in cands0],
                                   "analysis": analysis, "kept": [dict(c) for c in kept], "slots": slots}

    def _leader_effects(self, tname, bar_date, buf):
        """team ④ 와 같은 규칙으로 후보마다 효과를 다시 정한다: veto·hold·low_conv·ordered·over_slots."""
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
            raise H1LogicError(f"{tname}: 팀장 효과를 다시 계산한 결과가 team ④ 와 다름 {mine} vs {kept_codes}",
                               code="L19")
        rank = {code: i for i, code in enumerate(kept_codes)}
        for r in rows:
            if r["effect"] == "kept":
                r["effect"] = "ordered" if rank[r["code"]] < n_slots else "over_slots"
        over = max(0, len(kept_codes) - n_slots)
        return rows, skips, over

    # ---------------- 종가 (G5) ----------------

    def close_day(self, st, tname, bar_date, prices, value) -> None:
        """종가 단계 i: 평가 확인·marks·그림자 서킷·새 주문 기록·팀장 결과·하루 기록 1줄."""
        t = bar_date
        w = st["wallet"]
        missing = [c for c in w.holdings if c not in prices]
        if missing:                                   # R14: 가격표에 없으면 평균 매입가로 평가돼 조용히 틀림
            raise H1LogicError(f"{tname}: 평가 가격표에 보유 종목 {missing} 이 없음", code="L7")
        if prices.get(self.idle.code) != self.idle.close:
            raise H1LogicError(f"{tname}: 가격표의 대기 자산 종가가 IdleBar 와 다름", code="L7")
        positions = st["positions"]
        if set(positions) - set(w.holdings):
            raise H1LogicError(f"{tname}: 지갑 보유에 없는 positions {sorted(set(positions) - set(w.holdings))}",
                               code="L2")
        marks = {c: prices[c] for c in positions}
        stock_value = sum(w.holdings[c].shares * marks[c] for c in positions)
        units = self._units(w)
        idle_value = units * self.idle.close
        total = w.cash + stock_value + idle_value
        if abs(total - value) > h1_check.EPS_REL * max(1.0, abs(total), abs(value)):
            raise H1LogicError(f"{tname}: 평가액 불일치 {total!r} vs wallet.value {value!r}", code="L7")

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
                    raise H1LogicError(f"{tname}: 끝난 주문과 같은 id 의 새 주문 {oid}", code="L5")
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
                raise H1LogicError(f"{tname}: 팀장 버퍼 날짜 {buf['date']} ≠ {t}", code="L19")
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
    """run_bar 결과. ok 가 False 면(L 오류) 그 봉은 저장하지 않는다(종료 코드 2)."""
    date: str
    states: dict                 # 처리 뒤 장부 6개 {arm: {trainer: st}} (입력 장부는 그대로 둠)
    problems: list               # h1_check.Problem (L 오류 + W 경고)
    lines: list                  # team.run_trainer 가 돌려준 사람용 한 줄들 ("A0 마라토너: …")
    found: dict                  # 스크리너 결과 {트레이너: [후보]}
    used: int
    mode: str                    # "llm" | "late" | "replay"
    late: bool
    llm_calls: int
    late_calls: int
    new_records: list            # 이번 봉에서 판정 기록에 더한 줄
    fingerprint: str             # 처리 뒤 장부 6개의 내용 지문

    @property
    def errors(self):
        return h1_check.errors(self.problems)

    @property
    def ok(self):
        return not self.errors


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
      decisions  DecisionLog (판정 기록, 여기서 줄이 더해질 수 있음)
      leader_mode "llm"(운영) | "replay"(재현: LLM 안 부름). "llm" 이면 now() < next_open(t) 일 때만 llm, 아니면 late
      halted     t 에 거래정지인 종목(국내: 원본에 t 행이 있고 거래량 0). 정지 종목은 t 확정 행이 없어야 한다
      delist     {code: {"last_date", "last_close"}} — corp-action --delist 로 등록한 종목(D2·D3 대상 아님)
      prev_cal_date 달력에서 t 바로 앞 거래일(S 면 S 전 거래일). t > S 이면 장부 last_date 와 같아야 한다
      calendar   L16 점검용 달력 날짜 목록(calendar.jsonl 마지막 줄, S 전 거래일 ~ t). None 이면 달력 비교 생략
      now, ask, cli_version  Leader 에 넘김(시계·LLM 함수·claude 버전)
      code_hash, env  하루 기록에 적을 코드 지문·환경. allowed = L22 허용 {(code_hash, env_key(env))}(None 이면 생략)
      head       L18 점검용 HEAD 의 (판정 기록 줄 수, 앞부분 sha256). None 이면 생략
      universe_sha256 / meta_universe_sha256  L22 종목군 파일 지문 비교(둘 다 있을 때)
      brains     screener.scan_frames 의 brains (None = screener.BRAINS. 재현 W3 의 가짜 브레인용)

    순서: 장부·자료 확인(D3 일부) → 스크리너 한 번(두 장부 공유) → 팀장 방식 → 트레이너마다(마라토너→스프린터→파이오니어)
          A0→A1 순서로 team.run_trainer(breaker=CircuitBreaker(inf, inf), cache=엄격 cache, h1=H1Day) → h1_check.check_day.
    돌려줌: BarResult. result.ok 가 False(L 오류)면 저장하지 말 것.
    예외: H1LogicError(장부 논리 오류, 종료 코드 2 — 저장 안 함), H1DataProblem(D2·D3, 종료 코드 4 — 저장 안 함)."""
    mk = _mkey(market)
    _check_iso(t, "t")
    if leader_mode not in ("llm", "replay"):
        raise ValueError(f"leader_mode 는 'llm' 또는 'replay' (받은 값 {leader_mode!r})")
    for arm in ARMS:
        if arm not in states or any(tn not in states[arm] for tn in TRAINERS):
            raise H1LogicError(f"장부 6개가 다 있어야 해요({arm})", code="L16")
    flat = [states[a][tn] for a in ARMS for tn in TRAINERS]
    starts = {st["start_date"] for st in flat}
    lasts = {st["last_date"] for st in flat}
    if len(starts) != 1:
        raise H1LogicError(f"여섯 장부의 시작일이 다름 {sorted(starts)}", code="L16")
    if len(lasts) != 1:
        raise H1LogicError(f"여섯 장부의 last_date 가 다름 {sorted(map(str, lasts))}", code="L16")
    S, last = starts.pop(), lasts.pop()
    if last is None:
        if t != S:
            raise H1LogicError(f"처음 처리하는 봉은 S({S}) 여야 해요 (받은 t {t})", code="L16")
    else:
        if t <= last:
            raise H1LogicError(f"봉 {t} 는 이미 처리됨(last_date {last})", code="L16")
        if prev_cal_date != last:
            raise H1LogicError(f"달력의 앞 거래일 {prev_cal_date} ≠ 장부 last_date {last} (빠진 봉?)", code="L16")
    if idle.code != idle_code(mk) or idle.date != t:
        raise H1LogicError(f"대기 자산 봉이 다름 ({idle.code} {idle.date}, 기대 {idle_code(mk)} {t})", code="L3")
    for v in (idle.open, idle.close):
        if not (_isnum(v) and math.isfinite(v) and v > 0):
            raise H1DataProblem("D1", f"대기 자산 {idle.code} {t} 시가·종가가 이상함 ({idle.open!r}, {idle.close!r})")
    halted = frozenset(halted)
    delist = {c: dict(v) for c, v in (delist or {}).items()}

    # 엄격 cache (t 이하)
    cut = {code: cut_frame(df, t) for code, df in frames.items()}
    strict = StrictFrames(cut)

    # 자료 준비 확인 (D3 의 장부 쪽: 보유·대기 종목은 t 확정 행, 대기 주문 종목은 시가까지)
    for st in flat:
        pend = {o["code"] for o in st["pending"]}
        for code in (set(st["positions"]) | pend) - set(delist):
            if code not in cut or cut[code] is None:
                raise H1DataProblem("D2", f"보유·대기 종목 {code} 시세 없음")
            row = _row_at(cut[code], t)
            if code in halted:
                if row is not None:
                    raise H1LogicError(f"{code}: 정지 목록에 있는데 {t} 확정 행이 있음", code="L6")
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
    before = clone_states(states, mk)
    after = clone_states(states, mk)
    days = {arm: H1Day(mk, arm, idle, leader, start_date=S, prev_cal_date=prev_cal_date, mode=mode, late=late,
                       halted=halted, delist=delist, code_hash=code_hash, env=env, screened=found, run_at=run_at)
            for arm in ARMS}
    caps = main.CONFIG["종목상한"]
    lines = []
    for tname in TRAINERS:
        for arm in ARMS:
            st = after[arm][tname]
            line, st2 = team.run_trainer(tname, st["start_cash"], caps[tname], CircuitBreaker(*LEDGER_BREAKER),
                                         found.get(tname, []), t, st=st, cache=strict, mk=mk, h1=days[arm])
            if st2 is not st or not st["days"] or st["days"][-1]["date"] != t:
                raise H1LogicError(f"{arm}/{tname}: 봉 {t} 하루 기록이 생기지 않음({line})", code="L16")
            if st["stopped"]:
                raise H1LogicError(f"{arm}/{tname}: 장부 서킷이 걸림(끈 서킷이어야 함)", code="L2")
            lines.append(f"{arm} {line}")

    # 4. 점검
    problems = h1_check.check_day(mk, t, before, after, cut, idle, calendar, halted, decisions, allowed,
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
                     fingerprint=ledger_fingerprint(after))
