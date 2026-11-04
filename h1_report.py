"""
h1_report.py - H1 포워드 월간·최종 보고서 (설계 docs/h1-forward-design.md 3판 §3.8, F8, 단계 2c)
------------------------------------------------------------------
무엇을 하나 (주식 초보용 설명)
- H1 장부 두 개(A1 = 쉬는 돈을 지수에, A0 = 쉬는 돈을 현금에)가 그동안 어떻게 굴러갔는지 한 장으로 정리한다.
- **저장된 파일만** 읽는다: 장부 6개(HEAD.json 으로 엄격하게)·meta.json·HEAD.json·calendar.jsonl·판정 기록·
  runs/errors/restarts/changes.jsonl·금리 저장본. 시세는 다시 받지 않는다(하루 기록에 지수 시가·종가와 보유 종목 종가가 있음).
- 수익률·MDD·A1−A0 같은 숫자는 **기록만** 한다. 판정에 쓰지 않는다(사전 등록 ③⑨).
- `--final` 은 판정 창(S~S+62)을 다 처리한 뒤 운영 기준 ①~③ 의 통과/실패만 판정한다.
- 장부·일지는 한 글자도 고치지 않는다. 쓰는 것은 보고서 파일(state/h1/reports/)과 금리 저장본(state/h1/rates/)뿐이다.
  같은 입력이면 같은 보고서(바이트까지)가 나온다 — 그래서 "만든 시각"은 넣지 않고, 기준은 HEAD(마지막 저장)로 적는다.

명령
  python h1_report.py --market us|kr [--month YYYY-MM] [--final] [--offline]
      → state/h1/reports/<market>-<YYYY-MM>.md  (--final 이면 <market>-final-<S>.md, 같은 이름이면 덮어씀)
      인터넷이 되면 먼저 FRED 금리를 받아 저장본을 새로 한다(--offline 이면 받지 않음).
  python h1_report.py --fetch-rates [--market us|kr]      FRED 금리만 받아 state/h1/rates/ 에 저장
  종료 코드: 0 정상 / 2 예상 밖(장부 파일 손상 L24 포함) / 4 금리 받기 실패(--fetch-rates) / 5 잠금 30분 초과 /
            8 장부 없음 / 9 명령 인자 오류(없는 달 등)

함수(설계 §3.8)
  build(market, month=None, final=False, root=None, online=True) -> str     보고서 마크다운
  write(market, month=None, final=False, root=None, online=True) -> Path    파일로 저장
  collect(...) -> dict                                                       보고서 숫자 묶음(시험·재현용)
  fetch_rates(series_id, cache_dir, timeout=20) -> Path | None              FRED 받기(표준 라이브러리 urllib)
  load_rates(series_id, cache_dir) -> pd.Series | None                     FRED 원본·R2 형식 둘 다, "." 은 빈값
  rate_for_days(dates, series, rule) -> list[float]                         R2 sim_team.rate_for_days 와 같은 규칙·같은 값
  interest_overlay(dates, cash, rate_pct) -> list[float]                    I_t = I_{t−1}·(1+q_t) + C_t·q_t
  realized(fills, corp_actions=None) -> dict                                 평균원가법 실현손익(주식/지수 따로)
  index_buy_hold_same_start(opens, closes, total, fee_rate, slippage) -> dict
      지수 B&H(같은 시작) — R2 index_buy_hold_fractional(md, i0+1, i1, total) 와 같은 식(재현 M6 이 쓴다)
  cli(argv=None) -> int

import 관계: h1_report → h1·h1_check·main·markets·metrics. h1 은 h1_report 를 import 하지 않는다.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import math
import re
import sys
import urllib.request
from collections import Counter
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import h1
import h1_check
import main
import markets
import metrics

# ============================ 상수 ============================

SERIES = {"us": "DTB3", "kr": "IR3TIB01KRM156N"}          # F8: 미국 3개월 T-bill(일별), 국내 3개월 은행간 금리(월별)
RULE = {"us": "prev_day", "kr": "prev_month"}             # STAGE0-A1 전 거래일 / STAGE0-A2 전달
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
R2_RATE_NAMES = {"DTB3": "us_tbill.csv", "IR3TIB01KRM156N": "kr_shortrate.csv"}   # R2 data/rates 의 파일 이름
DAYS_PER_YEAR = 252                                       # B4: 거래일마다 연% / 100 / 252

EXIT_OK = 0
EXIT_ERROR = 2          # 예상 밖 오류, 장부 파일 손상(L24)
EXIT_FETCH = 4          # --fetch-rates 에서 금리를 못 받음
EXIT_LOCK = 5
EXIT_NO_LEDGER = 8
EXIT_USAGE = 9

FIXED_RECORD_ONLY = ("수익률은 기록만 하고 판정하지 않는다(사전 등록 ③). 3개월은 판단하기에 너무 짧다 — "
                     "수익률·MDD·A1−A0·지수 대비·그림자 서킷·팀장 성적은 판정에도, 재시작 사유에도 쓰지 않는다.")
FIXED_A0 = ("A0 는 R2 A0 규칙의 그림자 장부이고 운영 team.py 장부가 아니다(설계 §1.1 표). "
            "이 숫자를 운영 state/team_*.json 과 견주면 안 된다.")
US_TAX_NOTE = "해외주식 양도세(연 250만 원 초과분) 인식용 참고값 — 달러 기준, 환율·신고 방식(선입선출 등) 미반영(미확인)"
OFFLINE_CHECKS = ("L3(주식 체결가 = 그날 그 종목 시가: 그날 시세 필요)",
                  "L6 의 '체결 종목에 그날 확정 행이 있음'(그날 시세 필요)",
                  "D1~D7 자료 점검 전부(시세·달력을 새로 받아야 함)")
NAME = {"us": "미국", "kr": "국내"}
ARM_WORD = {"A0": "쉬는 돈=현금(그림자)", "A1": "쉬는 돈=지수(H1)"}
SKIP_KINDS = ("0주", "현금부족", "팀장hold", "확신도낮음")
EFFECTS = ("veto", "hold", "low_conv", "ordered", "over_slots")
EFFECT_WORD = {"veto": "veto(빠짐)", "hold": "hold(보류)", "low_conv": "확신도 낮음(보류)", "ordered": "주문",
               "over_slots": "빈자리 부족"}
_FAR = "9999-12-31"


class ReportError(Exception):
    """보고서를 만들 수 없음. code = 종료 코드(8 장부 없음, 9 인자·없는 달, 2 장부 손상)."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ============================ 금리: 받기·읽기 ============================

def _iso_ok(d) -> bool:
    if not isinstance(d, str) or len(d) != 10:
        return False
    try:
        return _date.fromisoformat(d).isoformat() == d
    except ValueError:
        return False


