"""
h1_report.py - H1 포워드 월간·최종 보고서 (설계 docs/h1-forward-design.md 3판 §3.8, F8, 단계 2c)
------------------------------------------------------------------
무엇을 하나 (주식 초보용 설명)
- H1 장부 두 개(A1 = 쉬는 돈을 지수에, A0 = 쉬는 돈을 현금에)가 그동안 어떻게 굴러갔는지 한 장으로 정리한다.
- **저장된 파일만** 읽는다: 장부 6개(HEAD.json 으로 엄격하게)·meta.json·HEAD.json·calendar.jsonl·판정 기록·
  runs/errors/restarts/changes.jsonl·금리 저장본. 시세는 다시 받지 않는다(하루 기록에 지수 시가·종가와 보유 종목 종가가 있음).
- 수익률·MDD·A1−A0 같은 숫자는 **기록만** 한다. 판정에 쓰지 않는다(사전 등록 ③⑨).
- `--final` 은 판정 창(S~S+62)을 다 처리한 뒤 운영 기준 ①~③ 의 통과/실패만 판정한다. S+62 전이면 판정하지 않고
  남은 봉 수만 적는다(마감까지 끝날 수 없음이 확실하거나 재시작 상한을 넘으면 그때도 "H1 포워드 실패").
  S+62 뒤에 처리한 봉은 '연장 기록'으로만 적는다.
- 월간 보고서는 지금 판정 창의 S 부터 그달 마지막 처리 봉까지를 본다.
  - **이 달 숫자(2~9절)는 그달 마지막 봉까지로 고정**: 값·비율·매매·그림자·실현손익·팀장·이자는 그 봉까지의 하루 기록·체결로,
    실행 일지(멈춤·관문 거절·L 오류·종료 코드 6 등)는 '그 실행이 처리하려던 봉'이 그달 안인 것만 센다. 그래서 다음 달 봉을
    더 처리한 뒤 지난달 보고서를 다시 만들어도 이 숫자는 같다. 처리하려던 봉을 아직 알 수 없는 줄(이번 달 마지막 저장 봉 뒤,
    달력 기록 없이 멈춘 실행)은 '어느 달인지 모름'으로 따로 센다.
  - **머리말의 HEAD 와 10절 다시 점검의 '만든 때' 부분은 보고서를 만든 때의 장부 전체 기준**이라, 봉이 더 쌓이면 바뀐다
    (10절은 그달 마지막 봉까지 날짜의 L 오류를 따로 적는다).
- 일지 줄이 어느 창의 것인지는 h1._in_window 그대로(그 창이 만들어진 뒤의 줄만) 세고, 같은 시각일 때는 그 창을 만든 start
  보다 먼저 시작한 실행의 줄을 뺀다(2c 검토 R-1). L 오류는 errors.jsonl 과 runs.jsonl 의 종료 코드 2 를 run_id 로 합쳐 센다(R-2).
- 장부·일지는 한 글자도 고치지 않는다. 쓰는 것은 보고서 파일(state/h1/reports/)과 금리 저장본(state/h1/rates/)뿐이다.
  같은 입력이면 같은 보고서(바이트까지)가 나온다 — 그래서 "만든 시각"은 넣지 않고, 기준은 HEAD(마지막 저장)로 적는다.

명령
  python h1_report.py --market us|kr [--month YYYY-MM] [--final] [--offline]
      → state/h1/reports/<market>-<YYYY-MM>.md  (--final 이면 <market>-final-<S>.md, 같은 이름이면 덮어씀)
      인터넷이 되면 먼저 FRED 금리를 받아 저장본을 새로 한다(--offline 이면 받지 않음).
  python h1_report.py --fetch-rates [--market us|kr]      FRED 금리만 받아 state/h1/rates/ 에 저장
  종료 코드: 0 정상 / 2 예상 밖 오류(코드 버그, 장부 파일 손상 L24 포함) / 4 환경 문제(OSError·MemoryError: 디스크·권한,
            또는 --fetch-rates 에서 금리를 못 받음 = 인터넷 문제) / 5 잠금 30분 초과 / 8 장부 없음 /
            9 명령 인자 오류(없는 달, --final 과 --month 같이 씀 등) / 130 사람이 멈춤(Ctrl-C)

함수(설계 §3.8). root=None 은 h1.H1_DIR(state/h1)을 뜻한다 — h1.py 와 같은 약속(부를 때의 값이라 시험에서 바꿔 끼울 수 있음).
  build(market, month=None, final=False, root=None, online=True) -> str     보고서 마크다운
  write(market, month=None, final=False, root=None, online=True) -> Path    파일로 저장(잠금 아래, 같은 이름은 덮어씀)
  collect(...) -> dict                                                       보고서 숫자 묶음(시험·재현용)
  fetch_rates(series_id, cache_dir, timeout=20) -> Path | None              FRED 받기(표준 라이브러리 urllib)
  load_rates(series_id, cache_dir) -> pd.Series | None                     FRED 원본·R2 형식 둘 다, "." 은 빈값
  rate_for_days(dates, series, rule) -> list[float]                         R2 sim_team.rate_for_days 와 같은 규칙·같은 값
  interest_overlay(dates, cash, rate_pct) -> list[float]                    I_t = I_{t−1}·(1+q_t) + C_t·q_t
  a0_interest(market, states, series, upto=None) -> dict                    장부로 A0 현금 이자(날마다 금리·이자) — 재현 M7
  realized(fills, corp_actions=None) -> dict                                 평균원가법 실현손익(주식/지수 따로)
  index_buy_hold_same_start(opens, closes, total, fee_rate, slippage) -> dict
      지수 B&H(같은 시작) — R2 index_buy_hold_fractional(md, i0+1, i1, total) 와 같은 식
  index_bh_from_states(market, states, upto=None) -> dict                   장부 하루 기록으로 지수 B&H 매일 값 — 재현 M6
  cli(argv=None) -> int

재현(단계 5)에서 R2 와 맞출 때 쓰는 것
  M6: index_bh_from_states(…)["values"][1:] 를 R2 index_buy_hold_fractional(md, i0+1, i1, total)["equity"] 와
      (마지막 날만 R2 가 매도 비용을 뺀 값이라 units × 그날 종가로) 비교. 단위는 정확히 같음(같은 식·같은 계산 순서).
  M7: a0_interest(…) 의 rates 를 R2 sim_team.rate_for_days(같은 달력, 같은 금리 파일)[i0:i1+1] 과, interest 를 같은 식으로
      따로 계산한 값과 비교.

import 관계: h1_report → h1·h1_check·markets·metrics. h1 은 h1_report 를 import 하지 않는다.
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
import traceback
import urllib.request
from collections import Counter
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import h1
import h1_check
import markets
import metrics

# ============================ 상수 ============================

SERIES = {"us": "DTB3", "kr": "IR3TIB01KRM156N"}          # F8: 미국 3개월 T-bill(일별), 국내 3개월 은행간 금리(월별)
RULE = {"us": "prev_day", "kr": "prev_month"}             # STAGE0-A1 전 거래일 / STAGE0-A2 전달
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
R2_RATE_NAMES = {"DTB3": "us_tbill.csv", "IR3TIB01KRM156N": "kr_shortrate.csv"}   # R2 data/rates 의 파일 이름
DAYS_PER_YEAR = 252                                       # B4: 거래일마다 연% / 100 / 252

EXIT_OK = 0
EXIT_ERROR = 2          # 예상 밖 오류(코드 버그), 장부 파일 손상(L24)
EXIT_ENV = 4            # 환경 문제(OSError·MemoryError: 디스크 가득·권한·입출력) — h1.py 의 ENV 와 같은 번호
EXIT_FETCH = EXIT_ENV   # --fetch-rates 에서 금리를 못 받음(인터넷 문제 = 환경 문제)
EXIT_LOCK = 5
EXIT_NO_LEDGER = 8
EXIT_USAGE = 9
EXIT_INTERRUPT = 130

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
CHANGE_WORD = {"replay-pass": "재현 통과 기록 추가(코드·환경 변경)", "amend-rules(done)": "세율 줄 추가",
               "false_positive": "점검 함수 거짓 양성 판정(사전 등록 ④)",
               "amend-rules(abandoned)": "세율 줄 추가 취소(커밋 전에 꺼짐)",
               "corp-action:split": "기업 행위 분할", "corp-action:delist": "기업 행위 상장폐지",
               "corp-action:correction": "기업 행위 정정 확정"}
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
    """금리 저장본 상태: {"ok", "series"(pd.Series|None), "path", "format", "first", "last", "rows", "fetched_at", "why",
    "skipped"}. 저장본은 <ID>.csv → R2 이름(us_tbill.csv·kr_shortrate.csv) 순서로 찾고, 깨진 파일은 건너뛰고 다음 것을 쓴다
    (건너뛴 까닭은 "skipped" 에). fetched_at 은 저장본 옆 <ID>.json 에 적힌 받은 시각(없으면 None — 예: R2 형식 복사본)."""
    skipped = []
    for p in _rate_paths(series_id, cache_dir):
        if not p.is_file():
            continue
        try:
            items, fmt = _parse_rates(p.read_bytes().decode("utf-8-sig"), series_id)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            skipped.append(f"{p.name}: 깨짐({type(e).__name__}: {e})")
            continue
        if not items:
            skipped.append(f"{p.name}: 값이 하나도 없음")
            continue
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
                "source": meta.get("url") if isinstance(meta, dict) else None, "why": None, "skipped": skipped}
    why = "금리 저장본이 없음" if not skipped else "쓸 수 있는 금리 저장본이 없음 — " + "; ".join(skipped)
    return {"ok": False, "series": None, "path": None, "why": why, "skipped": skipped}


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


def _team_rows(states, arm, upto=None, start=None) -> list:
    """장부(arm) 세 트레이너 합의 매일 값 [{date, value, cash, stock_value, idle_value, idle_units}].
    날짜는 첫 트레이너의 하루 기록 순서(start ≤ 날짜 ≤ upto). 세 트레이너 모두 기록이 있는 날만(빠지면 L16 이 잡는다)."""
    per = [{r["date"]: r for r in states[arm][tn]["days"]} for tn in h1.TRAINERS]
    out = []
    for r0 in states[arm][h1.TRAINERS[0]]["days"]:
        d = r0["date"]
        if (upto is not None and d > upto) or (start is not None and d < start):
            continue
        rows = [p.get(d) for p in per]
        if any(r is None for r in rows):
            continue
        out.append({"date": d, **{k: sum(r[k] for r in rows)
                                  for k in ("value", "cash", "stock_value", "idle_value", "idle_units")}})
    return out


def a0_interest(market, states, series, upto=None) -> dict:
    """A0 현금 + 단기금리 이자(계산만, 설계 §3.8-9) — 저장된 장부 states = {arm: {trainer: st}} 와 금리 Series 로.
    재현 M7 은 이 함수의 rates 를 R2 sim_team.rate_for_days(같은 달력·같은 금리 파일)와, interest 를 같은 식으로
    따로 계산한 값과 비교한다.
    - 달력 = A0 세 트레이너의 하루 기록 날짜(S ~ upto).
    - 미국(prev_day): 그날 금리 = 전 거래일 날짜 이하 마지막 DTB3. S 날의 전 거래일은 하루 기록 prev_cal_date(저장 달력의
      S 전 거래일)라서 [prev_cal_date(S)] + 달력 으로 rate_for_days 를 부르고 첫 값을 버린다(= R2 전체 달력의 그 구간).
    - 국내(prev_month): 그 달의 전달 1일 이하 마지막 값(없는 달은 이월).
    - C_t = A0 세 트레이너 그날 종가 현금 합(S 날 = 시작 금액 전부), I_t = I_{t−1}·(1+q_t) + C_t·q_t.
    돌려줌: {"rule", "dates", "keys"(금리를 찾은 기준 날짜), "rate_dates"(실제로 쓴 금리 날짜, 없으면 None),
             "rates"(연 %, 없으면 NaN → 이자 0), "cash", "interest"(I_t), "prev_mismatch"(prev_cal_date ≠ 달력 앞 날짜인 봉)}"""
    mk = h1._mkey(market)
    rule = RULE[mk]
    team0 = _team_rows(states, "A0", upto)
    dates = [r["date"] for r in team0]
    by = {r["date"]: r for r in states["A0"][h1.TRAINERS[0]]["days"]}
    if not dates:
        return {"rule": rule, "dates": [], "keys": [], "rate_dates": [], "rates": [], "cash": [], "interest": [],
                "prev_mismatch": []}
    bad_prev = []
    if rule == "prev_day":
        prev0 = by[dates[0]].get("prev_cal_date")
        if prev0 is None:                               # (일어나지 않아야 함) S 전 거래일을 모름 → S 날 금리 없음
            match = rate_match(dates, series, rule)
            rates = rate_for_days(dates, series, rule)
        else:
            cal = [prev0] + dates
            match = rate_match(cal, series, rule)[1:]
            rates = rate_for_days(cal, series, rule)[1:]
        bad_prev = [d for d, (k, _, _) in zip(dates, match) if k != by[d].get("prev_cal_date")]
    else:
        match = rate_match(dates, series, rule)
        rates = rate_for_days(dates, series, rule)
    cash = [r["cash"] for r in team0]
    return {"rule": rule, "dates": dates, "keys": [k for k, _, _ in match], "rate_dates": [g for _, g, _ in match],
            "rates": rates, "cash": cash, "interest": interest_overlay(dates, cash, rates), "prev_mismatch": bad_prev}


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


def index_bh_from_states(market, states, upto=None) -> dict:
    """저장된 장부의 하루 기록(지수 시가·종가 idle_open·idle_close)으로 지수 B&H(같은 시작) 매일 값 — 시세를 다시 받지 않는다.
    총액 = A1 세 트레이너 시작 금액 합, 비용 = A1 지갑의 수수료·슬리피지(= markets 값). 재현 M6 이 쓴다.
    돌려줌: index_buy_hold_same_start 결과 + "dates"(S ~ upto)."""
    h1._mkey(market)                                     # 모르는 시장이면 ValueError
    rows = [r for r in states["A0"][h1.TRAINERS[0]]["days"] if upto is None or r["date"] <= upto]
    w = h1._plain_wallet(states["A1"][h1.TRAINERS[0]]["wallet"])
    total = sum(states["A1"][tn]["start_cash"] for tn in h1.TRAINERS)
    out = index_buy_hold_same_start([r["idle_open"] for r in rows], [r["idle_close"] for r in rows], total,
                                    w["fee_rate"], w["slippage"])
    out["dates"] = [r["date"] for r in rows]
    return out


# ============================ 읽기 ============================

class _Ctx:
    """한 시장의 저장 자료(읽기만)."""

    def __init__(self, mk, root, loaded, decisions, cal_line, logs, broken, cal_lines):
        self.mk, self.root = mk, root
        self.meta, self.head, self.states = loaded.meta, loaded.head, loaded.states
        self.S = self.meta["start_date"]
        self.created_at = self.meta.get("created_at")
        self.rules = dict(self.meta.get("rules") or {})
        self.decisions = decisions
        self.cal_line = cal_line
        self.runs, self.errors = logs["runs.jsonl"], logs["errors.jsonl"]
        self.changes, self.restart_lines = logs["changes.jsonl"], logs["restarts.jsonl"]
        self.broken = broken                           # 일지마다 읽지 못한(깨진) 줄 수
        self.cal_by_run = {r.get("run_id"): r for r in cal_lines if r.get("run_id")}
        self.canon = self.states["A0"][h1.TRAINERS[0]]["days"]
        self.dates = [r["date"] for r in self.canon]
        self.m = markets.MARKETS[mk]
        self._journal = None
        self.pre_runs = self._pre_window_runs()

    def rule(self, key, default):
        v = self.rules.get(key)
        return default if v is None else v

    def _pre_window_runs(self) -> set:
        """이 창을 만든(마지막으로 성공한 같은 S 의) start 실행보다 runs.jsonl 에서 먼저 시작한 실행들의 run_id.
        시각이 같아 created_at 으로 가를 수 없을 때(시계가 거칠거나 같은 분에 다시 친 start)를 위한 보충 — 이 실행들의 줄은
        창 밖이다(2c 검토 R-1)."""
        idx = {}
        creator = None
        for i, r in enumerate(self.runs):
            rid = r.get("run_id")
            if r.get("market") != self.mk or not rid:
                continue
            idx.setdefault(rid, i)
            if r.get("event") == "end" and r.get("command") == "start" and r.get("exit_code") == h1.EXIT_OK \
                    and r.get("start_date") == self.S:
                creator = rid
        if creator is None:
            return set()
        return {rid for rid, i in idx.items() if i < idx[creator]}

    def inwin(self, r) -> bool:
        """이 시장·이 판정 창의 일지 줄인가: h1._in_window(창이 만들어진 뒤의 줄만, 2c 검토 R-1) + 이 창을 만든 start 보다
        먼저 시작한 실행의 줄은 뺀다(같은 시각일 때의 보충)."""
        return r.get("market") == self.mk and h1._in_window(r, self.S, self.created_at) \
            and r.get("run_id") not in self.pre_runs


JOURNALS = ("runs.jsonl", "errors.jsonl", "changes.jsonl", "restarts.jsonl")


def _read_counted(path) -> tuple:
    """일지 JSONL 을 h1.read_jsonl 처럼 너그럽게 읽되, 건너뛴(깨진·dict 아닌) 줄 수도 센다 → (기록 목록, 깨진 줄 수)."""
    p = Path(path)
    if not p.exists():
        return [], 0
    out, bad = [], 0
    for raw in p.read_bytes().split(b"\n"):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            bad += 1
            continue
        if isinstance(rec, dict):
            out.append(rec)
        else:
            bad += 1
    return out, bad


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
    logs, broken = {}, {}
    for name in JOURNALS:
        logs[name], broken[name] = _read_counted(h1.h1_path(root, name))
    cal_lines, broken["calendar.jsonl"] = _read_counted(h1.h1_path(root, mk, "calendar.jsonl"))
    return _Ctx(mk, root, loaded, decisions, h1._last_ok_calendar_line(root, mk), logs, broken, cal_lines)


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
    return _team_rows(c.states, arm, upto, start)


def _rows(c, arm, tn, upto, start=None):
    return [r for r in c.states[arm][tn]["days"] if r["date"] <= upto and (start is None or r["date"] >= start)]


def _ret(v, base):
    return None if base in (None, 0) or v is None else v / base - 1


def _mdd(values):
    return metrics.max_drawdown(values) if values else None


# ============================ 운영 기준 (§3.8-2) ============================

def _saved_at(c, bar):
    """봉 bar 를 저장한 때. 그 봉을 저장한 실행(run·start)의 runs.jsonl 끝 줄 시각, 끝 줄이 없으면(커밋 뒤 kill·전원 꺼짐)
    HEAD 로 보호되는 그 봉 하루 기록의 run_at(그 봉을 처리한 실행 시각, 2c 검토 R-3). 둘 다 없으면 None."""
    for r in c.runs:                    # bars 에는 커밋한 봉만 적힌다(그 뒤 다른 봉에서 멈췄어도) → 종료 코드는 보지 않음
        if r.get("event") == "end" and bar in (r.get("bars") or []) and c.inwin(r):
            return r.get("at")
    return next((r.get("run_at") for r in c.canon if r["date"] == bar), None)


def _order_key(at, sub, i):
    """일지 줄 순서 열쇠: 시각(시간대 있음) → 같은 시각이면 sub → 파일 순서. 시각을 못 읽으면 맨 뒤(파일 순서)."""
    try:
        t = datetime.fromisoformat(at)
        if t.tzinfo is not None:
            return (0, t.timestamp(), sub, i)
    except (TypeError, ValueError):
        pass
    return (1, 0.0, sub, i)


def _journal(c) -> dict:
    """이 창의 실행 일지를 시간 순서로 걸으며 일마다 '그때 마지막으로 저장된 봉(base)'과 '처리하려던 봉(target)'을 정한다
    (2c 검토 R-2·R-3·R-5). 봉이 없는 실행 줄(자료 멈춤·관문 거절·종료 코드 6·날짜 없는 L·잠금 초과·끝 줄 없는 실행)을
    어느 봉의 일로 셀지 정하는 데 쓴다 — 시각이 아니라 '그 실행이 처리하려던 봉'으로 판정 창(S+62)·달을 나눈다.
    - 저장된 봉: runs.jsonl 끝 줄의 bars. 끝 줄이 없는 봉은 하루 기록 run_at 의 때(그 시각 이전의 마지막 끝 줄 없는 시작 줄
      바로 뒤)에 저장된 것으로 본다.
    - target: base 보다 뒤인 날짜 중 (1) 그 실행 일지의 D·L 문제 날짜 (2) 그 실행의 calendar.jsonl 줄 날짜 목록
      (3) 장부 하루 기록 날짜(다음에 저장된 봉 = 달력의 다음 거래일, L16) 에서 가장 이른 것. 셋 다 없으면 None(모름)."""
    if c._journal is not None:
        return c._journal
    mk = c.mk
    end_ids = {r.get("run_id") for r in c.runs if r.get("event") == "end" and r.get("run_id")}
    evs = []
    covered = set()
    for i, r in enumerate(c.runs):
        if not c.inwin(r):
            continue
        kind = {"end": "end", "lock_timeout": "lock"}.get(r.get("event"))
        if r.get("event") == "start" and r.get("run_id") not in end_ids:
            kind = "orphan"                                   # 시작 줄만 있고 끝 줄이 없음(kill·전원 꺼짐)
        if kind is None:
            continue
        ev = {"kind": kind, "rec": r, "run_id": r.get("run_id"), "key": _order_key(r.get("at"), 0, i),
              "bars": list(r.get("bars") or []) if kind == "end" else []}
        if kind == "end":
            covered |= set(ev["bars"])
        evs.append(ev)
    for i, r in enumerate(c.errors):
        if c.inwin(r) and any(isinstance(p, dict) and p.get("level") == "L" for p in r.get("problems") or []):
            evs.append({"kind": "error", "rec": r, "run_id": r.get("run_id"), "key": _order_key(r.get("at"), 0, i),
                        "bars": []})
    orphans = sorted((e for e in evs if e["kind"] == "orphan" and e["rec"].get("command") in ("run", "start")),
                     key=lambda e: e["key"])
    for row in c.canon:                                      # 끝 줄 없이 저장된 봉(커밋 뒤 꺼진 실행)
        d = row["date"]
        if d in covered:
            continue
        rk = _order_key(row.get("run_at"), 0, 0)
        host = [o for o in orphans if o["key"][:2] <= rk[:2]] if rk[0] == 0 else []
        key = (host[-1]["key"][:3] + (host[-1]["key"][3] + 0.5,)) if host else _order_key(row.get("run_at"), 1, 0)
        evs.append({"kind": "save", "rec": {}, "run_id": None, "key": key, "bars": [d]})
    evs.sort(key=lambda e: e["key"])
    last = None
    for ev in evs:
        ev["before"] = last
        if ev["kind"] in ("end", "save") and ev["bars"]:
            last = max([x for x in (last,) if x] + ev["bars"])
        ev["base"] = max(ev["bars"]) if ev["kind"] == "end" and ev["bars"] else ev["before"]
    by_run = {}
    for ev in evs:
        if ev["kind"] in ("end", "orphan") and ev["run_id"]:
            by_run.setdefault(ev["run_id"], ev)
    for ev in evs:
        if ev["kind"] != "save":
            ev["target"] = _target(c, ev)
    for ev in evs:                                           # L 기록: 봉 날짜가 있으면 그 날짜, 없으면 그 실행의 봉
        if ev["kind"] == "error":
            date = ev["rec"].get("date")
            run = by_run.get(ev["run_id"])
            if isinstance(date, str) and date:
                ev["target"], ev["base"] = date, (run or ev)["base"]
            elif run is not None:
                ev["target"], ev["base"] = run["target"], run["base"]
    outside = [r for r in c.errors + [x for x in c.runs if x.get("event") in ("end", "lock_timeout")]
               if r.get("market") == mk and r.get("start_date") == c.S and not c.inwin(r)]
    c._journal = {"events": [e for e in evs if e["kind"] != "save"], "by_run": by_run, "outside": len(outside)}
    return c._journal


def _target(c, ev):
    base = ev["base"]
    if base is None:
        return None
    rec = ev["rec"]
    found = [p.get("date") for p in rec.get("problems") or []
             if isinstance(p, dict) and p.get("level") in ("D", "L") and isinstance(p.get("date"), str)
             and p.get("date") > base]
    if found:
        return min(found)
    cl = c.cal_by_run.get(ev["run_id"]) if ev["run_id"] else None
    if cl is not None:
        nxt = [d for d in cl.get("dates") or [] if isinstance(d, str) and d > base]
        if nxt:
            return min(nxt)
    return next((d for d in c.dates if d > base), None)


def _scope(ev, B, unknown_in) -> str:
    """일 ev 가 보고서 범위(처리하려던 봉 ≤ B)에 드는가: "in" / "out" / "unknown"(어느 봉의 일인지 모름).
    target 을 모르면: 그때 마지막 저장 봉이 이미 B 이상이면 B 뒤의 일(out), 아니면 unknown_in 에 따라 in/unknown."""
    t = ev["target"]
    if t is not None:
        return "in" if t <= B else "out"
    if ev["base"] is not None and ev["base"] >= B:
        return "out"
    return "in" if unknown_in else "unknown"


def _l_events(c, J) -> list:
    """②-1 L 오류(2c 검토 R-2): errors.jsonl 의 L 줄과 runs.jsonl 끝 줄 중 종료 코드 2 인 실행을 run_id 로 합친 합집합.
    (errors.jsonl 줄이 반쯤 쓰였거나 쓰기에 실패해도 runs.jsonl 의 종료 코드 2 로 잡는다.) 시작 줄만 있고 끝 줄이 없는
    실행은 L 로 세지 않는다(따로 '끝 기록 없는 실행')."""
    out = {}
    for ev in J["events"]:
        if ev["kind"] == "error":
            k = ev["run_id"] or f"error#{id(ev)}"
            e = out.setdefault(k, {"run_id": ev["run_id"], "target": ev["target"], "base": ev["base"], "codes": set(),
                                   "src": set(), "at": ev["rec"].get("at")})
            e["codes"] |= {str(p.get("code")) for p in ev["rec"].get("problems") or []
                           if isinstance(p, dict) and p.get("level") == "L"}
            e["src"].add("errors")
            if e["target"] is None:
                e["target"], e["base"] = ev["target"], ev["base"]
    for ev in J["events"]:
        if ev["kind"] == "end" and ev["rec"].get("exit_code") == h1.EXIT_LOGIC:
            k = ev["run_id"] or f"end#{id(ev)}"
            e = out.get(k)
            if e is None:
                out[k] = {"run_id": ev["run_id"], "target": ev["target"], "base": ev["base"],
                          "codes": {"(errors.jsonl 기록 없음 — 종료 코드 2)"}, "src": {"runs"}, "at": ev["rec"].get("at")}
            else:
                e["src"].add("runs")
    fps = {(r.get("error_run_id"), r.get("bar")) for r in c.changes
           if r.get("kind") == "false_positive" and r.get("market") == c.mk}
    for e in out.values():
        e["false_positive"] = bool(e["run_id"]) and (e["run_id"], e["target"]) in fps
    return list(out.values())


def _restart_info(c) -> dict:
    """재시작 수(2c 검토 R-7) = 셋 중 가장 큰 값: meta.restart_no(HEAD 로 보호), restarts.jsonl 의 restart_id 중
    'done' 이거나 보관 폴더가 실제로 있는 것, archive/<시장>-* 폴더 수. 셋이 다르면 경고.
    지금 창을 옮기려던 'moving' 줄(보관 폴더 없음, 시장 폴더 그대로)은 재시작으로 세지 않고 '끝나지 않은 restart 기록'."""
    groups = {}
    for r in c.restart_lines:
        if r.get("market") != c.mk:
            continue
        g = groups.setdefault(h1._restart_id(r), {"recs": []})
        g["recs"].append(r)
        for k in ("at", "reason", "old_start", "old_last", "restart_no", "archive"):
            if g.get(k) is None and r.get(k) is not None:
                g[k] = r.get(k)
    counted, pending = [], []
    for g in groups.values():
        done = any(r.get("status", "done") == "done" for r in g["recs"])
        try:
            arch = bool(g.get("archive")) and h1._archive_path(c.root, g).exists()
        except (h1.H1Refused, ValueError):
            arch = False
        g["done"] = done
        (counted if done or arch else pending).append(g)
    adir = h1.h1_path(c.root, "archive")
    n_arch = sum(1 for x in adir.iterdir() if x.is_dir() and x.name.startswith(f"{c.mk}-")) if adir.is_dir() else 0
    meta_n = c.meta.get("restart_no")
    meta_n = meta_n if isinstance(meta_n, int) and not isinstance(meta_n, bool) else 0
    sources = {"meta.restart_no": meta_n, "restarts.jsonl": len(counted), "archive 폴더": n_arch}
    return {"used": max(sources.values()), "sources": sources, "mismatch": len(set(sources.values())) > 1,
            "list": [{k: g.get(k) for k in ("at", "reason", "old_start", "old_last", "done")} for g in counted],
            "pending": [{k: g.get(k) for k in ("at", "reason", "old_start", "old_last")} for g in pending]}


def _ops(c, bar_upto, B, unknown_in, end_at, allowed, allowed_why):
    """운영 기준 칸. bar_upto = 하루 기록을 볼 마지막 봉. 일지 줄은 '처리하려던 봉 ≤ B' 인 것만 센다(_journal·_scope):
    최종 = S+62(다 찼을 때), 월간 = 그달 마지막 날. unknown_in = 어느 봉의 일인지 모르는 줄을 넣을지(아니면 따로 셈).
    end_at = 변경 일지·기업 행위의 시각 상한(그 봉을 저장한 때)."""
    mk, S = c.mk, c.S

    def in_time(r):
        return end_at is None or _le_time(r.get("at"), end_at)

    dates = [d for d in c.dates if d <= bar_upto]
    out = {"n_bars": len(dates), "window_bars": int(c.rule("window_bars", h1.WINDOW_BARS)), "first": S,
           "last": dates[-1] if dates else None, "bound": B}
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
    # 실행 일지: 이 창(h1._in_window) + 처리하려던 봉이 범위(≤ B) 안인 것
    J = _journal(c)
    unknown = Counter()

    def pick(evs, label):
        got = []
        for ev in evs:
            sc = _scope(ev, B, unknown_in)
            if sc == "in":
                got.append(ev)
            elif sc == "unknown":
                unknown[label] += 1
        return got

    ends = [ev for ev in J["events"] if ev["kind"] == "end"]
    procs = [ev for ev in ends if ev["rec"].get("command") in ("run", "start") and ev["bars"]]
    out["batch_max"] = max((len(ev["bars"]) for ev in procs if any(b <= B for b in ev["bars"])), default=0)
    code = lambda ev: ev["rec"].get("exit_code")   # noqa: E731
    out["backlog_fail"] = len(pick([ev for ev in ends if code(ev) == h1.EXIT_BACKLOG], "밀린 봉 초과(6)"))
    out["gate_refused"] = len(pick([ev for ev in ends if code(ev) == h1.EXIT_GATE], "관문 거절(3)"))
    stops = pick([ev for ev in ends if code(ev) in (h1.EXIT_DATA, h1.EXIT_D7)], "자료 멈춤(4·7)")
    out["data_stops"] = len(stops)

    def kinds_of(ev):
        ks = sorted({str(p.get("code")) for p in ev["rec"].get("problems") or []
                     if isinstance(p, dict) and p.get("level") == "D"})
        return ks or ["(종류 없음)"]
    out["data_kinds"] = dict(sorted(Counter(k for ev in stops for k in kinds_of(ev)).items()))
    out["data_by_exit"] = {x: {"n": sum(1 for ev in stops if code(ev) == x),
                               "kinds": dict(sorted(Counter(k for ev in stops if code(ev) == x
                                                            for k in kinds_of(ev)).items()))}
                           for x in (h1.EXIT_DATA, h1.EXIT_D7)}
    out["lock_timeouts"] = len(pick([ev for ev in J["events"] if ev["kind"] == "lock"], "잠금 초과(5)"))
    out["no_end"] = len(pick([ev for ev in J["events"] if ev["kind"] == "orphan"], "끝 기록 없는 실행"))
    # ②-1 L 오류: errors.jsonl ∪ runs.jsonl 종료 코드 2 (run_id 로 한 번), 사전 등록 ④ 거짓 양성 판정은 빼고 따로
    lev = []
    for e in _l_events(c, J):
        sc = _scope(e, B, unknown_in)
        if sc == "unknown":
            unknown["장부 논리 오류(L)"] += 1
        elif sc == "in":
            lev.append(e)
    errs = [e for e in lev if not e["false_positive"]]
    out["l_errors"] = len(errs)
    out["l_false_positive"] = len(lev) - len(errs)
    out["l_codes"] = dict(sorted(Counter(k for e in errs for k in e["codes"]).items()))
    out["l_runs_only"] = sum(1 for e in errs if e["src"] == {"runs"})
    out["l_list"] = [(e["at"], e["target"], ", ".join(sorted(e["codes"]))) for e in errs]
    out["unknown"] = dict(sorted(unknown.items()))
    out["outside"] = J["outside"]
    out["broken"] = {k: v for k, v in c.broken.items() if v}
    # 다른 지문으로 처리한 봉 (②-3): 하루 기록·실행 일지의 (code_hash, env) 가 재현 통과 기록에 없음
    bad_rows = sorted({r["date"] for arm in h1.ARMS for tn in h1.TRAINERS for r in _rows(c, arm, tn, bar_upto)
                       if allowed is None or (r.get("code_hash"), h1.env_key(r.get("env"))) not in allowed})
    bad_runs = sorted({b for ev in procs for b in ev["bars"] if b <= B and b <= bar_upto
                       and (allowed is None or (ev["rec"].get("code_hash"), h1.env_key(ev["rec"].get("env")))
                            not in allowed)})
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
    # 재시작(R-7) · 코드 변경 일지 · 기업 행위
    rs = _restart_info(c)
    out["restarts"], out["restarts_pending"] = rs["list"], rs["pending"]
    out["restarts_used"], out["restart_sources"], out["restart_mismatch"] = rs["used"], rs["sources"], rs["mismatch"]
    max_rs = int(c.rule("max_restarts", h1.MAX_RESTARTS))
    out["max_restarts"] = max_rs
    out["restarts_left"] = max(0, max_rs - out["restarts_used"])
    ch_all = [r for r in c.changes if (r.get("market") in (mk, None)) and (c.created_at is None
                                                                             or not _le_time(r.get("at"), c.created_at))]
    ch = [r for r in ch_all if in_time(r)]
    out["changes_after"] = len(ch_all) - len(ch)
    # 변경 일지: 같은 일의 의도 줄(pending)·끝 줄(done/abandoned)은 한 번으로(run_id), 종류별로 센다
    seen_ch, kinds = set(), Counter()
    for r in ch:
        kind = str(r.get("kind"))
        if kind == "amend-rules":
            kind = f"amend-rules({r.get('status')})"
            if r.get("status") == "pending":
                continue                                   # 끝 줄(done·abandoned)만 센다(C-7 이 빠진 끝 줄을 채움)
        key = (kind, r.get("run_id")) if r.get("run_id") else (kind, json.dumps(r, sort_keys=True, ensure_ascii=False))
        if key in seen_ch:
            continue
        seen_ch.add(key)
        kinds[kind] += 1
    out["changes"] = dict(sorted(kinds.items()))
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
    bh = index_bh_from_states(c.mk, c.states, cut)
    before = [v for d, v in zip(bh.pop("dates"), bh["values"]) if mstart is not None and d < mstart]
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
             "skips": {k: 0 for k in SKIP_KINDS}, "over_slots": 0, "marathon_short": 0,
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
                    if tn == h1.TRAINERS[0] and s["kind"] == "현금부족":
                        a["marathon_short"] += 1
            a["over_slots"] += sum(r.get("over_slots") or 0 for r in _rows(c, arm, tn, cut, start))
        out[arm] = a
    return out


def _shadow_desc(start_cash, prev, value) -> str:
    """그림자 서킷이 걸린 날의 쉬운 설명(risk_guard 와 같은 순서: 누적 먼저, 그다음 하루)."""
    cum_lim, day_lim = h1.SHADOW_BREAKER
    cum = value / start_cash - 1 if start_cash else 0.0
    if cum <= -cum_lim:
        what = f"누적 {cum * 100:.1f}%(한도 -{cum_lim * 100:.0f}%)"
    else:
        day = value / prev - 1 if prev else 0.0
        what = f"하루 {day * 100:.1f}%(한도 -{day_lim * 100:.0f}%)"
    return what + " — 서킷이 켜져 있었다면 멈췄을 날(실제로는 팔거나 멈추지 않음)"


def _shadow(c, cut):
    """그림자 서킷: (장부, 트레이너)별 첫 발동일·사유·발동한 날 수 (S ~ cut). why = 장부에 적힌 risk_guard 문구 그대로,
    desc = 보고서용 쉬운 설명(그날 평가액으로 다시 계산한 누적·하루 변화)."""
    out = []
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            rows = _rows(c, arm, tn, cut)
            hits, prev = [], None
            for r in rows:
                for e in r.get("events") or []:
                    if e.get("kind") == "shadow_breaker":
                        hits.append((r["date"], e, prev, r["value"]))
                prev = r["value"]
            days = sorted({d for d, _, _, _ in hits})
            first = hits[0] if hits else None
            sc = c.states[arm][tn]["start_cash"]
            out.append({"arm": arm, "trainer": tn, "first": first[0] if first else None,
                        "why": first[1].get("why") if first else None,
                        "desc": _shadow_desc(sc, first[2], first[3]) if first else None, "days": len(days),
                        "flag_first": next((d for d, e, _, _ in hits if e.get("first")), None)})
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


def _window_keys(c, start, cut) -> set:
    """이 창이 실제로 쓴 판정 기록 열쇠 = 두 장부 하루 기록(start ~ cut)의 팀장 칸(leader)에 적힌 열쇠."""
    return {e.get("key") for arm in h1.ARMS for tn in h1.TRAINERS for r in _rows(c, arm, tn, cut, start)
            for e in r.get("leader") or [] if e.get("key")}


def _leader(c, start, cut):
    """팀장 판정 기록(이 창이 start ~ cut 에 쓴 것): 판정 × 출처, 상태별, 폴백 비율(⑧), 장부별 효과, CLI 버전·모델이 바뀐 날.
    '창의 판정 기록' = 하루 기록의 팀장 칸이 가리키는 기록(파일 순서 = 물은 순서). 같은 날짜 범위에 있어도 이 창이 쓰지 않은
    기록(재시작 전 창의 것, 저장되지 못한 봉의 것)은 세지 않고 수만 따로 적는다. 늦은 봉 폴백(late_no_llm)도 센다."""
    keys = _window_keys(c, start, cut)
    in_range = [r for r in c.decisions.records() if r.get("market") == c.mk and start <= str(r.get("date")) <= cut]
    recs = [r for r in c.decisions.records() if r.get("key") in keys]
    n = len(recs)
    fb = sum(1 for r in recs if r.get("status") != "ok")
    flag = float(c.rule("fallback_flag", h1.FALLBACK_FLAG))
    out = {"n": n, "fallback": fb, "ratio": fb / n if n else None, "flag": flag,
           "unrepresentative": (fb / n > flag) if n else False,
           "by_verdict": dict(sorted(Counter(((r.get("verdict") or "없음"), r.get("source") or "?")
                                             for r in recs).items())),
           "by_status": dict(sorted(Counter(r.get("status") or "?" for r in recs).items())),
           "truncated": c.decisions.truncated,
           "unused": sum(1 for r in in_range if r.get("key") not in keys),
           "missing": len(keys - {r.get("key") for r in recs})}
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
    res = a0_interest(c.mk, c.states, info["series"], cut)
    team0 = _team(c, "A0", cut)
    team1 = _team(c, "A1", cut)
    last_rate = info["last"]
    offline = rates["mode"] != "online"
    table = []
    monthly_rule = res["rule"] == "prev_month"
    for d, key, got, v, i in zip(res["dates"], res["keys"], res["rate_dates"], res["rates"], res["interest"]):
        if not math.isfinite(v):
            note = "금리 없음(자료보다 앞) → 0 으로 계산"
        elif key > last_rate:
            note = (f"자료 끝 → {got[:7] if monthly_rule else got} 값 이월"
                    + (f" (오프라인: {got} 값 이월)" if offline else ""))
        elif got != key:
            note = (f"전달({key[:7]}) 값 없음 → {got[:7]} 값 이월" if monthly_rule
                    else f"전 거래일 {key} 값 없음(휴일) → {got} 값")
        else:
            note = f"전달({key[:7]}) 값 사용(월 금리)" if monthly_rule else ""
        table.append({"date": d, "key": key, "rate_date": got, "rate": v, "interest": i, "note": note})
    before = [x["interest"] for x in table if x["date"] < period_start]
    v0, v1 = team0[-1]["value"], team1[-1]["value"]
    start_total = sum(c.states["A0"][tn]["start_cash"] for tn in h1.TRAINERS)
    i_cut = res["interest"][-1]
    carried = [x for x in table if x["key"] and math.isfinite(x["rate"]) and x["key"] > last_rate]
    out.update({"table": [x for x in table if x["date"] >= period_start], "interest": i_cut,
                "interest_period": i_cut - (before[-1] if before else 0.0),
                "a0": v0, "a0_plus": v0 + i_cut, "ret_plus": (v0 + i_cut) / start_total - 1,
                "a1_minus_plus": v1 - (v0 + i_cut),
                "missing_days": sum(1 for v in res["rates"] if not math.isfinite(v)),
                "carried_days": len(carried), "carried_from": carried[0]["rate_date"] if carried else None,
                "skipped": info.get("skipped") or [],
                "prev_mismatch": res["prev_mismatch"]})
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
    """장부 다시 점검(§3.8-10): 저장 자료(만든 때의 장부 전체)로 h1_check 를 다시 돈다.
    cut_date 가 있으면 날짜가 그 봉 이하이거나 날짜 없는 문제를 'n_window' 로(최종 판정 ②-1),
    날짜가 cut_date 이하인 문제만 'n_upto' 로(월간 10절: 그달 마지막 봉까지의 하루 기록) 따로 센다(2c 검토 R-6)."""
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
    upto = [p for p in errs if p.date is not None and (cut_date is None or p.date <= cut_date)]
    return {"n": len(errs), "codes": dict(sorted(Counter(p.code for p in errs).items())),
            "list": [f"{p.code} {p.arm or ''}/{p.trainer or ''} {p.date or ''}: {p.detail}" for p in errs[:20]],
            "n_window": len(in_win), "n_upto": len(upto), "n_nodate": sum(1 for p in errs if p.date is None),
            "cut": cut_date, "universe_ok": uni_ok, "universe_why": uni_why,
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
        period_start = S
        year_start = S
    else:
        cut = max(d for d in c.dates if d <= f"{month}-31")
        period_start = max(S, f"{month}-01")
        year_start = max(S, f"{month[:4]}-01-01")
    # 운영 기준·일지는 S ~ cut 까지만 본다. 일지 줄은 '그 실행이 처리하려던 봉'으로 나눈다(_journal, 2c 검토 R-3·R-5):
    # 최종(다 찬 창) = S+62 까지, 덜 찬 창 = 지금까지 전부, 월간 = 그달 마지막 날까지(어느 달인지 모르는 줄은 따로 셈) —
    # 그래서 지난달 보고서를 나중에 다시 만들어도 그달 숫자는 같다. 변경 일지·기업 행위는 그 봉을 저장한 때까지.
    if final and complete:
        B, unknown_in, end_at = s62, True, _saved_at(c, s62)
    elif final:
        B, unknown_in, end_at = _FAR, True, None
    else:
        B, unknown_in, end_at = f"{month}-31", False, _saved_at(c, cut)
    data.update({"cut": cut, "period_start": period_start, "end_at": end_at, "bound": B})
    data["ops"] = _ops(c, cut, B, unknown_in, end_at, allowed, allowed_why)
    data["values"] = _values(c, cut, None if final else f"{month}-01")
    data["ratios"] = {"period": _ratios(c, period_start, cut)}
    data["trades"] = {"period": _trades(c, period_start, cut)}
    if not final:
        data["trades"]["since_s"] = _trades(c, S, cut)
    data["shadow"] = _shadow(c, cut)
    data["realized"] = _realized_all(c, cut, period_start, year_start)
    data["leader"] = _leader(c, S, cut)
    data["interest"] = _interest(c, cut, period_start, rates)
    data["recheck"] = _recheck(c, s62 if final and complete else (cut if not final else None))
    if final:
        data["verdict"] = _verdict(data)
        data["extension"] = _extension(c, s62) if complete and last > s62 else None
    return data


def _verdict(d) -> dict:
    """--final: 사전 등록 ①~③ 의 통과/실패(수익률은 쓰지 않음, ③⑨)와 ⑤ 재시작 상한·마감.
    ① 판정 창 63봉(S ~ S+62)을 다 처리했는가 — 아니면 판정하지 않는다(남은 봉 수만).
    ②-1 L 오류 0(errors.jsonl + 저장 자료로 다시 점검), ②-2 빠진 날 0·늦은 봉 ≤ 10·한 번에 ≤ 5(종료 코드 6 없음),
    ②-3 모든 하루 기록 지문이 replay_pass 에 있고 다른 지문으로 봉을 처리한 실행 없음.
    결과: "pass" / "fail_window"(판정 창 실패 → 재시작 대상) / "fail_h1"(H1 포워드 실패(운영 기준 미충족):
    재시작이 상한을 넘게 필요하거나, 마감까지 깨끗한 창이 끝나지 않음·끝날 수 없음) / "not_finished"."""
    ops, rc = d["ops"], d["recheck"]
    deadline, wb = ops["deadline"], d["window_bars"]
    c0 = {"ok": bool(d["complete"]),
          "detail": f"처리 {min(ops['n_bars'], wb)}/{wb}봉" + ("" if d["complete"] else f", 남은 봉 {ops['bars_left']}개")}
    c1 = {"ok": ops["l_errors"] == 0 and rc["n_window"] == 0,
          "detail": f"일지의 L 오류(errors.jsonl·종료 코드 2) {ops['l_errors']}건"
                    + (f"(거짓 양성 판정 {ops['l_false_positive']}건은 뺌, 사전 등록 ④)" if ops["l_false_positive"] else "")
                    + f", 저장 자료로 다시 점검한 L 오류 {rc['n_window']}건"}
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
    used, cap = ops["restarts_used"], ops["max_restarts"]
    no_more = used >= cap                               # 이 창이 실패하면 필요한 재시작이 상한을 넘음
    over_cap = used > cap                               # (일어나지 않아야 함: restart 가 거절) 이 창 자체가 상한 밖
    last = d["last"]
    # 마감까지 끝날 수 없음(확실한 것만): 거래일은 평일의 일부라서 'k 번째 평일'보다 일찍 올 수 없다.
    this_min_end = d["s62"] if d["complete"] else _add_weekdays(last, ops["bars_left"])
    next_min_end = _add_weekdays(last, wb - 1)          # 재시작하면 새 S ≥ 지금 마지막 봉 → 새 S+62 ≥ 이 날
    out = {"complete": d["complete"], "c0": c0, "c1": c1, "c2": c2, "c3": c3,
           "over_deadline": this_min_end > deadline, "this_min_end": this_min_end, "next_min_end": next_min_end,
           "violated": violated}
    if over_cap:
        out.update(passed=False if d["complete"] else None, result="fail_h1",
                   why=f"재시작 {used}번 — 상한 {cap}번을 넘은 창(사전 등록 ⑤)")
        return out
    if not d["complete"]:
        out["passed"] = None
        if this_min_end > deadline:
            out["result"] = "fail_h1"
            out["why"] = (f"마감 {deadline} 까지 깨끗한 판정 창이 끝나지 않음 — 남은 {ops['bars_left']}봉을 휴장일 없이 매일 "
                          f"처리해도 S+62 가 빨라야 {this_min_end}")
        elif violated and no_more:
            out["result"] = "fail_h1"
            out["why"] = (f"이 창이 이미 운영 기준을 어겼고 남은 재시작이 없음(재시작 {used}/{cap} — "
                          f"재시작이 {cap}번을 넘게 필요함)")
        elif violated and next_min_end > deadline:
            out["result"] = "fail_h1"
            out["why"] = (f"이 창이 이미 운영 기준을 어겼고, 재시작해도 새 창의 S+62 가 빨라야 {next_min_end} 라서 "
                          f"마감 {deadline} 을 넘음")
        else:
            out["result"] = "not_finished"
            out["why"] = f"아직 판정 창이 끝나지 않음 — 남은 봉 {ops['bars_left']}개"
        return out
    out["passed"] = not violated and not out["over_deadline"]
    if out["passed"]:
        out["result"] = "pass"
        out["why"] = "운영 기준 ①~③ 모두 통과 → 이 시장에서 H1 을 기본 장부로 할지 검토로 넘어감"
    elif out["over_deadline"]:
        out["result"] = "fail_h1"
        out["why"] = f"판정 창 마지막 봉 S+62 {d['s62']} 이 마감 {deadline} 뒤"
    elif no_more:
        out["result"] = "fail_h1"
        out["why"] = (f"운영 기준 미충족이고 남은 재시작이 없음(재시작 {used}/{cap} — "
                      f"재시작이 {cap}번을 넘게 필요함)")
    elif next_min_end > deadline:
        out["result"] = "fail_h1"
        out["why"] = (f"운영 기준 미충족이고, 재시작해도 새 창의 S+62 가 빨라야 {next_min_end} 라서 마감 {deadline} 을 넘음")
    else:
        out["result"] = "fail_window"
        out["why"] = (f"판정 창 실패 → 재시작 대상(사전 등록 ⑤, 남은 재시작 {ops['restarts_left']}번, "
                      f"마감 {deadline}, 새 창의 S+62 는 빨라야 {next_min_end})")
    return out


def _extension(c, s62) -> dict:
    """연장 기록: 판정 창(S+62) 뒤에 처리한 봉. 판정에 쓰지 않는다(사전 등록 ①)."""
    ext = [d for d in c.dates if d > s62]
    last = ext[-1]
    lev = _l_events(c, _journal(c))
    out = {"n": len(ext), "first": ext[0], "last": last,
           "late": sum(1 for r in c.canon if r["date"] > s62 and r.get("late")),
           "l_errors": sum(1 for e in lev if _scope(e, s62, True) == "out" and not e["false_positive"])}
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


def _mdd_pct(x):
    """MDD 표기: 낙폭이 없으면 '0.00%'(+ 기호 없음), 있으면 '-4.24%'."""
    if x is None:
        return "계산 불가"
    return "0.00%" if x == 0 else f"{x * 100:.2f}%"


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
    if d["kind"] == "final":
        L += ["",
              f"- 이 보고서의 값은 {d['period_start']} ~ {d['cut']}"
              + (" (판정 창 S ~ S+62 로 고정)" if d["complete"] else " (지금까지)"),
              f"- 만든 때의 장부: 저장된 마지막 봉 {d['last']} (HEAD {d['head']['run_id']}, {d['head']['written_at']})"]
    else:
        L += ["",
              f"- **이 달 숫자(2~9절)는 그달 마지막 처리 봉 {d['cut']} 까지로 고정**이다: 값은 {d['period_start']} ~ "
              f"{d['cut']} (S 이후 누적도 같이), 일지는 '그 실행이 처리하려던 봉'이 {d['month']} 안인 것까지. "
              "다음 달 봉을 더 처리한 뒤 다시 만들어도 이 숫자는 같다.",
              f"- 머리말의 HEAD 와 10절 다시 점검의 '만든 때' 부분은 **보고서를 만든 때의 장부 전체** 기준이다: 저장된 마지막 봉 "
              f"{d['last']} (HEAD {d['head']['run_id']}, {d['head']['written_at']})"]
    L += [f"- 시작 금액(두 장부 같음): {_money(mk, val['arms']['A0']['start'])} · 재시작 번호 {d['restart_no']} · "
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
        elif v["violated"]:
            L += ["- 참고: 이 창은 이미 운영 기준을 어긴 기록이 있다(아래 2절) → 사전 등록 ⑤ 의 재시작 사유인지 확인. "
                  f"재시작하면 새 창의 S+62 는 빨라야 {v['next_min_end']} (마감 {ops['deadline']}).", ""]
        return L
    L += _table(["기준", "결과", "근거"], [
        ["① 판정 창 63봉(S ~ S+62)을 다 처리함", _ok_word(v["c0"]["ok"]), v["c0"]["detail"]],
        ["②-1 장부 논리 오류 0건", _ok_word(v["c1"]["ok"]), v["c1"]["detail"]],
        ["②-2 빠진 날 0 · 늦은 봉 · 한 번에 따라잡은 봉", _ok_word(v["c2"]["ok"]),
         v["c2"]["detail"] + " — " + ", ".join(f"{k} {'O' if ok else 'X'}" for k, ok in v["c2"]["parts"].items())],
        ["②-3 재현을 통과한 코드·환경만", _ok_word(v["c3"]["ok"]), v["c3"]["detail"]],
        ["③ 수익률은 기록만", "판정에 안 씀", "수익률·MDD·A1−A0·지수 대비·그림자 서킷·팀장 숫자는 아래 기록 절에만"],
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
    if final and d["complete"]:
        head = f"## 2. 운영 기준 (판정 창 안: S {d['S']} ~ S+62 {d['s62']})"
    elif final:
        head = f"## 2. 운영 기준 (판정 아님 — 이 창의 S {d['S']} ~ {ops['last']} 상태)"
    else:
        head = f"## 2. 운영 기준 (판정 아님 — 이 창의 S {d['S']} ~ {d['month']} 끝까지)"
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
    be = ops["data_by_exit"]
    k4 = ", ".join(f"{k} {v}" for k, v in be[h1.EXIT_DATA]["kinds"].items()) or "없음"
    k7 = ", ".join(f"{k} {v}" for k, v in be[h1.EXIT_D7]["kinds"].items()) or "없음"
    stops_txt = (f"{ops['data_stops']}번 — 종료 코드 4(자료 D1~D6·사전 조건 PRE·환경 ENV) {be[h1.EXIT_DATA]['n']}번: {k4} / "
                 f"종료 코드 7(기준 지수 늦음) {be[h1.EXIT_D7]['n']}번: {k7} (재시작 아님)")
    l_codes = ", ".join(f"{k} {v}" for k, v in ops["l_codes"].items())
    l_txt = (f"{ops['l_errors']}건" + (f" ({l_codes})" if l_codes else "") + " — 0 이어야 함(②-1)"
             + (f" · 그중 errors.jsonl 기록 없이 종료 코드 2 로만 남은 실행 {ops['l_runs_only']}번" if ops["l_runs_only"] else "")
             + (f" · 거짓 양성으로 판정(사전 등록 ④) {ops['l_false_positive']}건은 뺌" if ops["l_false_positive"] else ""))
    rs = ops["restart_sources"]
    rows = [
        ["판정 창 진행", f"{prog} · 시작 S {ops['first']} · {end}"],
        ["장부 논리 오류(L: errors.jsonl + 종료 코드 2 실행)", l_txt],
        ["빠진 날(calendar.jsonl vs 하루 기록)", miss + " — 0 이어야 함(②-2)"],
        ["늦은 봉(다음 장 시작 뒤 처리)", f"{len(ops['late'])}개 / 상한 {ops['max_late_total']}"
         + (f" ({', '.join(ops['late'][:12])})" if ops["late"] else "")
         + (f" · LLM 직전 시각 재확인으로 안 물은 호출 {ops['late_calls']}번" if ops["late_calls"] else "")],
        ["한 번에 따라잡은 최대 봉 수", f"{ops['batch_max']}봉 / 상한 {ops['max_late_batch']}"
         + (f" · 밀린 봉 초과로 멈춤(종료 코드 6) {ops['backlog_fail']}번" if ops["backlog_fail"] else "")],
        ["다른 지문으로 처리한 봉(재현 통과 기록에 없는 코드·환경)",
         f"{len(ops['other_fp'])}개" + (f" ({', '.join(ops['other_fp'][:10])})" if ops["other_fp"] else "")
         + (f" — {ops['allowed_why']}" if ops["allowed_why"] else "") + " — 0 이어야 함(②-3)"],
        ["관문 거절(종료 코드 3: 재현 미통과 코드·환경 또는 규칙 다름)", f"{ops['gate_refused']}번"],
        ["자료 멈춤(종료 코드 4·7)", stops_txt],
        ["잠금 30분 초과(종료 코드 5)", f"{ops['lock_timeouts']}번"],
        ["끝 기록 없는 실행(kill·전원 꺼짐 — 판정에는 안 씀)", f"{ops['no_end']}번"],
        ["재시작", f"{ops['restarts_used']}번 / 상한 {ops['max_restarts']} (남은 {ops['restarts_left']}번)"],
        ["마감", f"{ops['deadline']} 까지 {ops['days_to_deadline']}일(마지막 처리 봉 기준) · "
                 f"평일 {ops['weekdays_to_deadline']}일 · 남은 창 봉 {ops['bars_left']}개"],
    ]
    if ops["unknown"]:
        rows.append(["어느 달인지 모름(처리하려던 봉을 아직 모름 — 이 달 숫자에 안 넣음)",
                     ", ".join(f"{k} {v}" for k, v in ops["unknown"].items())])
    L += _table(["항목", "값"], rows)
    L.append("")
    L.append("- 일지 줄은 '그 실행이 처리하려던 봉'으로 셈한다(봉을 몇 개 저장한 뒤 멈췄으면 그 다음 봉의 일).")
    if ops["outside"]:
        L.append(f"- 창 밖 기록 {ops['outside']}줄: start_date 는 이 창의 S 와 같지만 창이 만들어지기 전의 줄(실패한 start, "
                 "같은 S 의 옛 창)이라 세지 않았다.")
    if ops["broken"]:
        L.append("- ※ 읽지 못한(깨진) 일지 줄: " + ", ".join(f"{k} {v}줄" for k, v in ops["broken"].items())
                 + " — 쓰다 꺼진 줄일 수 있다. 장부 논리 오류는 runs.jsonl 의 종료 코드 2 로도 센다.")
    if ops["restart_mismatch"]:
        L.append("- ※ 재시작 수의 출처가 서로 다름: " + ", ".join(f"{k} {v}" for k, v in rs.items())
                 + " → 가장 큰 값으로 셈. restarts.jsonl·archive/ 폴더를 사람이 확인하세요.")
    if ops["restarts"]:
        L.append("- 재시작 기록: " + "; ".join(f"{r['at']} (옛 S {r['old_start']} ~ {r['old_last']}, 사유 {r['reason']!r})"
                                           for r in ops["restarts"]))
    if ops["restarts_pending"]:
        L.append("- 끝나지 않은 restart 기록(폴더를 아직 옮기지 않음 — 재시작으로 세지 않음): "
                 + "; ".join(f"{r['at']} 사유 {r['reason']!r}" for r in ops["restarts_pending"])
                 + " → 다시 python h1.py restart 를 치면 마저 하거나, 의도가 아니면 사람이 확인")
    fps = ops["fingerprints"]
    L.append(f"- 코드·환경 지문: {len(fps)}가지" + (" (바뀐 날 " + ", ".join(
        f"{f['date']} code {f['code_hash']}… / {f['env']}" for f in fps[1:]) + ")" if len(fps) > 1 else "")
        + (f" · 처음 {fps[0]['date']} code {fps[0]['code_hash']}… / {fps[0]['env']}" if fps else ""))
    ch = ", ".join(f"{CHANGE_WORD.get(k, k)} {v}" for k, v in ops["changes"].items()) or "없음"
    L.append(f"- 코드·규칙 변경 일지(changes.jsonl, 이 창이 만들어진 뒤 ~ {d['cut']} 저장 때): {ch}"
             + (f" · 그 뒤의 변경 {ops['changes_after']}줄은 다음 봉의 달에 셈" if ops["changes_after"] and not final else ""))
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
                    + ([_pct(a["ret_period"])] if monthly else []) + [_mdd_pct(a["mdd"])])
    bh_txt = _money(mk, bh["value"]) if bh["started"] else "아직 없음(S+1 시가에 시작)"
    rows.append([f"{idle} 들고 있기(같은 시작: S+1 시가·소수 단위)", bh_txt,
                 _pct(bh["return"]) if bh["started"] else "-"]
                + ([_pct(bh["ret_period"]) if bh["started"] else "-"] if monthly else [])
                + [_mdd_pct(bh["mdd"]) if bh["started"] else "-"])
    L += _table(head, rows)
    L += ["",
          f"- A1−A0: {_money(mk, val['diff'], True)} ({_pp(val['diff_pp'])})"
          + (f" · 그달 {_pp(val['diff_period_pp'])}" if monthly else ""),
          f"- A1 − {idle} 들고 있기: {_pp(bh['a1_minus_pp'])}" if bh["started"] else f"- {idle} 들고 있기는 S+1 부터",
          f"- A1 이 들고 있는 {idle}: {h1.fmt_units(a1['units'])}단위(세 트레이너 합)"
          + (f" · {idle} 들고 있기 단위 {h1.fmt_units(bh['units'])}" if bh["started"] else ""),
          "- 수익률 = 평가액 ÷ 시작 금액 − 1(평가액 = 현금 + 주식 × 그날 종가 + 지수 단위 × 지수 종가, 파는 비용은 빼지 않음).",
          "- MDD(최대 낙폭) = 최고점에서 가장 많이 떨어진 비율. S 종가(= 시작 금액)부터 매일 종가 평가액으로 잰다"
          "(R2 와 같은 방식). 떨어진 적이 없으면 0.00%.", ""]
    rows = []
    for t in val["trainers"]:
        rows.append([t["trainer"], _money(mk, t["A0"]["value"]), _pct(t["A0"]["ret"]), _mdd_pct(t["A0"]["mdd"]),
                     _money(mk, t["A1"]["value"]), _pct(t["A1"]["ret"]), _mdd_pct(t["A1"]["mdd"]),
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
    ms = {arm: tr["period"][arm]["marathon_short"] for arm in h1.ARMS}
    L += ["", "- 마라토너는 종목당 상한이 30% 라서 5종목을 다 채우려면 150% 가 든다 — 현금(A1 은 현금+지수)이 모자라면 4·5번째 "
          "매수가 '현금 부족' 보류가 될 수 있다(team.py 그대로, R2 P6). "
          f"이 기간 마라토너의 '현금 부족' 보류: A0 {ms['A0']}건 · A1 {ms['A1']}건.",
          "- A1 은 주식을 살 때 모자란 만큼만 지수를 팔고, 남은 현금(1 이상)은 다시 지수로 산다(지수 다리 비용이 생김).", ""]
    return L


def _render_shadow(d):
    rows = [[f"{s['arm']} {s['trainer']}", s["first"] or "없음", s["desc"] or "-", s["days"]] for s in d["shadow"]]
    L = [f"## 6. 그림자 서킷 (S ~ {d['cut']}, 계산만 — 장부는 바뀌지 않음)", "",
         "켜져 있었다면 걸렸을지(누적 −10%·하루 −7%)를 매일 계산만 한 기록이다. 판정에 쓰지 않는다(사전 등록 ③).", ""]
    L += _table(["장부·트레이너", "첫 발동일", "사유(첫 발동)", "발동한 날 수"], rows)
    L += ["", "- H1 장부는 실제로 팔지도 멈추지도 않았다(stopped 는 늘 False). 사유는 그날 평가액으로 다시 센 누적·하루 변화다"
          "(장부 하루 기록 events 에는 risk_guard 문구가 그대로 있다).",
          "- 첫 발동 뒤에도 매일 다시 계산한다(영구 정지를 흉내 내지 않음). '발동한 날 수'는 걸렸을 날의 수다.", ""]
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
        L.append(f"- 이 창이 쓴 판정 기록 {ld['n']}건 · LLM 정상 {ld['n'] - ld['fallback']} · "
                 f"폴백(status ≠ ok, 늦은 봉 포함) {ld['fallback']} "
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
    if ld["unused"]:
        L.append(f"- 같은 날짜 범위에 있지만 이 창의 하루 기록이 쓰지 않은 판정 기록 {ld['unused']}건은 세지 않았다"
                 "(재시작 전 창의 것이거나 저장되지 못한 봉의 것).")
    if ld["missing"]:
        L.append(f"- ※ 하루 기록이 가리키는데 판정 기록에 없는 열쇠 {ld['missing']}개(L17 — 10절 다시 점검 참고).")
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
          f"받은 시각 {it['fetched_at'] or '기록 없음(옆 .json 없음 — 예: R2 data/rates 복사본)'} · {mode}",
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
        L += ["", f"- 금리 자료 끝({it['last_rate']})을 넘어 마지막 값을 이월한 날 {it['carried_days']}일"
              + (f" (오프라인: {it['carried_from']} 값 이월)" if it["mode"] != "online" else "")]
    if it["skipped"]:
        L += ["", "- ※ 건너뛴 금리 저장본: " + "; ".join(it["skipped"])]
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
    monthly = d["kind"] != "final"
    L = ["## 10. 장부 다시 점검 (저장 자료만으로 h1_check)", ""]
    if monthly:
        L.append(f"- **그달 마지막 봉 {d['cut']} 까지의 하루 기록**(날짜가 그 봉 이하)에서 찾은 L 오류 {rc['n_upto']}건"
                 " — 0 이어야 함")
    L += [f"- 만든 때의 장부 전체로 다시 돈 check_ledger(A0·A1)·check_pair·check_decisions(HEAD 의 판정 기록 앞부분 지문) → "
          f"**L 오류 {rc['n']}건**" + (f" ({', '.join(f'{k} {v}' for k, v in rc['codes'].items())})" if rc["codes"] else "")
          + (f", 그중 날짜 없는 것 {rc['n_nodate']}건" if rc["n_nodate"] else "") + " — 0 이어야 함",
          f"- 달력: calendar.jsonl 마지막 정상 줄({rc['calendar_at'] or '없음'}, 만든 때 기준)",
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
                                                 "종료 코드: 0 정상 / 2 예상 밖·장부 손상 / 4 환경 문제(디스크·권한, "
                                                 "--fetch-rates 받기 실패) / 5 잠금 / 8 장부 없음 / 9 인자 오류")
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
        return EXIT_INTERRUPT
    except (OSError, MemoryError) as e:
        h1._say(f"h1_report.py: 환경 문제(ENV) {type(e).__name__}: {e} → 디스크 공간·권한을 확인한 뒤 다시(장부는 그대로)")
        return EXIT_ENV
    except Exception as e:                      # noqa: BLE001
        h1._say(f"h1_report.py: 예상 밖 오류 {type(e).__name__}: {e}")
        try:
            traceback.print_exc()
        except OSError:
            pass
        return EXIT_ERROR


if __name__ == "__main__":
    import h1_report as _me                     # h1.py 와 같은 이유: 모듈이 두 벌이 되지 않게
    sys.exit(_me.cli())