def _parse_rates(text: str, series_id: str | None = None) -> tuple:
    """금리 CSV 글자 → ([(날짜, 연%)…] 날짜 오름차순, 형식).
    - FRED 원본: 머리 `observation_date,<ID>`(또는 옛 `DATE,<ID>`). 휴장일 값 "."(또는 빈칸)은 빈값 → 그 줄을 뺀다
      (STAGE0-A1 "그날 값이 없으면 직전 값" = 빼 두면 asof 가 직전 값을 고른다. R2 us_tbill.csv 도 "holidays dropped").
    - R2 형식: 머리 `date,rate_pct,source[,frequency]`.
    날짜가 이상하거나 같은 날짜에 다른 값이 두 번이면 ValueError."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("빈 파일")
    head = [h.strip().lstrip("﻿") for h in rows[0]]
    low = [h.lower() for h in head]
    if "date" in low and "rate_pct" in low:
        fmt, di, vi = "r2", low.index("date"), low.index("rate_pct")
    elif len(head) >= 2 and low[0] in ("observation_date", "date"):
        fmt, di, vi = "fred", 0, 1
        if series_id is not None and head[1] != series_id:
            raise ValueError(f"FRED 머리의 시리즈 {head[1]!r} ≠ {series_id!r}")
    else:
        raise ValueError(f"모르는 금리 파일 머리 {head!r}")
    got = {}
    for r in rows[1:]:
        if not r or all(not x.strip() for x in r):
            continue
        d = r[di].strip() if len(r) > di else ""
        v = r[vi].strip() if len(r) > vi else ""
        if not _iso_ok(d):
            raise ValueError(f"금리 날짜가 이상해요 {d!r}")
        if v in ("", "."):
            continue
        f = float(v)
        if not math.isfinite(f):
            raise ValueError(f"{d} 금리가 유한한 숫자가 아님 {v!r}")
        if d in got and got[d] != f:
            raise ValueError(f"{d} 금리가 두 번(값이 다름)")
        got[d] = f
    return sorted(got.items()), fmt


def _rate_paths(series_id, cache_dir) -> list:
    base = Path(cache_dir)
    out = [base / f"{series_id}.csv"]
    if series_id in R2_RATE_NAMES:
        out.append(base / R2_RATE_NAMES[series_id])      # 재현이 R2 data/rates 를 이름 그대로 복사해 둔 경우
    return out


def _sidecar(csv_path: Path) -> Path:
    return csv_path.with_suffix(".json")


def rates_info(series_id, cache_dir) -> dict:
    """금리 저장본 상태: {"ok", "series"(pd.Series|None), "path", "format", "first", "last", "rows", "fetched_at", "why"}.
    fetched_at 은 저장본 옆 <ID>.json 에 적힌 받은 시각(없으면 None — 예: R2 형식 복사본)."""
    for p in _rate_paths(series_id, cache_dir):
        if not p.is_file():
            continue
        try:
            items, fmt = _parse_rates(p.read_bytes().decode("utf-8-sig"), series_id)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            return {"ok": False, "series": None, "path": str(p), "why": f"저장본이 깨졌어요({type(e).__name__}: {e})"}
        if not items:
            return {"ok": False, "series": None, "path": str(p), "why": "저장본에 값이 하나도 없음"}
        meta = {}
        sp = _sidecar(p)
        if sp.is_file():
            try:
                meta = json.loads(sp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
        s = pd.Series([v for _, v in items], index=pd.DatetimeIndex([d for d, _ in items]), dtype=float)
        return {"ok": True, "series": s, "path": str(p), "file": p.name, "format": fmt, "first": items[0][0],
                "last": items[-1][0], "rows": len(items),
                "fetched_at": meta.get("fetched_at") if isinstance(meta, dict) else None,
                "source": meta.get("url") if isinstance(meta, dict) else None, "why": None}
    return {"ok": False, "series": None, "path": None, "why": "금리 저장본이 없음"}


def load_rates(series_id, cache_dir):
    """금리 저장본(state/h1/rates/<ID>.csv, 없으면 R2 이름 us_tbill.csv·kr_shortrate.csv)을 읽어 날짜 → 연% Series.
    FRED 원본·R2 형식 둘 다 읽고 "." 은 빈값(그 줄을 뺌). 없거나 깨졌으면 None."""
    return rates_info(series_id, cache_dir)["series"]


def store_rates(series_id, cache_dir, blob: bytes, fetched_at: str, url=None) -> Path:
    """금리 CSV 글자를 저장본으로(임시 파일 → 이름 바꿈) + 옆에 받은 시각 등 <ID>.json. 재현이 R2 파일로 첫 저장본을
    만들 때도 쓸 수 있다(fetched_at 에 'R2 data/rates (2026-11-04 수집)' 같은 글을 넣으면 됨)."""
    items, fmt = _parse_rates(blob.decode("utf-8-sig"), series_id)
    if not items:
        raise ValueError("값이 하나도 없는 금리 자료")
    base = Path(cache_dir)
    p = base / f"{series_id}.csv"
    h1._write_atomic(p, blob)
    side = {"series_id": series_id, "url": url, "fetched_at": fetched_at, "sha256": hashlib.sha256(blob).hexdigest(),
            "format": fmt, "rows": len(items), "first": items[0][0], "last": items[-1][0]}
    h1._write_atomic(_sidecar(p), (json.dumps(side, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return p


def fetch_rates(series_id, cache_dir, timeout=20, now=None):
    """FRED 에서 금리 CSV 를 받아 저장본으로(표준 라이브러리 urllib, API 키 없음, STAGE0 §2).
    실패(인터넷 없음·시간 초과·형식이 이상함)하면 None 이고 저장본은 그대로 둔다.
    새로 받은 자료의 마지막 날짜가 저장본보다 이르면(제공처가 줄여서 줌) 저장본을 지키고 None.
    now: 받은 시각을 주는 함수(시험용, 기본 이 컴퓨터 시각). 돌려줌: 저장한 CSV 경로."""
    url = FRED_URL.format(series_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "claude-stock-h1-report"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read()
        items, _ = _parse_rates(blob.decode("utf-8-sig"), series_id)
        if not items:
            return None
        old = rates_info(series_id, cache_dir)
        if old["ok"] and items[-1][0] < old["last"]:
            return None
        at = (now() if now is not None else datetime.now().astimezone()).isoformat(timespec="seconds")
        return store_rates(series_id, cache_dir, blob, at, url)
    except Exception:          # noqa: BLE001 — 받기 실패는 모두 "오프라인"으로 다룬다(보고서는 저장본으로 계속)
        return None


# ============================ 금리 규칙 · 이자 ============================

def _day(x) -> str:
    if isinstance(x, str):
        return x[:10]
    return pd.Timestamp(x).date().isoformat()


def _series_items(series) -> tuple:
    """Series(날짜 색인)·dict·(날짜, 값) 목록 → (날짜 글자 목록, 값 목록), 날짜 오름차순(같은 날짜는 들어온 순서)."""
    if series is None:
        return [], []
    if isinstance(series, pd.Series):
        pairs = [(_day(k), float(v)) for k, v in zip(series.index, series.to_numpy(float))]
    elif isinstance(series, dict):
        pairs = [(_day(k), float(v)) for k, v in series.items()]
    else:
        pairs = [(_day(k), float(v)) for k, v in series]
    pairs.sort(key=lambda kv: kv[0])
    return [d for d, _ in pairs], [v for _, v in pairs]


def _asof(sd, sv, key):
    """key 날짜 이하의 마지막 (날짜, 값). 없으면 (None, NaN) — R2 _asof(searchsorted side=right − 1) 와 같다."""
    i = bisect.bisect_right(sd, key) - 1
    return (sd[i], sv[i]) if i >= 0 else (None, math.nan)


def _first_of_prev_month(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y:04d}-{m:02d}-01"


def rate_keys(dates, rule) -> list:
    """날짜마다 금리를 찾을 기준 날짜. prev_day: 앞 날짜(첫날은 None) / prev_month: 그 전달 1일."""
    ds = [_day(d) for d in dates]
    if rule == "prev_day":
        return [None] + ds[:-1]
    if rule == "prev_month":
        return [_first_of_prev_month(d) for d in ds]
    raise ValueError(f"모르는 금리 규칙 {rule!r}")


def rate_match(dates, series, rule) -> list:
    """날짜마다 (기준 날짜, 쓴 금리 날짜, 연%) — 보고서의 '쓴 금리 날짜 표'. 값은 rate_for_days 와 같다."""
    sd, sv = _series_items(series)
    out = []
    for k in rate_keys(dates, rule):
        if k is None:
            out.append((None, None, math.nan))
        else:
            got, v = _asof(sd, sv, k)
            out.append((k, got, v))
    return out


def rate_for_days(dates, series, rule) -> list:
    """거래일마다 이자에 쓸 연 % 값 (R2 sim_team.rate_for_days 와 같은 규칙·같은 값, STAGE0-A1·A2).
    dates = 달력(오름차순, 'YYYY-MM-DD' 또는 날짜). series = 날짜 → 연% (load_rates 결과).
    - "prev_day"(미국 DTB3): i 번째 날 ← (i−1) 번째 날짜 이하의 마지막 값(그날 값이 없으면 직전 값).
      첫날은 앞 거래일이 없어 NaN → 보고서는 S 전 거래일(하루 기록 prev_cal_date)을 맨 앞에 붙여 부르고 첫 값을 버린다.
    - "prev_month"(국내 월별): m월의 날 ← m−1월 1일 이하의 마지막 값(없는 달은 그 전 값 이월).
    값이 하나도 없는 앞쪽 날은 NaN."""
    return [v for _, _, v in rate_match(dates, series, rule)]


def interest_overlay(dates, cash, rate_pct) -> list:
    """A0 현금 이자(계산만, 설계 §3.8-9): q_t = r_t/100/252, I_t = I_{t−1}·(1+q_t) + C_t·q_t (I 는 S 전날 0).
    dates·cash·rate_pct 는 같은 길이(C_t = 그날 종가 현금 합). 금리가 NaN·None 인 날은 0 으로 본다(R2 rate_missing 과 같음).
    돌려줌: 매일 누적 이자 I_t."""
    if not (len(dates) == len(cash) == len(rate_pct)):
        raise ValueError("dates·cash·rate_pct 길이가 다름")
    out, acc = [], 0.0
    for c, r in zip(cash, rate_pct):
        r = 0.0 if r is None or not math.isfinite(float(r)) else float(r)
        q = r / 100 / DAYS_PER_YEAR
        acc = acc * (1 + q) + float(c) * q
        out.append(acc)
    return out


# ============================ 실현손익 · 지수 B&H ============================

def realized(fills, corp_actions=None) -> dict:
    """평균원가법 실현손익(참고값, 보고서 안에서만 — 장부에는 칸이 없음, Q11).
    fills = 한 장부의 체결 기록(날짜 순). 주식("stock")과 지수("idle")를 따로 센다.
    - 취득가 = 산 돈(−cash_delta = 체결가(슬리피지 포함) × 수량 + 수수료). 팔 때 원가 = 평균 원가 × 판 수량.
    - 판 돈 = 받은 돈(cash_delta = 수수료·매도세를 뺀 뒤). 실현손익 = 판 돈 − 원가.
    - 분할(corp_actions 의 split): applied_after 날 뒤의 첫 체결 전에 수량 × r(원가 합은 그대로).
    돌려줌: {"stock": {...}, "idle": {...}, "sells": [{date, code, kind, qty, proceeds, cost, gain}], "open": {...}}
    kind 마다 {"total", "n_sells", "by_month": {YYYY-MM: 합}, "by_year": {YYYY: 합}, "by_code": {종목: 합}}."""
    splits = sorted((ca for ca in (corp_actions or []) if ca.get("kind") == "split"),
                    key=lambda ca: (ca.get("applied_after") or "", ca.get("code") or ""))
    pending = list(splits)
    pos = {}                     # code → {"kind", "qty", "cost"}
    sells = []

    def apply_splits(upto):
        while pending and (upto is None or (pending[0].get("applied_after") or "") < upto):
            ca = pending.pop(0)
            p = pos.get(ca["code"])
            if p is not None:
                p["qty"] = p["qty"] * float(ca["r"])

    for f in fills:
        apply_splits(f["date"])
        code, kind = f["code"], f["kind"]
        p = pos.setdefault(code, {"kind": kind, "qty": 0.0, "cost": 0.0})
        q = float(f["qty"])
        if f["side"] == "buy":
            p["qty"] += q
            p["cost"] += -float(f["cash_delta"])
            continue
        if p["qty"] <= 0:
            cost = 0.0
        elif q >= p["qty"] * (1 - 1e-12):          # 전부 판 것(지수 단위의 반올림 찌꺼기 포함)
            cost = p["cost"]
        else:
            cost = p["cost"] * (q / p["qty"])
        proceeds = float(f["cash_delta"])
        p["qty"] = max(0.0, p["qty"] - q)
        p["cost"] = p["cost"] - cost if p["qty"] > 0 else 0.0
        sells.append({"date": f["date"], "code": code, "kind": kind, "qty": q, "proceeds": proceeds, "cost": cost,
                      "gain": proceeds - cost})
    apply_splits(None)
    out = {"sells": sells, "open": {c: dict(p) for c, p in pos.items() if p["qty"] > 0}}
    for kind in ("stock", "idle"):
        mine = [s for s in sells if s["kind"] == kind]
        agg = {"total": sum(s["gain"] for s in mine), "n_sells": len(mine), "by_month": {}, "by_year": {},
               "by_code": {}}
        for s in mine:
            for key, k in (("by_month", s["date"][:7]), ("by_year", s["date"][:4]), ("by_code", s["code"])):
                agg[key][k] = agg[key].get(k, 0.0) + s["gain"]
        out[kind] = agg
    return out


def index_buy_hold_same_start(opens, closes, total, fee_rate, slippage) -> dict:
    """지수 B&H(같은 시작, 설계 §2.5): S 는 입금만, S+1 시가에 총액 전부를 지수 소수 단위로.
    opens·closes = S, S+1, … 의 지수 시가·종가. 단위 = 총액 ÷ (S+1 시가 × (1+slip) × (1+fee)) —
    R2 index_buy_hold_fractional(md, i0+1, i1, total) 와 같은 식·같은 계산 순서.
    돌려줌: {"values": [S 날 총액, 단위 × S+1 종가, …], "units"(S+1 전이면 None), "return", "mdd"}.
    R2 는 마지막 날에 매도 비용을 뺀 값을 넣지만 여기는 종가 평가 그대로다(재현 M6 은 마지막 날을 단위 × 종가로 비교)."""
    n = len(closes)
    if n == 0:
        return {"values": [], "units": None, "return": None, "mdd": None}
    if n == 1:
        values, units = [float(total)], None
    else:
        units = total / (opens[1] * (1 + slippage) * (1 + fee_rate))
        values = [float(total)] + [units * c for c in closes[1:]]
    return {"values": values, "units": units, "return": values[-1] / total - 1,
            "mdd": metrics.max_drawdown(values)}


# ============================ 읽기 ============================

class _Ctx:
    """한 시장의 저장 자료(읽기만)."""

    def __init__(self, mk, root, loaded, decisions, cal_line, runs, errors, changes):
        self.mk, self.root = mk, root
        self.meta, self.head, self.states = loaded.meta, loaded.head, loaded.states
        self.S = self.meta["start_date"]
        self.created_at = self.meta.get("created_at")
        self.rules = dict(self.meta.get("rules") or {})
        self.decisions = decisions
        self.cal_line = cal_line
        self.runs, self.errors, self.changes = runs, errors, changes
        self.canon = self.states["A0"][h1.TRAINERS[0]]["days"]
        self.dates = [r["date"] for r in self.canon]
        self.m = markets.MARKETS[mk]

    def rule(self, key, default):
        v = self.rules.get(key)
        return default if v is None else v


def _load(mk, root) -> _Ctx:
    try:
        loaded = h1.load_market(mk, root, repair=False)          # HEAD 로 엄격하게(되살리기·자르기 없음)
    except h1.H1Refused as e:
        raise ReportError(EXIT_NO_LEDGER, str(e))
    except h1.H1LogicError as e:
        raise ReportError(EXIT_ERROR, f"장부를 읽지 못함({e.code or 'L24'}): {e} → 다음 python h1.py run 이 백업으로 "
                                      "되살릴 수 있으면 되살려요. 그 뒤 다시 보고서를 만드세요")
    if not loaded.states["A0"][h1.TRAINERS[0]]["days"]:
        raise ReportError(EXIT_NO_LEDGER, "처리한 봉이 없는 장부예요")
    try:
        decisions = h1.DecisionLog(h1.decisions_path(root), read_only=True)
    except h1.H1LogicError as e:
        raise ReportError(EXIT_ERROR, f"판정 기록을 읽지 못함({e.code}): {e}")
    return _Ctx(mk, root, loaded, decisions, h1._last_ok_calendar_line(root, mk),
                h1._read_log(root, "runs.jsonl"), h1._read_log(root, "errors.jsonl"),
                h1._read_log(root, "changes.jsonl"))


def _replay_allowed(root):
    """(허용 지문 모음 또는 None, 이유). 재현 통과 기록의 (code_hash, env_key) 모음."""
    try:
        entries = h1.replay_pass_entries(root)
    except (h1.H1Refused, h1.H1LogicError) as e:
        return None, f"재현 통과 기록을 읽지 못함: {e}"
    if not entries:
        return set(), "재현 통과 기록(replay_pass.json)이 비었거나 없음"
    return {(e.get("code_hash"), h1.env_key(e.get("env"))) for e in entries}, None


# ============================ 계산 도움 ============================

def _le_time(a, b) -> bool:
    """시각 글자 a ≤ b (못 읽으면 True — 보수적으로 창 안에 넣음)."""
    try:
        return datetime.fromisoformat(a) <= datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return True


def _add_weekdays(d: str, n: int) -> str:
    x = _date.fromisoformat(d)
    while n > 0:
        x += timedelta(days=1)
        if x.weekday() < 5:
            n -= 1
    return x.isoformat()


def _weekdays_between(a: str, b: str) -> int:
    """a 다음 날 ~ b 까지 평일 수(휴장일은 빼지 않음)."""
    x, y, n = _date.fromisoformat(a), _date.fromisoformat(b), 0
    while x < y:
        x += timedelta(days=1)
        if x.weekday() < 5:
            n += 1
    return n


def _team(c, arm, upto, start=None):
    """장부(arm) 세 트레이너 합의 매일 값 [{date, value, cash, stock_value, idle_value, idle_units}] (start ≤ 날짜 ≤ upto)."""
    per = [{r["date"]: r for r in c.states[arm][tn]["days"]} for tn in h1.TRAINERS]
    out = []
    for d in c.dates:
        if d > upto or (start is not None and d < start):
            continue
        rows = [p.get(d) for p in per]
        if any(r is None for r in rows):
            continue
        out.append({"date": d, **{k: sum(r[k] for r in rows)
                                  for k in ("value", "cash", "stock_value", "idle_value", "idle_units")}})
    return out


def _rows(c, arm, tn, upto, start=None):
    return [r for r in c.states[arm][tn]["days"] if r["date"] <= upto and (start is None or r["date"] >= start)]


def _ret(v, base):
    return None if base in (None, 0) or v is None else v / base - 1


def _mdd(values):
    return metrics.max_drawdown(values) if values else None


# ============================ 운영 기준 (§3.8-2) ============================

def _window_end_at(c, s62):
    """판정 창 마지막 봉 S+62 를 저장한 실행의 끝 시각(그 뒤 일지 줄은 '연장'). 못 찾으면 None(일지 전체를 봄)."""
    for r in c.runs:
        if r.get("event") == "end" and r.get("market") == c.mk and s62 in (r.get("bars") or []) \
                and r.get("exit_code") in (h1.EXIT_OK, h1.EXIT_D7):
            return r.get("at")
    return None


def _ops(c, bar_upto, jr_upto, end_at, allowed, allowed_why):
    """운영 기준 칸. bar_upto = 하루 기록을 볼 마지막 봉, jr_upto = 일지 줄의 봉 날짜 상한, end_at = 일지 시각 상한."""
    mk, S = c.mk, c.S
    inwin = lambda r: r.get("market") == mk and h1._in_window(r, S, c.created_at)   # noqa: E731

    def in_time(r):
        return end_at is None or _le_time(r.get("at"), end_at)

    dates = [d for d in c.dates if d <= bar_upto]
    out = {"n_bars": len(dates), "window_bars": int(c.rule("window_bars", h1.WINDOW_BARS)), "first": S,
           "last": dates[-1] if dates else None}
    # 빠진 날: calendar.jsonl 마지막 정상 줄의 날짜 목록(S ~ 마지막 처리 봉) vs 하루 기록
    if c.cal_line is not None:
        cal = [d for d in c.cal_line.get("dates") or [] if S <= d <= bar_upto]
        out["missing"] = sorted(set(cal) - set(dates))
        out["extra"] = sorted(set(dates) - set(cal))
        out["cal_at"] = c.cal_line.get("at")
    else:
        out["missing"] = out["extra"] = None
        out["cal_at"] = None
    out["ledger_dates_differ"] = sorted(f"{arm}/{tn}" for arm in h1.ARMS for tn in h1.TRAINERS
                                        if [r["date"] for r in _rows(c, arm, tn, bar_upto)] != dates)
    out["late"] = sorted({r["date"] for arm in h1.ARMS for tn in h1.TRAINERS
                          for r in _rows(c, arm, tn, bar_upto) if r.get("late")})
    out["late_calls"] = sum(r.get("late_calls") or 0 for arm in h1.ARMS for tn in h1.TRAINERS
                            for r in _rows(c, arm, tn, bar_upto))
    # 일지(runs.jsonl 끝 줄): 이 창(h1._in_window) + 판정 창 안(봉이 jr_upto 이하, 봉 없는 줄은 시각이 end_at 이하)
    ends = [r for r in c.runs if r.get("event") == "end" and inwin(r)]

    def relevant(r):
        bars = r.get("bars") or []
        return any(b <= jr_upto for b in bars) if bars else in_time(r)

    rel = [r for r in ends if relevant(r)]
    procs = [r for r in rel if r.get("command") in ("run", "start")]
    out["batch_max"] = max((len(r.get("bars") or []) for r in procs), default=0)
    out["backlog_fail"] = sum(1 for r in rel if r.get("exit_code") == h1.EXIT_BACKLOG)
    out["gate_refused"] = sum(1 for r in rel if r.get("exit_code") == h1.EXIT_GATE)
    stops = [r for r in rel if r.get("exit_code") in (h1.EXIT_DATA, h1.EXIT_D7)]
    out["data_stops"] = len(stops)
    out["data_kinds"] = dict(sorted(Counter(p.get("code") for r in stops for p in r.get("problems") or []
                                            if p.get("level") == "D").items()))
    out["lock_timeouts"] = sum(1 for r in c.runs if r.get("event") == "lock_timeout" and inwin(r) and in_time(r))
    errs = [r for r in c.errors if inwin(r) and ((r.get("date") <= jr_upto) if r.get("date") else in_time(r))]
    out["l_errors"] = len(errs)
    out["l_codes"] = dict(sorted(Counter(p.get("code") for r in errs for p in r.get("problems") or []
                                         if p.get("level") == "L").items()))
    out["l_list"] = [(r.get("at"), r.get("date"), ", ".join(sorted({p.get("code") for p in r.get("problems") or []
                                                                     if p.get("level") == "L"})))
                     for r in errs]
    # 다른 지문으로 처리한 봉 (②-3): 하루 기록·실행 일지의 (code_hash, env) 가 재현 통과 기록에 없음
    bad_rows = sorted({r["date"] for arm in h1.ARMS for tn in h1.TRAINERS for r in _rows(c, arm, tn, bar_upto)
                       if allowed is None or (r.get("code_hash"), h1.env_key(r.get("env"))) not in allowed})
    bad_runs = sorted({b for r in procs for b in (r.get("bars") or []) if b <= jr_upto
                       and (allowed is None or (r.get("code_hash"), h1.env_key(r.get("env"))) not in allowed)})
    out["other_fp_rows"], out["other_fp_runs"] = bad_rows, bad_runs
    out["other_fp"] = sorted(set(bad_rows) | set(bad_runs))
    out["allowed_n"] = None if allowed is None else len(allowed)
    out["allowed_why"] = allowed_why
    # 코드·환경 지문이 바뀐 날(하루 기록)
    fps, prev = [], None
    for r in _rows(c, "A0", h1.TRAINERS[0], bar_upto):
        k = (r.get("code_hash"), h1.env_key(r.get("env")))
        if k != prev:
            env = r.get("env") or {}
            fps.append({"date": r["date"], "code_hash": str(r.get("code_hash"))[:12],
                        "env": f"python {env.get('python')} · pandas {env.get('pandas')} · "
                               f"FinanceDataReader {env.get('FinanceDataReader')}"})
            prev = k
    out["fingerprints"] = fps
    # 재시작 · 코드 변경 일지 · 기업 행위
    groups = {}                                        # restart_id → 의도 줄('moving')·끝 줄('done')을 합친 것
    for r in h1._restart_records(mk, c.root):
        g = groups.setdefault(h1._restart_id(r), {})
        for k in ("at", "reason", "old_start", "old_last", "restart_no"):
            if g.get(k) is None and r.get(k) is not None:
                g[k] = r.get(k)
        g["done"] = g.get("done", False) or r.get("status", "done") == "done"
    out["restarts"] = list(groups.values())
    out["restarts_used"] = h1._count_restarts(mk, c.root)
    max_rs = int(c.rule("max_restarts", h1.MAX_RESTARTS))
    out["max_restarts"] = max_rs
    out["restarts_left"] = max(0, max_rs - out["restarts_used"])
    ch = [r for r in c.changes if (r.get("market") in (mk, None)) and (c.created_at is None
                                                                          or not _le_time(r.get("at"), c.created_at))
          and in_time(r)]
    out["changes"] = dict(sorted(Counter(str(r.get("kind")) for r in ch).items()))
    out["amend"] = [(r.get("at"), r.get("source")) for r in ch if r.get("kind") == "amend-rules"
                    and r.get("status") == "done"]
    cas = c.states["A0"][h1.TRAINERS[0]]["corp_actions"]
    if end_at is not None:
        cas = [ca for ca in cas if _le_time(ca.get("at"), end_at)]
    out["corp"] = {k: [ca for ca in cas if ca.get("kind") == k] for k in ("split", "delist", "correction")}
    deadline = str(c.rule("deadline", h1.DEADLINE))
    out["deadline"] = deadline
    base = out["last"] or S
    out["days_to_deadline"] = (_date.fromisoformat(deadline) - _date.fromisoformat(base)).days
    left = max(0, out["window_bars"] - out["n_bars"])
    out["bars_left"] = left
    out["window_end"] = dates[out["window_bars"] - 1] if len(dates) >= out["window_bars"] else None
    out["window_end_est"] = out["window_end"] or (_add_weekdays(base, left) if left else base)
    out["weekdays_to_deadline"] = _weekdays_between(base, deadline) if deadline > base else 0
    out["max_late_total"] = int(c.rule("max_late_total", h1.MAX_LATE_TOTAL))
    out["max_late_batch"] = int(c.rule("max_late_batch", h1.MAX_LATE_BATCH))
    return out


# ============================ 값·비율·매매 (§3.8-3~5) ============================

def _values(c, cut, mstart):
    """두 장부·트레이너별 평가액·수익률(S 이후, 그 기간)·MDD, A1−A0, 지수 B&H."""
    out = {"cut": cut, "mstart": mstart, "arms": {}, "trainers": []}
    for arm in h1.ARMS:
        team = _team(c, arm, cut)
        start_total = sum(c.states[arm][tn]["start_cash"] for tn in h1.TRAINERS)
        vals = [r["value"] for r in team]
        v = vals[-1]
        before = [r["value"] for r in team if mstart is not None and r["date"] < mstart]
        base_m = before[-1] if before else vals[0]
        out["arms"][arm] = {"start": start_total, "value": v, "ret": _ret(v, start_total),
                            "ret_period": _ret(v, base_m) if mstart is not None else None,
                            "base_period": base_m if mstart is not None else None,
                            "mdd": _mdd(vals), "units": team[-1]["idle_units"], "n": len(vals)}
    a0, a1 = out["arms"]["A0"], out["arms"]["A1"]
    out["diff"] = a1["value"] - a0["value"]
    out["diff_pp"] = (a1["ret"] - a0["ret"]) * 100
    out["diff_period_pp"] = ((a1["ret_period"] - a0["ret_period"]) * 100) if mstart is not None else None
    rows = [r for r in c.canon if r["date"] <= cut]
    w = h1._plain_wallet(c.states["A1"][h1.TRAINERS[0]]["wallet"])
    bh = index_buy_hold_same_start([r["idle_open"] for r in rows], [r["idle_close"] for r in rows], a1["start"],
                                   w["fee_rate"], w["slippage"])
    before = [v for r, v in zip(rows, bh["values"]) if mstart is not None and r["date"] < mstart]
    bh["ret_period"] = _ret(bh["values"][-1], before[-1] if before else bh["values"][0]) \
        if mstart is not None and bh["values"] else None
    bh["value"] = bh["values"][-1] if bh["values"] else None
    bh["started"] = bh["units"] is not None
    bh["a1_minus_pp"] = (a1["ret"] - bh["return"]) * 100 if bh["return"] is not None else None
    bh.pop("values")
    out["bh"] = bh
    for tn in h1.TRAINERS:
        line = {"trainer": tn}
        for arm in h1.ARMS:
            rr = _rows(c, arm, tn, cut)
            sc = c.states[arm][tn]["start_cash"]
            line[arm] = {"value": rr[-1]["value"], "ret": _ret(rr[-1]["value"], sc),
                         "mdd": _mdd([r["value"] for r in rr])}
        line["diff"] = line["A1"]["value"] - line["A0"]["value"]
        out["trainers"].append(line)
    return out


def _ratios(c, start, cut):
    out = {}
    for arm in h1.ARMS:
        team = _team(c, arm, cut, start)
        fr = [(r["stock_value"] / r["value"], r["idle_value"] / r["value"], r["cash"] / r["value"]) for r in team]
        n = len(fr)
        out[arm] = {"n": n, "mean": tuple(sum(x[i] for x in fr) / n for i in range(3)) if n else None,
                    "last": fr[-1] if n else None}
    return out


def _trades(c, start, cut):
    """매매 수·보류·빈자리 부족·비용(주식/지수 다리 따로), start ≤ 날짜 ≤ cut."""
    out = {}
    for arm in h1.ARMS:
        a = {"stock_buy": 0, "stock_sell": 0, "idle_buy": 0, "idle_sell": 0, "delist": 0,
             "skips": {k: 0 for k in SKIP_KINDS}, "over_slots": 0,
             "cost": {kind: {"fee": 0.0, "slip": 0.0, "tax": 0.0} for kind in ("stock", "idle")}}
        for tn in h1.TRAINERS:
            st = c.states[arm][tn]
            for f in st["fills"]:
                if not (start <= f["date"] <= cut):
                    continue
                a[f"{f['kind']}_{f['side']}"] += 1
                if f.get("purpose") == "delist":
                    a["delist"] += 1
                cc = a["cost"][f["kind"]]
                cc["fee"] += f["fee"]
                cc["slip"] += f["slip_cost"]
                cc["tax"] += f["tax"]
            for s in st["skips"]:
                if start <= s["date"] <= cut:
                    a["skips"][s["kind"]] = a["skips"].get(s["kind"], 0) + 1
            a["over_slots"] += sum(r.get("over_slots") or 0 for r in _rows(c, arm, tn, cut, start))
        out[arm] = a
    return out


def _shadow(c, cut):
    """그림자 서킷: (장부, 트레이너)별 첫 발동일·사유·발동한 날 수 (S ~ cut)."""
    out = []
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            hits = [(r["date"], e) for r in _rows(c, arm, tn, cut) for e in r.get("events") or []
                    if e.get("kind") == "shadow_breaker"]
            days = sorted({d for d, _ in hits})
            first = hits[0] if hits else None
            out.append({"arm": arm, "trainer": tn, "first": first[0] if first else None,
                        "why": first[1].get("why") if first else None, "days": len(days),
                        "flag_first": next((d for d, e in hits if e.get("first")), None)})
    return out


def _realized_all(c, cut, period_start, year_start):
    """장부(arm)·종류별 실현손익: 그 기간(start~cut), 그해 누적(year_start~cut), S 이후(S~cut)."""
    out = {}
    for arm in h1.ARMS:
        a = {kind: {"period": 0.0, "ytd": 0.0, "since_s": 0.0, "n": 0} for kind in ("stock", "idle")}
        by_code = {}
        for tn in h1.TRAINERS:
            st = c.states[arm][tn]
            res = realized([f for f in st["fills"] if f["date"] <= cut], st["corp_actions"])
            for s in res["sells"]:
                k = a[s["kind"]]
                k["since_s"] += s["gain"]
                k["n"] += 1
                if s["date"] >= period_start:
                    k["period"] += s["gain"]
                if s["date"] >= year_start:
                    k["ytd"] += s["gain"]
                if s["kind"] == "stock":
                    by_code[s["code"]] = by_code.get(s["code"], 0.0) + s["gain"]
        a["by_code"] = dict(sorted(by_code.items()))
        out[arm] = a
    return out


def _leader(c, start, cut):
    """팀장 판정 기록(S ~ cut, 이 시장): 판정 × 출처, 상태별, 폴백 비율, 장부별 효과, CLI 버전·모델이 바뀐 날."""
    recs = [r for r in c.decisions.records() if r.get("market") == c.mk and start <= str(r.get("date")) <= cut]
    n = len(recs)
    fb = sum(1 for r in recs if r.get("status") != "ok")
    flag = float(c.rule("fallback_flag", h1.FALLBACK_FLAG))
    out = {"n": n, "fallback": fb, "ratio": fb / n if n else None, "flag": flag,
           "unrepresentative": (fb / n > flag) if n else False,
           "by_verdict": dict(sorted(Counter(((r.get("verdict") or "없음"), r.get("source") or "?")
                                             for r in recs).items())),
           "by_status": dict(sorted(Counter(r.get("status") or "?" for r in recs).items())),
           "truncated": c.decisions.truncated}
    eff = {}
    for arm in h1.ARMS:
        cnt = Counter(e.get("effect") for tn in h1.TRAINERS for r in _rows(c, arm, tn, cut, start)
                      for e in r.get("leader") or [])
        eff[arm] = {k: cnt.get(k, 0) for k in EFFECTS}
    out["effects"] = eff
    changes, prev = [], None
    for r in recs:                                     # 파일 순서 = 물은 순서
        cur = (r.get("cli_version"), r.get("model"))
        if prev is None:
            out["first_cli"], out["first_model"] = cur
        elif cur != prev:
            changes.append({"date": r.get("date"), "asked_at": r.get("asked_at"), "from": prev, "to": cur})
        prev = cur
    if prev is None:
        out["first_cli"] = out["first_model"] = None
    out["changes"] = changes
    return out


# ============================ A0 현금 + 이자 (§3.8-9) ============================

def _interest(c, cut, period_start, rates):
    """A0 현금 이자(계산만). rates = {"info": rates_info 결과, "mode": "online"|"offline"|"failed"}."""
    sid, rule = SERIES[c.mk], RULE[c.mk]
    info = rates["info"]
    out = {"series": sid, "rule": rule, "mode": rates["mode"], "ok": bool(info.get("ok")),
           "why": info.get("why"), "path": info.get("file"), "fetched_at": info.get("fetched_at"),
           "format": info.get("format"), "first_rate": info.get("first"), "last_rate": info.get("last"),
           "source": info.get("source")}
    if not info.get("ok"):
        return out
    series = info["series"]
    rows0 = [r for r in c.canon if r["date"] <= cut]
    dates = [r["date"] for r in rows0]
    if rule == "prev_day":
        cal = [rows0[0]["prev_cal_date"]] + dates
        rates_pct = rate_for_days(cal, series, rule)[1:]
        match = rate_match(cal, series, rule)[1:]
        bad_prev = [r["date"] for r, (k, _, _) in zip(rows0, match) if k != r.get("prev_cal_date")]
    else:
        rates_pct = rate_for_days(dates, series, rule)
        match = rate_match(dates, series, rule)
        bad_prev = []
    team0 = _team(c, "A0", cut)
    team1 = _team(c, "A1", cut)
    cash = [r["cash"] for r in team0]
    acc = interest_overlay(dates, cash, rates_pct)
    last_rate = info["last"]
    table = []
    for r, (key, got, v), i in zip(rows0, match, acc):
        if not math.isfinite(v):
            note = "금리 없음(자료보다 앞) → 0 으로 계산"
        elif key > last_rate:
            note = f"자료 끝 → {got} 값 이월" + (f" (오프라인: {got} 값 이월)" if rates["mode"] != "online" else "")
        elif got != key:
            note = f"그날 값 없음 → {got} 값"
        else:
            note = ""
        table.append({"date": r["date"], "key": key, "rate_date": got, "rate": v, "interest": i, "note": note})
    before = [x["interest"] for x in table if x["date"] < period_start]
    v0, v1 = team0[-1]["value"], team1[-1]["value"]
    start_total = sum(c.states["A0"][tn]["start_cash"] for tn in h1.TRAINERS)
    i_cut = acc[-1]
    out.update({"table": [x for x in table if x["date"] >= period_start], "interest": i_cut,
                "interest_period": i_cut - (before[-1] if before else 0.0),
                "a0": v0, "a0_plus": v0 + i_cut, "ret_plus": (v0 + i_cut) / start_total - 1,
                "a1_minus_plus": v1 - (v0 + i_cut),
                "missing_days": sum(1 for v in rates_pct if not math.isfinite(v)),
                "carried_days": sum(1 for x in table if x["key"] and math.isfinite(x["rate"])
                                    and x["key"] > last_rate),
                "prev_mismatch": bad_prev})
    return out


def _rates_for(mk, root, online):
    sid = SERIES[mk]
    cache = h1.h1_path(root, "rates")
    mode = "offline"
    if online:
        mode = "online" if fetch_rates(sid, cache) is not None else "failed"
    return {"info": rates_info(sid, cache), "mode": mode}


# ============================ 장부 다시 점검 (§3.8-10) ============================

def _recheck(c, cut_date=None):
    cal = c.cal_line.get("dates") if c.cal_line else None
    probs = []
    for arm in h1.ARMS:
        probs += h1_check.check_ledger(c.mk, arm, c.states[arm], cal, c.decisions, None)
    probs += h1_check.check_pair(c.mk, c.states["A0"], c.states["A1"], c.decisions)
    probs += h1_check.check_decisions(c.mk, c.decisions, h1._head_digest(c.head))
    errs = h1_check.errors(probs)
    uni_ok, uni_why = None, None
    try:
        got = h1.read_universe(c.mk, c.root)
        if got is None:
            uni_ok, uni_why = False, "종목군 파일이 없음"
        else:
            uni_ok = got[1] == c.meta["universe_sha256"]
            uni_why = None if uni_ok else "종목군 파일 지문 ≠ meta.universe_sha256"
    except h1.H1LogicError as e:
        uni_ok, uni_why = False, str(e)
    in_win = [p for p in errs if cut_date is None or p.date is None or p.date <= cut_date]
    return {"n": len(errs), "codes": dict(sorted(Counter(p.code for p in errs).items())),
            "list": [f"{p.code} {p.arm or ''}/{p.trainer or ''} {p.date or ''}: {p.detail}" for p in errs[:20]],
            "n_window": len(in_win), "universe_ok": uni_ok, "universe_why": uni_why,
            "calendar_at": c.cal_line.get("at") if c.cal_line else None}


# ============================ 모으기 ============================

def _month_ok(m) -> bool:
    return isinstance(m, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", m) is not None


def _collect_locked(mk, root, month, final, online) -> dict:
    c = _load(mk, root)
    S, last = c.S, c.dates[-1]
    if final and month is not None:
        raise ReportError(EXIT_USAGE, "--final 과 --month 는 같이 쓸 수 없어요(최종 보고서는 판정 창 전체)")
    if not final:
        month = month or last[:7]
        if not _month_ok(month):
            raise ReportError(EXIT_USAGE, f"--month 는 YYYY-MM 이어야 해요 (받은 값 {month!r})")
        if month < S[:7] or month > last[:7]:
            raise ReportError(EXIT_USAGE, f"{month} 는 이 판정 창(S {S} ~ 마지막 처리 봉 {last})의 달이 아니에요")
    allowed, allowed_why = _replay_allowed(root)
    rates = _rates_for(mk, root, online)
    wb = int(c.rule("window_bars", h1.WINDOW_BARS))
    complete = len(c.dates) >= wb
    s62 = c.dates[wb - 1] if complete else None
    data = {"market": mk, "name": NAME[mk], "kind": "final" if final else "monthly", "month": month, "S": S,
            "last": last, "head": {k: c.head[k] for k in ("last_date", "run_id", "written_at")},
            "created_at": c.created_at, "restart_no": c.meta.get("restart_no"), "idle": h1.idle_code(mk),
            "rules_changed": h1._norm(c.rules) != h1._norm(h1.rule_constants(mk)),
            "window_bars": wb, "complete": complete, "s62": s62}
    if final:
        cut = s62 if complete else last
        end_at = _window_end_at(c, s62) if complete else None
        jr_upto = s62 if complete else _FAR
        period_start = S
        year_start = S
    else:
        cut = max(d for d in c.dates if d <= f"{month}-31")
        end_at, jr_upto = None, _FAR
        period_start = max(S, f"{month}-01")
        year_start = max(S, f"{month[:4]}-01-01")
    data.update({"cut": cut, "period_start": period_start, "end_at": end_at})
    data["ops"] = _ops(c, cut if final else last, jr_upto, end_at, allowed, allowed_why)
    data["values"] = _values(c, cut, None if final else f"{month}-01")
    data["ratios"] = {"period": _ratios(c, period_start, cut)}
    data["trades"] = {"period": _trades(c, period_start, cut)}
    if not final:
        data["trades"]["since_s"] = _trades(c, S, cut)
    data["shadow"] = _shadow(c, cut)
    data["realized"] = _realized_all(c, cut, period_start, year_start)
    data["leader"] = _leader(c, S, cut)
    data["interest"] = _interest(c, cut, period_start, rates)
    data["recheck"] = _recheck(c, s62 if final and complete else None)
    if final:
        data["verdict"] = _verdict(data)
        data["extension"] = _extension(c, s62) if complete and last > s62 else None
    return data


def _verdict(d) -> dict:
    """--final: 운영 기준 ①~③ 의 통과/실패(수익률은 쓰지 않음, 사전 등록 ③⑨)와 ⑤ 재시작 상한·마감."""
    ops, rc = d["ops"], d["recheck"]
    over_deadline = (d["s62"] or d["last"]) > ops["deadline"]
    c1 = {"ok": ops["l_errors"] == 0 and rc["n_window"] == 0,
          "detail": f"errors.jsonl 의 L 오류 {ops['l_errors']}건, 저장 자료로 다시 점검한 L 오류 {rc['n_window']}건"}
    missing = ops["missing"]
    c2_parts = {
        "빠진 날 0": missing is not None and not missing and not ops["extra"] and not ops["ledger_dates_differ"],
        f"늦은 봉 ≤ {ops['max_late_total']}": len(ops["late"]) <= ops["max_late_total"],
        f"한 번에 따라잡은 봉 ≤ {ops['max_late_batch']}": ops["batch_max"] <= ops["max_late_batch"]
        and ops["backlog_fail"] == 0,
    }
    c2 = {"ok": all(c2_parts.values()), "parts": c2_parts,
          "detail": f"빠진 날 {('?' if missing is None else len(missing))}개, 늦은 봉 {len(ops['late'])}개, "
                    f"한 번에 최대 {ops['batch_max']}봉, 밀린 봉 초과(종료 코드 6) {ops['backlog_fail']}번"}
    c3 = {"ok": ops["allowed_n"] not in (None, 0) and not ops["other_fp"],
          "detail": f"다른 지문으로 처리한 봉 {len(ops['other_fp'])}개"
                    + (f" ({ops['allowed_why']})" if ops["allowed_why"] else "")}
    violated = not (c1["ok"] and c2["ok"] and c3["ok"])
    no_more = ops["restarts_left"] <= 0
    out = {"complete": d["complete"], "c1": c1, "c2": c2, "c3": c3, "over_deadline": over_deadline}
    if not d["complete"]:
        out["passed"] = None
        if d["last"] > ops["deadline"]:
            out["result"] = "fail_h1"
            out["why"] = f"마감 {ops['deadline']} 까지 깨끗한 판정 창이 끝나지 않음"
        elif violated and no_more:
            out["result"] = "fail_h1"
            out["why"] = (f"이 창이 이미 운영 기준을 어겼고 남은 재시작이 없음(재시작 {ops['restarts_used']}/"
                          f"{ops['max_restarts']} — 재시작이 {ops['max_restarts']}번을 넘게 필요함)")
        else:
            out["result"] = "not_finished"
            out["why"] = f"아직 판정 창이 끝나지 않음 — 남은 봉 {ops['bars_left']}개"
        return out
    out["passed"] = not violated and not over_deadline
    if out["passed"]:
        out["result"] = "pass"
        out["why"] = "운영 기준 ①~③ 모두 통과 → 이 시장에서 H1 을 기본 장부로 할지 검토로 넘어감"
    elif over_deadline:
        out["result"] = "fail_h1"
        out["why"] = f"판정 창 마지막 봉 {d['s62']} 이 마감 {ops['deadline']} 뒤"
    elif no_more:
        out["result"] = "fail_h1"
        out["why"] = (f"운영 기준 미충족이고 남은 재시작이 없음(재시작 {ops['restarts_used']}/{ops['max_restarts']} — "
                      f"재시작이 {ops['max_restarts']}번을 넘게 필요함)")
    else:
        out["result"] = "fail_window"
        out["why"] = (f"판정 창 실패 → 재시작 대상(사전 등록 ⑤, 남은 재시작 {ops['restarts_left']}번, "
                      f"마감 {ops['deadline']})")
    return out


def _extension(c, s62) -> dict:
    """연장 기록: 판정 창(S+62) 뒤에 처리한 봉. 판정에 쓰지 않는다(사전 등록 ①)."""
    ext = [d for d in c.dates if d > s62]
    last = ext[-1]
    out = {"n": len(ext), "first": ext[0], "last": last,
           "late": sum(1 for r in c.canon if r["date"] > s62 and r.get("late")),
           "l_errors": sum(1 for r in c.errors if r.get("market") == c.mk and h1._in_window(r, c.S, c.created_at)
                           and r.get("date") and r["date"] > s62)}
    for arm in h1.ARMS:
        team = _team(c, arm, last)
        base = next(r["value"] for r in reversed(team) if r["date"] <= s62)
        out[arm] = {"value": team[-1]["value"], "ret_ext": _ret(team[-1]["value"], base)}
    return out


def collect(market, month=None, final=False, root=None, online=True) -> dict:
    """보고서 숫자 묶음(잠금 아래에서 읽기만, online 이면 금리 저장본만 새로 씀). 시험·재현용."""
    mk = h1._mkey(market)
    root = h1._root(root)
    _need_market(mk, root)
    with h1.h1_lock(root):
        return _collect_locked(mk, root, month, final, online)


def _need_market(mk, root):
    if not h1.market_dir(mk, root).is_dir():
        raise ReportError(EXIT_NO_LEDGER, f"{mk} 장부가 없어요({h1.market_dir(mk, root)}) → 먼저 python h1.py start --market {mk}")


# ============================ 글로 쓰기 ============================

def _money(mk, v, sign=False):
    return markets.money(mk, v, sign)


def _pct(x, digits=2):
    return "계산 불가" if x is None else f"{x * 100:+.{digits}f}%"


def _pp(x):
    return "계산 불가" if x is None else f"{x:+.2f}%p"


def _frac(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return out


def _ok_word(ok):
    return "통과" if ok else "**실패**"


def render(d) -> str:
    mk, S = d["market"], d["S"]
    ops, val = d["ops"], d["values"]
    idle = d["idle"]
    L = []
    if d["kind"] == "final":
        L.append(f"# H1 포워드 최종 보고서 — {d['name']}({mk}) · 판정 창 S {S}"
                 + (f" ~ S+62 {d['s62']}" if d["complete"] else " (아직 끝나지 않음)"))
    else:
        L.append(f"# H1 포워드 월간 보고서 — {d['name']}({mk}) {d['month']} · 판정 창 S {S}")
    L += ["",
          f"- 기준: 저장된 마지막 봉 {d['last']} (HEAD {d['head']['run_id']}, {d['head']['written_at']}) · "
          f"이 보고서의 값은 {d['period_start']} ~ {d['cut']}" + (" (S 이후 누적도 같이)" if d["kind"] != "final" else ""),
          f"- 시작 금액(두 장부 같음): {_money(mk, val['arms']['A0']['start'])} · 재시작 번호 {d['restart_no']} · "
          f"창 만든 시각 {d['created_at']}",
          "- 진짜 돈·진짜 주문은 없다. 장부(가짜 지갑)만 쓴다.", ""]
    # 1. 고정 문장
    L += ["## 1. 먼저 읽을 것 (고정 문장)", "", f"> {FIXED_RECORD_ONLY}", ">", f"> {FIXED_A0}", ""]
    if d["rules_changed"]:
        L += ["> ※ 장부의 meta.rules(시작 때 규칙)가 지금 코드 상수와 달라요 → 다음 run 은 종료 코드 3. "
              "세율 줄 추가면 python h1.py amend-rules", ""]
    if d["kind"] == "final":
        L += _render_verdict(d)
    L += _render_ops(d)
    L += _render_values(d)
    L += _render_ratios(d)
    L += _render_trades(d)
    L += _render_shadow(d)
    L += _render_realized(d)
    L += _render_leader(d)
    L += _render_interest(d)
    L += _render_recheck(d)
    if d["kind"] == "final":
        L += _render_extension(d)
    L += ["## 11. 한계", "",
          "- 배당을 넣지 않았다(주식·지수 모두 가격만).",
          f"- ETF 운용보수가 없다: 대기 자산은 지수({idle}) 그 자체로 계산했다(실제 ETF 는 해마다 보수가 빠짐, Q13).",
          "- 생존편향: 종목군은 시작 때 정한 목록이다(미국은 S 날 S&P500 상위 섞기 40종목, 국내는 KR_UNIVERSE 32종목).",
          "- 3개월(63거래일)은 수익률을 판단하기에 너무 짧다(사전 등록 ③).",
          "- 'A0+이자'는 근사다(9절): R2 A0 는 이자가 현금에 들어가 매수·서킷에 쓰이지만 여기서는 따로 쌓기만 한다.",
          "- 실현손익은 평균원가법 참고값이다. 실제 신고 방식(선입선출 등)·환율은 반영하지 않았다.",
          "- 오프라인으로 다시 볼 수 없는 점검이 있다(10절).", ""]
    return "\n".join(L).rstrip() + "\n"


def _render_verdict(d):
    v, ops = d["verdict"], d["ops"]
    L = ["## 판정 (사전 등록 ①~③ — 운영 기준만, 수익률은 쓰지 않음)", ""]
    if not v["complete"]:
        L += [f"- **아직 판정 창이 끝나지 않음** — 처리 {ops['n_bars']}/{d['window_bars']}봉, 남은 봉 {ops['bars_left']}개. "
              "판정하지 않는다(S+62 를 처리한 뒤 다시 --final).", ""]
        if v["result"] == "fail_h1":
            L += [f"- **H1 포워드 실패(운영 기준 미충족)** — {v['why']} (사전 등록 ⑤)", ""]
        return L
    L += _table(["기준", "결과", "근거"], [
        ["②-1 장부 논리 오류 0건", _ok_word(v["c1"]["ok"]), v["c1"]["detail"]],
        ["②-2 빠진 날 0 · 늦은 봉 · 한 번에 따라잡은 봉", _ok_word(v["c2"]["ok"]),
         v["c2"]["detail"] + " — " + ", ".join(f"{k} {'O' if ok else 'X'}" for k, ok in v["c2"]["parts"].items())],
        ["②-3 재현을 통과한 코드·환경만", _ok_word(v["c3"]["ok"]), v["c3"]["detail"]],
    ])
    L.append("")
    if v["result"] == "pass":
        L.append(f"- **운영 기준 통과** — {v['why']}")
    elif v["result"] == "fail_h1":
        L.append(f"- **H1 포워드 실패(운영 기준 미충족)** — {v['why']} (사전 등록 ⑤)")
    else:
        L.append(f"- **판정 창 실패** — {v['why']}")
    L += ["- 판정 창: S {} ~ S+62 {} (63봉). 그 뒤 봉은 아래 '연장 기록'에만 쓰고 판정에 쓰지 않는다(사전 등록 ①)."
          .format(d["S"], d["s62"]),
          "- 수익률·MDD·A1−A0·지수 대비·그림자 서킷·팀장 숫자는 아래 기록 절에만 있다(사전 등록 ③⑨).", ""]
    return L


def _render_ops(d):
    ops = d["ops"]
    final = d["kind"] == "final"
    head = "## 2. 운영 기준" + (" (판정 창 안)" if final and d["complete"] else " (판정 아님 — 이 창의 지금까지 상태)")
    L = [head, ""]
    prog = f"{min(ops['n_bars'], ops['window_bars'])}/{ops['window_bars']}봉"
    if ops["n_bars"] > ops["window_bars"]:
        prog += f" (+연장 {ops['n_bars'] - ops['window_bars']}봉)"
    end = (f"S+62 = {ops['window_end']} (처리함)" if ops["window_end"]
           else f"S+62 예정 {ops['window_end_est']} 무렵(휴장일을 빼지 않은 어림, 남은 {ops['bars_left']}봉)")
    if ops["missing"] is None:
        miss = "calendar.jsonl 정상 줄이 없어 셀 수 없음"
    else:
        miss = f"{len(ops['missing'])}개" + (f" ({', '.join(ops['missing'][:10])})" if ops["missing"] else "")
        if ops["extra"]:
            miss += f" · 달력에 없는 하루 기록 {len(ops['extra'])}개({', '.join(ops['extra'][:10])})"
    if ops["ledger_dates_differ"]:
        miss += f" · 날짜 목록이 다른 장부 {', '.join(ops['ledger_dates_differ'])}"
    kinds = ", ".join(f"{k} {v}" for k, v in ops["data_kinds"].items()) or "없음"
    l_codes = ", ".join(f"{k} {v}" for k, v in ops["l_codes"].items())
    rows = [
        ["판정 창 진행", f"{prog} · 시작 S {ops['first']} · {end}"],
        ["장부 논리 오류(L, errors.jsonl)", f"{ops['l_errors']}건" + (f" ({l_codes})" if l_codes else "")
         + " — 0 이어야 함(②-1)"],
        ["빠진 날(calendar.jsonl vs 하루 기록)", miss + " — 0 이어야 함(②-2)"],
        ["늦은 봉(다음 장 시작 뒤 처리)", f"{len(ops['late'])}개 / 상한 {ops['max_late_total']}"
         + (f" ({', '.join(ops['late'][:12])})" if ops["late"] else "")
         + (f" · LLM 직전 시각 재확인으로 안 물은 호출 {ops['late_calls']}번" if ops["late_calls"] else "")],
        ["한 번에 따라잡은 최대 봉 수", f"{ops['batch_max']}봉 / 상한 {ops['max_late_batch']}"
         + (f" · 밀린 봉 초과로 멈춤(종료 코드 6) {ops['backlog_fail']}번" if ops["backlog_fail"] else "")],
        ["다른 지문으로 처리한 봉(재현 통과 기록에 없는 코드·환경)",
         f"{len(ops['other_fp'])}개" + (f" ({', '.join(ops['other_fp'][:10])})" if ops["other_fp"] else "")
         + (f" — {ops['allowed_why']}" if ops["allowed_why"] else "") + " — 0 이어야 함(②-3)"],
        ["관문 거절(종료 코드 3)", f"{ops['gate_refused']}번"],
        ["자료 멈춤(종료 코드 4·7)", f"{ops['data_stops']}번 · 종류별 {kinds} (재시작 아님)"],
        ["잠금 30분 초과(종료 코드 5)", f"{ops['lock_timeouts']}번"],
        ["재시작", f"{ops['restarts_used']}번 / 상한 {ops['max_restarts']} (남은 {ops['restarts_left']}번)"],
        ["마감", f"{ops['deadline']} 까지 {ops['days_to_deadline']}일(마지막 처리 봉 기준) · "
                 f"평일 {ops['weekdays_to_deadline']}일 · 남은 창 봉 {ops['bars_left']}개"],
    ]
    L += _table(["항목", "값"], rows)
    L.append("")
    if ops["restarts"]:
        L.append("- 재시작 기록: " + "; ".join(f"{r['at']} (옛 S {r['old_start']} ~ {r['old_last']}, 사유 {r['reason']!r})"
                                           for r in ops["restarts"]))
    fps = ops["fingerprints"]
    L.append(f"- 코드·환경 지문: {len(fps)}가지" + (" (바뀐 날 " + ", ".join(
        f"{f['date']} code {f['code_hash']}… / {f['env']}" for f in fps[1:]) + ")" if len(fps) > 1 else "")
        + (f" · 처음 {fps[0]['date']} code {fps[0]['code_hash']}… / {fps[0]['env']}" if fps else ""))
    ch = ", ".join(f"{k} {v}" for k, v in ops["changes"].items()) or "없음"
    L.append(f"- 변경 일지(changes.jsonl, 이 창이 만들어진 뒤): {ch}")
    if ops["amend"]:
        L.append("- 세율 줄 추가(amend-rules): " + "; ".join(f"{a} 출처 {s}" for a, s in ops["amend"]))
    corp = ops["corp"]
    L.append(f"- 기업 행위(장부 corp_actions 기준): 분할 {len(corp['split'])}건 · 상장폐지 {len(corp['delist'])}건 · "
             f"정정 확정 {len(corp['correction'])}건")
    for ca in corp["split"]:
        L.append(f"  - 분할 {ca['code']} r={ca['r']} 효력일 {ca['date']} (장부 {ca['applied_after']} 뒤 적용) 출처 {ca.get('source')}")
    for ca in corp["delist"]:
        L.append(f"  - 상장폐지 {ca['code']} 마지막 거래 {ca['last_date']} 종가 {ca['last_close']} 출처 {ca.get('source')}")
    for ca in corp["correction"]:
        L.append(f"  - 정정 확정 {ca['code']} {len(ca.get('items') or [])}칸 출처 {ca.get('source')}")
    L.append("")
    return L


def _render_values(d):
    mk, val = d["market"], d["values"]
    monthly = d["kind"] != "final"
    a0, a1, bh = val["arms"]["A0"], val["arms"]["A1"], val["bh"]
    idle = d["idle"]
    L = ["## 3. 값 (기록만 — 판정에 쓰지 않음)", ""]
    head = ["장부", f"{val['cut']} 평가액", "S 이후"] + (["그달"] if monthly else []) + ["MDD(S 종가부터)"]
    rows = []
    for arm in h1.ARMS:
        a = val["arms"][arm]
        rows.append([f"{arm} {ARM_WORD[arm]}", _money(mk, a["value"]), _pct(a["ret"])]
                    + ([_pct(a["ret_period"])] if monthly else []) + [_pct(a["mdd"])])
    bh_txt = _money(mk, bh["value"]) if bh["started"] else "아직 없음(S+1 시가에 시작)"
    rows.append([f"{idle} 들고 있기(같은 시작: S+1 시가·소수 단위)", bh_txt,
                 _pct(bh["return"]) if bh["started"] else "-"]
                + ([_pct(bh["ret_period"]) if bh["started"] else "-"] if monthly else [])
                + [_pct(bh["mdd"]) if bh["started"] else "-"])
    L += _table(head, rows)
    L += ["",
          f"- A1−A0: {_money(mk, val['diff'], True)} ({_pp(val['diff_pp'])})"
          + (f" · 그달 {_pp(val['diff_period_pp'])}" if monthly else ""),
          f"- A1 − {idle} 들고 있기: {_pp(bh['a1_minus_pp'])}" if bh["started"] else f"- {idle} 들고 있기는 S+1 부터",
          f"- A1 이 들고 있는 {idle}: {h1.fmt_units(a1['units'])}단위(세 트레이너 합)"
          + (f" · {idle} 들고 있기 단위 {h1.fmt_units(bh['units'])}" if bh["started"] else ""),
          "- 수익률 = 평가액 ÷ 시작 금액 − 1(평가액 = 현금 + 주식 × 그날 종가 + 지수 단위 × 지수 종가, 파는 비용은 빼지 않음).", ""]
    rows = []
    for t in val["trainers"]:
        rows.append([t["trainer"], _money(mk, t["A0"]["value"]), _pct(t["A0"]["ret"]), _pct(t["A0"]["mdd"]),
                     _money(mk, t["A1"]["value"]), _pct(t["A1"]["ret"]), _pct(t["A1"]["mdd"]),
                     _money(mk, t["diff"], True)])
    L += ["트레이너별:", ""]
    L += _table(["트레이너", "A0 평가액", "A0 S 이후", "A0 MDD", "A1 평가액", "A1 S 이후", "A1 MDD", "A1−A0"], rows)
    L.append("")
    return L


def _render_ratios(d):
    r = d["ratios"]["period"]
    word = "판정 창 평균" if d["kind"] == "final" else "그달 평균"
    rows = []
    for arm in h1.ARMS:
        a = r[arm]
        mean = a["mean"] or (None, None, None)
        last = a["last"] or (None, None, None)
        rows.append([arm, *(_frac(x) for x in mean), *(_frac(x) for x in last)])
    L = [f"## 4. 주식·지수·현금 비율 ({d['period_start']} ~ {d['cut']}, {r['A0']['n']}봉)", ""]
    L += _table(["장부", f"주식({word})", f"지수({word})", f"현금({word})", "주식(마지막 날)", "지수(마지막 날)",
                 "현금(마지막 날)"], rows)
    L.append("")
    return L


def _render_trades(d):
    mk = d["market"]
    tr = d["trades"]
    cols = [("period", "판정 창" if d["kind"] == "final" else "그달")]
    if "since_s" in tr:
        cols.append(("since_s", "S 이후"))
    head = ["항목"] + [f"{arm} {w}" for arm in h1.ARMS for _, w in cols]

    def row(name, fn):
        return [name] + [fn(tr[k][arm]) for arm in h1.ARMS for k, _ in cols]

    rows = [row("주식 매수", lambda a: a["stock_buy"]), row("주식 매도", lambda a: a["stock_sell"]),
            row("  그중 상장폐지 정리", lambda a: a["delist"]),
            row("지수 매수(첫날 전부·쓸어 담기)", lambda a: a["idle_buy"]),
            row("지수 매도(주식 살 돈 마련)", lambda a: a["idle_sell"])]
    rows += [row(f"보류: {k}", lambda a, k=k: a["skips"].get(k, 0)) for k in SKIP_KINDS]
    rows.append(row("빈자리 부족(주문 못 낸 후보)", lambda a: a["over_slots"]))
    for kind, word in (("stock", "주식 다리"), ("idle", "지수 다리")):
        for k, kw in (("fee", "수수료"), ("slip", "슬리피지"), ("tax", "세금")):
            rows.append(row(f"비용 {word} {kw}", lambda a, kind=kind, k=k: _money(mk, a["cost"][kind][k])))
    L = ["## 5. 매매 · 보류 · 비용", ""]
    L += _table(head, rows)
    L += ["", "- 마라토너는 종목당 상한 30% × 5종목 = 150% 라서 4·5번째 매수는 늘 '현금 부족' 보류가 된다(team.py 그대로, R2 P6).",
          "- A1 은 주식을 살 때 모자란 만큼만 지수를 팔고, 남은 현금(1 이상)은 다시 지수로 산다(지수 다리 비용이 생김).", ""]
    return L


def _render_shadow(d):
    rows = [[f"{s['arm']} {s['trainer']}", s["first"] or "없음", s["why"] or "-", s["days"]] for s in d["shadow"]]
    L = [f"## 6. 그림자 서킷 (S ~ {d['cut']}, 계산만 — 장부는 바뀌지 않음)", "",
         "켜져 있었다면 걸렸을지(누적 −10%·하루 −7%)를 매일 계산만 한 기록이다. 판정에 쓰지 않는다(사전 등록 ③).", ""]
    L += _table(["장부·트레이너", "첫 발동일", "사유(첫 발동)", "발동한 날 수"], rows)
    L.append("")
    return L


def _render_realized(d):
    mk = d["market"]
    r = d["realized"]
    final = d["kind"] == "final"
    head = ["장부·종류", "판정 창" if final else "그달"] + ([] if final else ["그해 누적(S 이후)"]) + ["S 이후", "매도 수"]
    rows = []
    for arm in h1.ARMS:
        for kind, word in (("stock", "주식"), ("idle", "지수")):
            a = r[arm][kind]
            if arm == "A0" and kind == "idle":
                continue
            rows.append([f"{arm} {word}", _money(mk, a["period"], True)] + ([] if final else [_money(mk, a["ytd"], True)])
                        + [_money(mk, a["since_s"], True), a["n"]])
    L = ["## 7. 실현손익 (참고값 — 장부 칸이 아니라 보고서 계산)", ""]
    if mk == "us":
        L += [f"> {US_TAX_NOTE}", ""]
    L += _table(head, rows)
    L += ["", "- 평균원가법: 산 돈(체결가·수수료 포함)의 평균을 원가로, 판 돈(수수료·세금 뺀 뒤)과의 차이를 실현손익으로 본다. "
          "분할은 수량만 바꾸고 원가 합은 그대로 둔다.",
          "- A1 은 주식을 살 때마다 지수를 조금씩 팔아서 지수 실현손익이 자주 생긴다(R2 한계 3).", ""]
    by = {k: v for k, v in r["A1"]["by_code"].items()}
    if by:
        L.append("- A1 주식 종목별(S 이후): " + ", ".join(f"{k} {_money(mk, v, True)}" for k, v in by.items()))
    by0 = r["A0"]["by_code"]
    if by0:
        L.append("- A0 주식 종목별(S 이후): " + ", ".join(f"{k} {_money(mk, v, True)}" for k, v in by0.items()))
    L.append("")
    return L


def _render_leader(d):
    ld = d["leader"]
    L = [f"## 8. 팀장 (S ~ {d['cut']}, 채점은 하지 않음)", ""]
    if ld["n"] == 0:
        L += ["- 이 기간 판정 기록이 없음(후보가 없었음).", ""]
    else:
        ratio = ld["ratio"] * 100
        L.append(f"- 판정 기록 {ld['n']}건 · LLM 정상 {ld['n'] - ld['fallback']} · 폴백(status ≠ ok) {ld['fallback']} "
                 f"→ 폴백 비율 {ratio:.1f}% ({ld['flag'] * 100:.0f}% 를 넘으면 '대표성 없음' 표시, 사전 등록 ⑧)")
        if ld["unrepresentative"]:
            L.append(f"- **팀장 판정 대표성 없음** — 폴백이 {ld['flag'] * 100:.0f}% 를 넘음(사전 등록 ⑧). 실패 사유는 아님.")
        L.append("")
        L += _table(["판정", "출처", "건수"], [[v, s, n] for (v, s), n in ld["by_verdict"].items()])
        L += ["", "- 상태별: " + ", ".join(f"{k} {v}" for k, v in ld["by_status"].items())]
    rows = [[arm] + [ld["effects"][arm][k] for k in EFFECTS] for arm in h1.ARMS]
    L += ["", "장부별 효과(하루 기록의 팀장 칸):", ""]
    L += _table(["장부"] + [EFFECT_WORD[k] for k in EFFECTS], rows)
    first = f"CLI {ld['first_cli'] or '모름'} · 모델 {ld['first_model'] or '모름'}"
    if ld["changes"]:
        ch = "; ".join(f"{c['date']} ({c['asked_at']}): CLI {c['from'][0] or '모름'} → {c['to'][0] or '모름'}, "
                       f"모델 {c['from'][1] or '모름'} → {c['to'][1] or '모름'}" for c in ld["changes"])
        L += ["", f"- CLI 버전·모델: 처음 {first}. 바뀐 날: {ch}"]
    else:
        L += ["", f"- CLI 버전·모델: {first} (바뀐 날 없음)" if ld["n"] else "- CLI 버전·모델: 기록 없음"]
    if ld["truncated"]:
        L.append(f"- 판정 기록 마지막 줄이 반쯤 쓰여 있음({ld['truncated']['bytes']}바이트) — 다음 run 이 잘라 냄")
    L.append("")
    return L


def _render_interest(d):
    mk = d["market"]
    it = d["interest"]
    rule_txt = ("미국: 하루 기록의 전 거래일(prev_cal_date) 날짜 이하 마지막 DTB3 값(STAGE0-A1, S 날도 같음)"
                if it["rule"] == "prev_day" else
                "국내: 그 달의 전달 1일(m−1월 1일) 이하 마지막 IR3TIB01KRM156N 값, 없는 달은 이월(STAGE0-A2)")
    mode = {"online": "인터넷에서 새로 받음", "offline": "오프라인(--offline): 받지 않고 저장본만 봄",
            "failed": "오프라인(받기 실패): 저장본만 봄"}[it["mode"]]
    L = ["## 9. A0 현금 + 단기금리 이자 (계산만)", ""]
    if not it["ok"]:
        L += [f"- 금리 자료 없음 → 계산 불가 ({it['why']} · {mode}). 나머지 절은 그대로다.", ""]
        return L
    L += [f"- 식: q_t = r_t / 100 / 252, I_t = I_(t−1) × (1 + q_t) + C_t × q_t (C_t = A0 세 트레이너 종가 현금 합, S 날부터). "
          "'A0+이자' = A0 평가액 + I_t.",
          f"- 금리 규칙: {rule_txt}.",
          f"- 금리 파일: {it['series']} ({it['path']}, {it['format']} 형식, {it['first_rate']} ~ {it['last_rate']}) · "
          f"받은 시각 {it['fetched_at'] or '기록 없음'} · {mode}",
          "- **근사**다: R2 A0 는 이자가 현금에 들어가 매수·서킷에 쓰이지만 여기서는 따로 쌓기만 한다. 금리는 보고서를 만들 때 가진 "
          "자료로 다시 계산한다(R2 와 같은 방식). 국내 월 금리는 발표가 1~2달 늦어 이월값이 섞이고, 나중에 다시 만들면 바뀔 수 있다.",
          ""]
    L += _table(["", "값"], [
        [f"{d['cut']} A0 평가액", _money(mk, it["a0"])],
        ["쌓인 이자 I (S 이후)", _money(mk, it["interest"])],
        ["그 기간 이자", _money(mk, it["interest_period"])],
        ["A0+이자", f"{_money(mk, it['a0_plus'])} ({_pct(it['ret_plus'])})"],
        ["A1 − (A0+이자)", _money(mk, it["a1_minus_plus"], True)],
    ])
    if it["missing_days"]:
        L += ["", f"- 금리 자료보다 앞선 날 {it['missing_days']}일은 0 으로 계산했다."]
    if it["carried_days"]:
        L += ["", f"- 자료 끝을 넘어 마지막 값을 이월한 날 {it['carried_days']}일"
              + (" (오프라인: 저장본 마지막 값 이월)" if it["mode"] != "online" else "")]
    if it["prev_mismatch"]:
        L += ["", f"- ※ 하루 기록 prev_cal_date 가 달력 앞 날짜와 다른 봉: {', '.join(it['prev_mismatch'])}"]
    L += ["", f"쓴 금리 날짜 ({d['period_start']} ~ {d['cut']}):", ""]
    rows = [[x["date"], x["key"], x["rate_date"] or "-", "-" if not math.isfinite(x["rate"]) else f"{x['rate']:.2f}%",
             _money(mk, x["interest"]), x["note"]] for x in it["table"]]
    L += _table(["봉", "기준 날짜", "쓴 금리 날짜", "연 %", "쌓인 이자", "비고"], rows)
    L.append("")
    return L


def _render_recheck(d):
    rc = d["recheck"]
    L = ["## 10. 장부 다시 점검 (저장 자료만으로 h1_check)", "",
         f"- check_ledger(A0·A1)·check_pair·check_decisions(HEAD 의 판정 기록 앞부분 지문) → **L 오류 {rc['n']}건**"
         + (f" ({', '.join(f'{k} {v}' for k, v in rc['codes'].items())})" if rc["codes"] else "") + " — 0 이어야 함",
         f"- 달력: calendar.jsonl 마지막 정상 줄({rc['calendar_at'] or '없음'})",
         "- 종목군 파일 지문(L22 일부): " + ("meta 와 같음" if rc["universe_ok"] else f"**다름** ({rc['universe_why']})"),
         "- 코드·환경 지문(L22 나머지)은 2절 '다른 지문으로 처리한 봉'에 있다(재현 통과 기록과 비교).",
         "- 오프라인으로는 다시 못 보는 점검: " + "; ".join(OFFLINE_CHECKS) + "."]
    for line in rc["list"]:
        L.append(f"  - {line}")
    L.append("")
    return L


def _render_extension(d):
    e = d.get("extension")
    if not d["complete"]:
        return []
    L = ["## 연장 기록 (S+62 뒤 — 판정에 쓰지 않음)", ""]
    if e is None:
        return L + ["- S+62 뒤에 처리한 봉이 아직 없음.", ""]
    mk = d["market"]
    L += [f"- {e['first']} ~ {e['last']} {e['n']}봉 · 늦은 봉 {e['late']} · L 오류(errors.jsonl) {e['l_errors']}",
          f"- A0 {_money(mk, e['A0']['value'])} (S+62 뒤 {_pct(e['A0']['ret_ext'])}) · "
          f"A1 {_money(mk, e['A1']['value'])} (S+62 뒤 {_pct(e['A1']['ret_ext'])})", ""]
    return L


# ============================ build · write · cli ============================

def build(market, month=None, final=False, root=None, online=True) -> str:
    """보고서 마크다운(잠금 아래에서 저장 자료만 읽음). online 이면 먼저 FRED 금리를 받아 저장본을 새로 한다."""
    return render(collect(market, month, final, root, online))


def report_name(market, data) -> str:
    return f"{data['market']}-final-{data['S']}.md" if data["kind"] == "final" else f"{data['market']}-{data['month']}.md"


def write(market, month=None, final=False, root=None, online=True) -> Path:
    """보고서를 state/h1/reports/<market>-<YYYY-MM>.md (--final 이면 <market>-final-<S>.md) 로 쓴다(같은 이름은 덮어씀).
    잠금 아래에서 읽고 쓴다. 장부·일지는 고치지 않는다."""
    mk = h1._mkey(market)
    root = h1._root(root)
    _need_market(mk, root)
    with h1.h1_lock(root):
        data = _collect_locked(mk, root, month, final, online)
        text = render(data)
        path = h1.h1_path(root, "reports", report_name(mk, data))
        h1._write_atomic(path, text.encode("utf-8"))
    return path


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def _parser():
    p = _Parser(prog="h1_report.py", description="H1 포워드 월간·최종 보고서 (저장된 장부만 읽음, 수익률은 기록만). "
                                                 "종료 코드: 0 정상 / 2 예상 밖·장부 손상 / 4 금리 받기 실패 / 5 잠금 / "
                                                 "8 장부 없음 / 9 인자 오류")
    p.add_argument("--market", choices=("us", "kr"))
    p.add_argument("--month", default=None, help="YYYY-MM (없으면 마지막 처리 봉의 달)")
    p.add_argument("--final", action="store_true", help="판정 창(S~S+62) 최종 보고서 — 운영 기준 ①~③ 통과/실패")
    p.add_argument("--offline", action="store_true", help="금리를 받지 않고 저장본만 사용")
    p.add_argument("--fetch-rates", action="store_true", help="FRED 금리만 받아 state/h1/rates/ 에 저장")
    return p


def cli(argv=None) -> int:
    try:
        a = _parser().parse_args(sys.argv[1:] if argv is None else argv)
        if a.fetch_rates and (a.month or a.final or a.offline):
            raise _UsageError("--fetch-rates 는 --month·--final·--offline 과 같이 쓰지 않아요")
        if not a.fetch_rates and a.market is None:
            raise _UsageError("--market us|kr 가 필요해요")
    except _UsageError as e:
        h1._say(f"h1_report.py: 명령 인자 오류 — {e}  (python h1_report.py -h)")
        return EXIT_USAGE
    try:
        if a.fetch_rates:
            root = h1._root(None)
            mks = [a.market] if a.market else ["us", "kr"]
            bad = []
            with h1.h1_lock(root):
                for mk in mks:
                    p = fetch_rates(SERIES[mk], h1.h1_path(root, "rates"))
                    info = rates_info(SERIES[mk], h1.h1_path(root, "rates"))
                    if p is None:
                        bad.append(SERIES[mk])
                        h1._say(f"[금리] {SERIES[mk]} 받기 실패 → 저장본 {'있음 (' + info['last'] + ' 까지)' if info['ok'] else '없음'}")
                    else:
                        h1._say(f"[금리] {SERIES[mk]} 받음 → {p} ({info['first']} ~ {info['last']}, 받은 시각 {info['fetched_at']})")
            return EXIT_FETCH if bad else EXIT_OK
        path = write(a.market, a.month, a.final, None, not a.offline)
        h1._say(f"[H1 {a.market}] 보고서: {path}")
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("- **"):
                h1._say(f"  {line[2:]}")
        return EXIT_OK
    except ReportError as e:
        h1._say(f"h1_report.py: {e}")
        return e.code
    except h1.H1Refused as e:
        h1._say(f"h1_report.py: 거절 — {e}")
        return e.code
    except KeyboardInterrupt:
        h1._say("h1_report.py: 사람이 멈춤(Ctrl-C)")
        return 130
    except Exception as e:                      # noqa: BLE001
        h1._say(f"h1_report.py: 예상 밖 오류 {type(e).__name__}: {e}")
        return EXIT_ERROR


if __name__ == "__main__":
    import h1_report as _me                     # h1.py 와 같은 이유: 모듈이 두 벌이 되지 않게
    sys.exit(_me.cli())
