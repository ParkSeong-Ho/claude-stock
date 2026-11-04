"""
h1_check.py - H1 장부 점검 (설계 docs/h1-forward-design.md §4, 단계 2b-1)
------------------------------------------------------------------
무엇을 하나 (주식 초보용 설명)
- H1 장부(가짜 지갑 + 주문·체결·보류·하루 기록)가 규칙대로 쓰였는지 숫자로 다시 맞춰 본다.
- 문제는 Problem 한 줄로 돌려준다. level "L" = 장부 논리 오류(그 봉 저장 안 함, 종료 코드 2 → 고치고 재시작),
  "W" = 경고(멈추지 않음). 자료 문제(D)는 h1.py 가 준비 단계에서 직접 판단한다.
- 순수 함수다: 인터넷·파일 쓰기 없음. 장부는 메모리 모양(지갑이 PaperWallet)이든 JSON dict 든 받는다.
- 지갑 기록(log, 금액을 소수 2자리로 반올림함)은 쓰지 않고 fills·days 로 맞춘다.
- 허용 오차: 현금 EPS_CASH(절대 1e-6 달러/원), 비율 EPS_REL(1e-9). 체결가는 정확히 같아야 한다.

함수
  check_ledger(market, arm, states, calendar, decisions, allowed=None, *, frames=None)
      한 장부(arm)의 트레이너 3명 장부 전체 기록을 저장 자료만으로 점검(보고서·재현). frames 를 주면 L3·L6 의
      "그날 주식 시세" 부분까지 본다.
  check_pair(market, a0, a1, decisions)        A0 ↔ A1 짝 점검(L16·L17·L23)
  check_decisions(decisions, head=None)        판정 기록 L18 (중복 열쇠, HEAD 에 적은 앞부분 지문)
  check_day(market, date, before, after, frames, idle, calendar, halted, decisions, allowed, *, head=None,
            universe_sha256=None, meta_universe_sha256=None)
      봉 하나 처리 전후(장부 6개)를 점검: 위 셋 + 처리 전 기록이 그대로인지 + 그날 시세와 체결가
  errors(problems)                             L 등급만

L24(장부 파일 손상)는 2b-2 의 장부 읽기가 판단한다. 여기서는 장부 모양이 깨져 점검을 끝낼 수 없을 때만 L24 로 알린다.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import h1
import main
import markets
import team
from paper_wallet import PaperWallet, shares_within_cap
from risk_guard import CircuitBreaker

EPS_CASH = 1e-6        # 현금 비교 허용 오차(절대, 달러/원)
EPS_REL = 1e-9         # 비율 비교 허용 오차(상대)
L_CODES = tuple(f"L{i}" for i in range(1, 25))
SKIP_KINDS = ("0주", "현금부족", "팀장hold", "확신도낮음")
ORDER_STATUS = ("pending", "filled", "skipped", "dropped")
EFFECTS = ("veto", "hold", "low_conv", "ordered", "over_slots")


@dataclass(frozen=True)
class Problem:
    level: str            # "L" | "D" | "W"
    code: str             # "L1" … / "D1" … / "W1" …
    market: str
    arm: str | None
    trainer: str | None
    date: str | None
    detail: str


def errors(problems) -> list:
    """L 등급(장부 논리 오류)만."""
    return [p for p in problems if p.level == "L"]


class _Out:
    def __init__(self, market):
        self.market = market
        self.items = []

    def add(self, code, detail, arm=None, trainer=None, date=None, level="L"):
        self.items.append(Problem(level, code, self.market, arm, trainer, date, detail))


# ---------------- 작은 도움 함수 ----------------

def _plain(st):
    """메모리 장부(지갑 PaperWallet)든 JSON dict 든 지갑을 dict 로 바꾼 얕은 사본."""
    w = st.get("wallet")
    if isinstance(w, PaperWallet):
        w = asdict(w)
    return {**st, "wallet": w}


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _intlike(v):
    return _isnum(v) and math.isfinite(v) and float(v).is_integer()


def _rel_ok(a, b):
    return abs(a - b) <= EPS_REL * max(1.0, abs(a), abs(b))


def _cash_ok(a, b):
    return abs(a - b) <= EPS_CASH


def _walk_numbers(obj, path="$"):
    """장부 안의 모든 숫자(float·int)를 (경로, 값)으로."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_numbers(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk_numbers(v, f"{path}[{i}]")
    elif _isnum(obj):
        yield path, obj


def _conviction_of(decisions, key):
    """team ④ 가 정렬에 쓴 확신도: 판정 기록이 llm 이고 판정이 있으면 그 확신도, 아니면 None(= 0 으로 침)."""
    if decisions is None:
        return None
    rec = decisions.get(key)
    if rec and rec.get("source") == "llm" and rec.get("verdict") is not None:
        return rec.get("conviction")
    return None


def _pending_buys_at_close(orders, d):
    """그날 종가 뒤 '매수 대기' 주문 수 (그날까지 생겼고, 아직 끝나지 않았거나 그 뒤에 끝난 것)."""
    n = 0
    for o in orders:
        if o["action"] != "매수" or o["created_on"] > d:
            continue
        if o["status"] == "pending" or (o.get("done_date") is not None and o["done_date"] > d):
            n += 1
    return n


def _pending_codes_at_close(orders, d):
    out = set()
    for o in orders:
        if o["created_on"] > d:
            continue
        if o["status"] == "pending" or (o.get("done_date") is not None and o["done_date"] > d):
            out.add(o["code"])
    return out


def _fee_slip(market):
    m = markets.MARKETS[market]
    return m.fee_rate, m.slippage


# ============================ 장부 하나 ============================

def _check_one(out, market, arm, tname, st, calendar, decisions, allowed, frames):
    def P(code, detail, date=None):
        out.add(code, detail, arm, tname, date)

    d = _plain(st)
    w = d["wallet"]
    idle = h1.idle_code(market)
    fee, slip = w["fee_rate"], w["slippage"]
    start_cash, S = d["start_cash"], d["start_date"]
    days, fills, skips, orders = d["days"], d["fills"], d["skips"], d["orders"]
    positions, holds, pending = d["positions"], w["holdings"], d["pending"]
    cap = main.CONFIG["종목상한"][tname]

    # L21 모든 숫자 유한
    for path, v in _walk_numbers(d):
        if not math.isfinite(v):
            P("L21", f"{path} = {v!r} (NaN·inf)")

    # L9 지갑 비용 상수 = 시장 값
    mfee, mslip = _fee_slip(market)
    if fee != mfee or slip != mslip:
        P("L9", f"지갑 수수료·슬리피지 ({fee}, {slip}) ≠ 시장 ({mfee}, {mslip})")

    # L1 현금
    if not w["cash"] >= -EPS_CASH:
        P("L1", f"지갑 현금 {w['cash']!r} < 0")
    for row in days:
        if not row["cash"] >= -EPS_CASH:
            P("L1", f"하루 기록 현금 {row['cash']!r} < 0", row["date"])
    for f in fills:
        if not f["cash_after"] >= -EPS_CASH:
            P("L1", f"체결 뒤 현금 {f['cash_after']!r} < 0 ({f['code']})", f["date"])

    # L2 보유·positions·stopped
    if d["stopped"] is not False:
        P("L2", "stopped 가 False 가 아님(H1 장부 서킷은 꺼져 있어야 함)")
    for code, h in holds.items():
        q = h["shares"]
        if not (_isnum(q) and math.isfinite(q) and q > 0):
            P("L2", f"보유 {code} 수량 {q!r} (양수·유한이어야 함)")
            continue
        if code == idle:
            continue
        if not _intlike(q):
            P("L2", f"주식 {code} 수량 {q!r} 가 정수가 아님")
        if code not in positions:
            P("L2", f"positions 에 없는 주식 보유 {code}")
    for code, pos in positions.items():
        if code == idle:
            P("L2", "대기 자산이 positions 에 있음(지수는 지갑 보유에만)")
            continue
        h = holds.get(code)
        if h is None or h["shares"] != pos["shares"]:
            P("L2", f"positions {code} 수량 {pos.get('shares')!r} ≠ 지갑 보유 {None if h is None else h['shares']!r}")
        if not _intlike(pos.get("shares")):
            P("L2", f"positions {code} 수량이 정수가 아님")

    # L10 A0: 대기 자산 체결·보유 없음
    if arm == "A0":
        if idle in holds:
            P("L10", "A0 지갑에 대기 자산 보유")
        for f in fills:
            if f["kind"] == "idle" or f["code"] == idle:
                P("L10", "A0 에 대기 자산 체결", f["date"])
        for row in days:
            if row["idle_units"] != 0 or row["idle_value"] != 0:
                P("L10", "A0 하루 기록에 지수 단위·평가", row["date"])

    # L16 하루 기록 날짜
    dates = [row["date"] for row in days]
    day_ix = {}
    for i, dt in enumerate(dates):
        if dt in day_ix:
            P("L16", f"하루 기록 날짜 중복 {dt}", dt)
        day_ix[dt] = i
        if i and not dt > dates[i - 1]:
            P("L16", f"하루 기록 날짜 순서가 거꾸로 {dates[i - 1]} → {dt}", dt)
        if i and days[i]["prev_cal_date"] != dates[i - 1]:
            P("L16", f"prev_cal_date {days[i]['prev_cal_date']} ≠ 앞 하루 기록 {dates[i - 1]} (빠진 봉)", dt)
    if days and dates[0] != S:
        P("L16", f"첫 하루 기록 {dates[0]} ≠ 시작 봉 S {S}")
    if (dates[-1] if days else None) != d["last_date"]:
        P("L16", f"last_date {d['last_date']} ≠ 마지막 하루 기록 {dates[-1] if days else None}")
    if calendar is not None and days:
        cal = list(calendar)
        if S not in cal:
            P("L16", f"달력에 시작 봉 S {S} 가 없음")
        else:
            i0 = cal.index(S)
            want = cal[i0:i0 + len(days)]
            if dates != want:
                P("L16", f"하루 기록 날짜가 달력 S~ 와 다름 (기록 {len(dates)}개, 달력 {want[:3]}…)")
            if i0 == 0 or days[0]["prev_cal_date"] != cal[i0 - 1]:
                P("L16", f"S 의 prev_cal_date {days[0]['prev_cal_date']} ≠ 달력의 S 전 거래일", S)

    halted_on = {row["date"]: set(row.get("halted") or ()) for row in days}
    by_id = {}
    for o in orders:
        if o["id"] in by_id:
            P("L5", f"주문 id 중복 {o['id']}", o.get("created_on"))
        by_id[o["id"]] = o

    # ---- 체결 하나하나: L3(지수)·L4·L6·L9·L11·L13·L14 ----
    fill_count = {}
    seen_leg = set()
    for i, f in enumerate(fills):
        dt, code, kind, side = f["date"], f["code"], f["kind"], f["side"]
        if dt not in day_ix:
            P("L4", f"처리한 봉이 아닌 날 체결 {code}", dt)
        q, px = f["qty"], f["price"]
        # L9 비용식
        if side == "buy":
            E = px * (1 + slip)
            exp, tax_rate = -(E * q + E * q * fee), 0.0
        else:
            E = px * (1 - slip)
            tax_rate = 0.0 if kind == "idle" else h1.stock_sell_tax(market, dt)
            exp = E * q - E * q * fee - E * q * tax_rate
        if not _cash_ok(f["cash_delta"], exp):
            P("L9", f"{code} {side} 현금 변화 {f['cash_delta']!r} ≠ 비용식 {exp!r}", dt)
        if not _rel_ok(f["exec_price"], E):
            P("L9", f"{code} 체결가(슬리피지 포함) {f['exec_price']!r} ≠ {E!r}", dt)
        if not _cash_ok(f["fee"], E * q * fee):
            P("L9", f"{code} 수수료 {f['fee']!r} ≠ {E * q * fee!r}", dt)
        if not _cash_ok(f["tax"], E * q * tax_rate if side == "sell" else 0.0):
            P("L9", f"{code} 매도세 {f['tax']!r} (세율 {tax_rate})", dt)
        if not _cash_ok(f["slip_cost"], q * px * slip):
            P("L9", f"{code} 슬리피지 비용 {f['slip_cost']!r}", dt)
        if kind == "idle":
            if code != idle:
                P("L11", f"대기 자산 다리의 종목 {code} ≠ {idle}", dt)
            if dt in day_ix and px != days[day_ix[dt]]["idle_open"]:
                P("L3", f"지수 체결가 {px!r} ≠ 그날 지수 시가 {days[day_ix[dt]]['idle_open']!r}", dt)
            if side == "buy":
                if f["purpose"] not in ("start", "sweep"):
                    P("L11", f"지수 매수 목적 {f['purpose']!r}", dt)
            else:
                purpose = f["purpose"] or ""
                if not purpose.startswith("fund:"):
                    P("L11", f"지수 매도 목적 {purpose!r} (fund:<종목> 이어야 함)", dt)
                else:
                    x = purpose[5:]
                    nxt = fills[i + 1] if i + 1 < len(fills) else None
                    if not (nxt and nxt["kind"] == "stock" and nxt["side"] == "buy" and nxt["code"] == x
                            and nxt["date"] == dt):
                        P("L11", f"지수를 판 뒤 {x} 매수가 이어지지 않음(지수 판 뒤 매수 실패)", dt)
                    short = f.get("short")
                    u_net = px * (1 - slip) - px * (1 - slip) * fee
                    got = q * u_net
                    if not (_isnum(short) and short > 0 and short <= got <= short * (1 + 2e-9) + EPS_CASH):
                        P("L11", f"{x} 자금 지수 매도: 메운 금액 {short!r} vs 판 금액 {got!r}", dt)
                    if any(s["date"] == dt and s["code"] == x and s["kind"] == "현금부족" for s in skips):
                        P("L11", f"'현금 부족' 보류된 {x} 매수에 지수 매도가 쓰임", dt)
            continue
        # 주식 다리
        if not _intlike(q):
            P("L2", f"주식 체결 수량 {q!r} 가 정수가 아님 ({code})", dt)
        leg = (code, side, dt)
        if leg in seen_leg:
            P("L5", f"같은 날 같은 종목·방향 체결 중복 {code} {side}", dt)
        seen_leg.add(leg)
        if f["purpose"] == "delist":
            if f["order_id"] is not None or side != "sell":
                P("L23", f"상장폐지 정리 체결 모양이 다름 ({code})", dt)
            continue
        if f["purpose"] != "order":
            P("L14", f"주식 체결 목적 {f['purpose']!r}", dt)
        if code in halted_on.get(dt, ()):
            P("L6", f"거래정지일에 {code} 체결", dt)
        if side == "buy" and q != shares_within_cap(start_cash, cap, px, fee, slip):
            P("L13", f"{code} 매수 수량 {q} ≠ 상한 기준 {shares_within_cap(start_cash, cap, px, fee, slip)}", dt)
        oid = f["order_id"]
        o = by_id.get(oid)
        fill_count[oid] = fill_count.get(oid, 0) + 1
        if o is None:
            P("L14", f"체결의 주문 {oid!r} 이 주문 기록에 없음", dt)
            continue
        if o["code"] != code or o["action"] != ("매수" if side == "buy" else "매도"):
            P("L14", f"체결 {code} {side} 와 주문 {oid} 이 맞지 않음", dt)
        if o["status"] != "filled" or o.get("done_date") != dt:
            P("L14", f"주문 {oid} 상태 {o['status']}/{o.get('done_date')} 인데 {dt} 체결", dt)
        if not o["created_on"] < dt:
            P("L14", f"주문 {oid} 이 체결일 전날 끝에 대기 중이 아니었음(생긴 날 {o['created_on']})", dt)
        if not o["signal_date"] < dt:
            P("L4", f"신호일 {o['signal_date']} ≥ 체결일 ({code})", dt)
    for oid, n in fill_count.items():
        if oid is not None and n > 1:
            P("L14", f"주문 {oid} 이 {n}번 체결됨")

    # ---- 주문 기록: L4(정지로만 기다림)·L14 ----
    pend_ids = [h1.order_id(o) for o in pending]
    if len(set(p["code"] for p in pending)) != len(pending):
        P("L5", "대기 목록에 같은 종목 주문이 둘 이상")
    for o in orders:
        if o["id"] != f"{o['signal_date']}|{o['code']}|{o['action']}":
            P("L14", f"주문 id 모양이 다름 {o['id']}")
        if o["status"] not in ORDER_STATUS:
            P("L14", f"주문 {o['id']} 상태 {o['status']!r}")
            continue
        if o["created_on"] not in day_ix:
            P("L14", f"주문 {o['id']} 생긴 날 {o['created_on']} 이 처리한 봉이 아님")
        if o["status"] == "pending":
            if o["id"] not in pend_ids:
                P("L14", f"pending 주문 {o['id']} 이 대기 목록에 없음")
            end = None
        else:
            end = o.get("done_date")
            if end not in day_ix or not end > o["created_on"]:
                P("L14", f"주문 {o['id']} 끝난 날 {end!r} 이 이상함")
            if o["status"] == "filled" and fill_count.get(o["id"], 0) != 1:
                P("L14", f"filled 주문 {o['id']} 의 체결이 {fill_count.get(o['id'], 0)}개")
            if o["status"] == "skipped":
                ss = [s for s in skips if s.get("order_id") == o["id"]]
                if len(ss) != 1 or ss[0]["date"] != end or ss[0]["kind"] != o.get("why"):
                    P("L14", f"skipped 주문 {o['id']} 와 보류 기록이 맞지 않음")
        for dt in dates:                           # 생긴 다음 처리 봉 ~ 끝난 날 전: 정지로만 기다렸어야 함
            if dt <= o["created_on"] or (end is not None and dt >= end):
                continue
            if o["code"] not in halted_on.get(dt, ()):
                P("L4", f"주문 {o['id']} 이 정지가 아닌 날 {dt} 에 체결되지 않고 남음", dt)
    for oid in pend_ids:
        if oid not in by_id or by_id[oid]["status"] != "pending":
            P("L14", f"대기 주문 {oid} 의 주문 기록이 없거나 pending 이 아님")
    for o in pending:
        if o["action"] == "매수" and o["code"] in positions:
            P("L5", f"보유 종목 {o['code']} 의 매수 주문이 대기 중")
        if o["action"] == "매도" and o["code"] not in positions:
            P("L5", f"보유하지 않은 {o['code']} 의 매도 주문이 대기 중")
    if len(positions) + sum(1 for o in pending if o["action"] == "매수") > team.MAX_POSITIONS:
        P("L5", "보유 + 매수 대기 > MAX_POSITIONS")

    # ---- L12 보류 ----
    for s in skips:
        dt, kind = s["date"], s["kind"]
        if dt not in day_ix:
            P("L12", f"처리한 봉이 아닌 날 보류 {s['code']}", dt)
        if kind not in SKIP_KINDS:
            P("L12", f"모르는 보류 종류 {kind!r}", dt)
        elif kind == "현금부족":
            need, avail = s.get("need"), s.get("avail")
            if not (_isnum(need) and _isnum(avail)):
                P("L12", f"현금부족 보류 {s['code']} 에 need·avail 이 없음", dt)
            else:
                ok = need > avail * (1 - h1.SHORT_MARGIN) if arm == "A1" else need > avail
                if not ok:
                    P("L12", f"현금부족 보류 {s['code']} 인데 필요 {need!r} ≤ 가능 {avail!r}", dt)
        elif kind == "0주":
            px = s.get("price")
            if not _isnum(px) or shares_within_cap(start_cash, cap, px, fee, slip) != 0:
                P("L12", f"0주 보류 {s['code']} 인데 상한 안에서 살 수 있음 (가격 {px!r})", dt)

    # ---- 원장 다시 걷기: L7·L8·L10·L15·L23 ----
    regs = {ca["code"]: ca for ca in d["corp_actions"] if ca.get("kind") == "delist"}
    fills_on = {}
    for f in fills:
        fills_on.setdefault(f["date"], []).append(f)
    shares = {}
    prev_cash, prev_units = start_cash, 0.0           # S 날 = 0 + 입금
    for i, row in enumerate(days):
        dt = row["date"]
        cur_cash, cur_units = prev_cash, prev_units
        for f in fills_on.get(dt, []):
            if not _cash_ok(f["cash_before"], cur_cash):
                P("L8", f"체결 전 현금 {f['cash_before']!r} ≠ 원장 {cur_cash!r} ({f['code']})", dt)
            if not _rel_ok(f["units_before"], cur_units):
                P("L8", f"체결 전 지수 단위 {f['units_before']!r} ≠ 원장 {cur_units!r}", dt)
            if not _cash_ok(f["cash_before"] + f["cash_delta"], f["cash_after"]):
                P("L8", f"체결 전 현금 + 변화 ≠ 체결 뒤 현금 ({f['code']})", dt)
            cur_cash = f["cash_after"]
            if f["kind"] == "idle":
                exp_u = cur_units + f["qty"] if f["side"] == "buy" else cur_units - f["qty"]
                if not _rel_ok(f["units_after"], exp_u):
                    P("L8", f"지수 단위 원장 {f['units_after']!r} ≠ {exp_u!r}", dt)
                cur_units = f["units_after"]
            else:
                if not _rel_ok(f["units_after"], f["units_before"]):
                    P("L8", f"주식 체결에서 지수 단위가 바뀜 ({f['code']})", dt)
                c = f["code"]
                if f["side"] == "buy":
                    if shares.get(c):
                        P("L5", f"이미 보유한 {c} 를 또 매수", dt)
                    shares[c] = shares.get(c, 0) + f["qty"]
                else:
                    if shares.get(c, 0) != f["qty"]:
                        P("L23" if f["purpose"] == "delist" else "L8",
                          f"{c} 매도 수량 {f['qty']} ≠ 그 직전 보유 {shares.get(c, 0)}", dt)
                    shares[c] = shares.get(c, 0) - f["qty"]
                    if f["purpose"] == "delist":
                        reg = regs.get(c)
                        if reg is None:
                            P("L23", f"상장폐지 등록이 없는 {c} 정리", dt)
                        else:
                            if not dt > reg["last_date"]:
                                P("L23", f"{c} 정리일 {dt} ≤ 등록 마지막 거래일 {reg['last_date']}", dt)
                            if f["price"] != reg["last_close"]:
                                P("L23", f"{c} 정리 가격 {f['price']!r} ≠ 등록 마지막 종가 {reg['last_close']!r}", dt)
        if not _cash_ok(cur_cash, row["cash"]):
            P("L8", f"현금 원장: 전날 {prev_cash!r} + 체결 = {cur_cash!r} ≠ 기록 {row['cash']!r}", dt)
        if not _rel_ok(cur_units, row["idle_units"]):
            P("L8", f"지수 단위 원장 {cur_units!r} ≠ 기록 {row['idle_units']!r}", dt)
        held = {c: q for c, q in shares.items() if q}
        marks = row["marks"]
        if set(marks) != set(held):
            P("L7", f"marks 종목 {sorted(marks)} ≠ 그날 보유 {sorted(held)}", dt)
        stock_v = sum(q * marks[c] for c, q in held.items() if c in marks)
        idle_v = row["idle_units"] * row["idle_close"]
        if not _rel_ok(stock_v, row["stock_value"]):
            P("L7", f"주식 평가 {row['stock_value']!r} ≠ Σ수량×marks {stock_v!r}", dt)
        if not _rel_ok(idle_v, row["idle_value"]):
            P("L7", f"지수 평가 {row['idle_value']!r} ≠ 단위×종가 {idle_v!r}", dt)
        if not _rel_ok(row["cash"] + stock_v + idle_v, row["value"]):
            P("L7", f"평가액 {row['value']!r} ≠ 현금+주식+지수 {row['cash'] + stock_v + idle_v!r}", dt)
        # L5 그날 종가 뒤 보유 + 매수 대기 ≤ 5
        if len(held) + _pending_buys_at_close(orders, dt) > team.MAX_POSITIONS:
            P("L5", "그날 보유 + 매수 대기 > MAX_POSITIONS", dt)
        # L23 등록 마지막 거래일 뒤에도 남은 보유·대기
        for c, reg in regs.items():
            if dt > reg["last_date"] and (c in held or c in _pending_codes_at_close(orders, dt)):
                P("L23", f"상장폐지 등록 {c} 가 {dt} 종가에도 보유·대기에 남음", dt)
        # L10 A1
        if arm == "A1":
            if i == 0:
                if not _cash_ok(row["cash"], start_cash) or row["idle_units"] != 0 or fills_on.get(dt):
                    P("L10", "S 날 A1 은 입금만(현금 = 시작 금액, 지수 0, 체결 0)", dt)
            else:
                if not row["cash"] < h1.SWEEP_MIN:
                    P("L10", f"A1 종가 현금 {row['cash']!r} ≥ {h1.SWEEP_MIN} (쓸어 담기 누락)", dt)
                if i == 1:
                    fl = fills_on.get(dt, [])
                    if not fl or not (fl[0]["kind"] == "idle" and fl[0]["side"] == "buy"
                                      and fl[0]["purpose"] == "start"):
                        P("L10", "S+1 첫 체결이 purpose='start' 지수 매수가 아님", dt)
        prev_cash, prev_units = row["cash"], row["idle_units"]
    if arm == "A1":
        starts = [f for f in fills if f["purpose"] == "start"]
        if len(starts) > 1 or (starts and (len(days) < 2 or starts[0]["date"] != days[1]["date"])):
            P("L10", "purpose='start' 지수 매수는 S+1 에 한 번만")
    # 끝 상태 = 지갑
    if days:
        if not _cash_ok(prev_cash, w["cash"]):
            P("L8", f"마지막 하루 기록 현금 {prev_cash!r} ≠ 지갑 현금 {w['cash']!r}")
        units_w = holds[idle]["shares"] if idle in holds else 0.0
        if not _rel_ok(prev_units, units_w):
            P("L8", f"마지막 하루 기록 지수 단위 {prev_units!r} ≠ 지갑 {units_w!r}")
        held = {c: q for c, q in shares.items() if q}
        if held != {c: p["shares"] for c, p in positions.items()}:
            P("L8", f"체결로 다시 센 보유 {held} ≠ positions")
        last = days[-1]
        prices = {**last["marks"], idle: last["idle_close"]}
        if all(c in prices for c in holds):
            wv = w["cash"] + sum(h["shares"] * prices[c] for c, h in holds.items())
            if not _rel_ok(wv, last["value"]):
                P("L7", f"마지막 평가액 {last['value']!r} ≠ wallet.value(가격표) {wv!r}", last["date"])
        else:
            P("L7", "마지막 하루 기록 가격표에 없는 보유가 있음", last["date"])

    # ---- L15 보유일수 ----
    for code, pos in positions.items():
        buys = [f for f in fills if f["kind"] == "stock" and f["side"] == "buy" and f["code"] == code]
        if not buys:
            P("L15", f"{code} 매수 체결 기록이 없음")
            continue
        b = buys[-1]
        if pos.get("buy_date") != b["date"] or pos.get("buy_price") != b["price"]:
            P("L15", f"{code} 매수일·매수가가 체결 기록과 다름")
        want = sum(1 for row in days if row["date"] > b["date"] and code not in halted_on[row["date"]])
        if pos.get("days_held") != want:
            P("L15", f"{code} 보유일수 {pos.get('days_held')} ≠ 정지 아닌 처리 봉 수 {want}")

    # ---- L17(장부 하나 쪽)·L19 팀장 ----
    for row in days:
        dt = row["date"]
        entries = row.get("leader") or []
        for e in entries:
            key = h1.decision_key(market, dt, tname, e["code"])
            if e.get("key") != key:
                P("L17", f"팀장 열쇠 {e.get('key')!r} ≠ {key}", dt)
            if decisions is not None:
                rec = decisions.get(key)
                if rec is None:
                    P("L17", f"판정 기록에 열쇠 {key} 가 없음", dt)
                elif e.get("verdict") != (rec.get("verdict") if rec.get("source") == "llm" else None):
                    P("L17", f"{e['code']} 하루 기록 판정 {e.get('verdict')!r} ≠ 판정 기록 {rec.get('verdict')!r}", dt)
            if e.get("effect") not in EFFECTS:
                P("L19", f"{e['code']} 효과 {e.get('effect')!r}", dt)
        created = [o for o in orders if o["created_on"] == dt and o["origin"] == "candidate"]
        ordered = [e for e in entries if e.get("effect") == "ordered"]
        ranked = sorted([e for e in entries if e.get("effect") in ("ordered", "over_slots")],
                        key=lambda e: _conviction_of(decisions, e.get("key")) or 0, reverse=True)
        n_ord = len(ordered)
        if decisions is None:                      # 확신도를 모르면 순서는 못 보고 대상만 본다
            if sorted(e["code"] for e in ordered) != sorted(o["code"] for o in created):
                P("L19", "주문 대상이 팀장 효과 'ordered' 와 다름", dt)
        elif [e["code"] for e in ranked[:n_ord]] != [o["code"] for o in created] \
                or any(e["effect"] != "ordered" for e in ranked[:n_ord]):
            P("L19", "주문 순서·대상이 '확신도 높은 순(같으면 스크리너 순서)'과 다름", dt)
        if row["over_slots"] != len(ranked) - n_ord:
            P("L19", f"over_slots {row['over_slots']} ≠ 빈자리 부족 후보 {len(ranked) - n_ord}", dt)
        if len(ranked) > n_ord:                    # 빈자리가 모자랐으면 그날 빈자리를 다 채웠어야 함
            held_now = {c for c, q in _shares_after(fills, dt).items() if q}
            if len(held_now) + _pending_buys_at_close(orders, dt) != team.MAX_POSITIONS:
                P("L19", "빈자리 부족 후보가 있는데 보유 + 매수 대기 ≠ MAX_POSITIONS", dt)
        for e in entries:
            conv = _conviction_of(decisions, e.get("key"))
            v = e.get("verdict")
            if v == "veto":
                want = "veto"
            elif v == "hold":
                want = "hold"
            elif decisions is None:                # 확신도를 모름 → 셋 중 하나면 받아 준다
                want = ("low_conv", "ordered", "over_slots")
            elif conv is not None and conv < team.CONV_MIN:
                want = "low_conv"
            else:
                want = ("ordered", "over_slots")
            if (e.get("effect") not in want) if isinstance(want, tuple) else (e.get("effect") != want):
                P("L19", f"{e['code']} 판정 {v!r}·확신도 {conv!r} 인데 효과 {e.get('effect')!r}", dt)
            if e.get("effect") in ("veto", "hold", "low_conv") and any(o["code"] == e["code"] for o in created):
                P("L19", f"{e['code']} 는 {e['effect']} 인데 매수 주문이 생김", dt)
            kind = {"hold": "팀장hold", "low_conv": "확신도낮음"}.get(e.get("effect"))
            if kind and not any(s["date"] == dt and s["code"] == e["code"] and s["kind"] == kind for s in skips):
                P("L19", f"{e['code']} {e['effect']} 인데 보류 기록({kind})이 없음", dt)

    # ---- L20 그림자 서킷 ----
    prev, seen_first = None, False
    for row in days:
        hit = CircuitBreaker(*h1.SHADOW_BREAKER).check(start_cash, prev, row["value"])
        evs = [e for e in (row.get("events") or []) if e.get("kind") == "shadow_breaker"]
        if hit:
            if len(evs) != 1 or evs[0].get("why") != hit or evs[0].get("first") != (not seen_first):
                P("L20", f"그림자 서킷 사건이 다시 계산한 결과와 다름(걸림: {hit[:20]}…)", row["date"])
            seen_first = True
        elif evs:
            P("L20", "그림자 서킷이 걸리지 않는 날에 사건 기록", row["date"])
        prev = row["value"]

    # ---- L22 코드·환경 지문 ----
    if allowed is not None:
        for row in days:
            if (row.get("code_hash"), h1.env_key(row.get("env"))) not in allowed:
                P("L22", f"허용 목록에 없는 코드·환경으로 처리한 봉 (code_hash {str(row.get('code_hash'))[:12]}…)",
                  row["date"])

    # ---- L3·L6 (그날 주식 시세가 있을 때) ----
    if frames is not None:
        for f in fills:
            if f["kind"] != "stock" or f["purpose"] == "delist":
                continue
            _check_stock_price(P, frames, f)


def _shares_after(fills, d):
    """d 날 체결까지 반영한 주식 보유 수량."""
    sh = {}
    for f in fills:
        if f["date"] > d or f["kind"] != "stock":
            continue
        sh[f["code"]] = sh.get(f["code"], 0) + (f["qty"] if f["side"] == "buy" else -f["qty"])
    return sh


def _check_stock_price(P, frames, f):
    dt, code = f["date"], f["code"]
    df = frames.get(code) if hasattr(frames, "get") else None
    row = None
    if df is not None:
        hits = [i for i, x in enumerate(df.index) if x.date().isoformat() == dt]
        row = df.iloc[hits[0]] if len(hits) == 1 else None
    if row is None:
        P("L6", f"{code} 체결일에 확정 행이 없음", dt)
        return
    if f["price"] != main.open_price(row):
        P("L3", f"{code} 체결가 {f['price']!r} ≠ 그날 시가 {main.open_price(row)!r}", dt)


def check_ledger(market, arm, states, calendar=None, decisions=None, allowed=None, *, frames=None) -> list:
    """한 장부(arm)의 트레이너 장부 전부를 저장 자료만으로 다시 점검한다. states = {trainer: st}."""
    market = main.mkt(market).key
    out = _Out(market)
    for tname, st in states.items():
        try:
            _check_one(out, market, arm, tname, st, calendar, decisions, allowed, frames)
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as e:
            out.add("L24", f"장부 모양이 깨져 점검을 끝낼 수 없음: {type(e).__name__}: {e}", arm, tname)
    return out.items


def check_pair(market, a0, a1, decisions=None) -> list:
    """A0 ↔ A1 짝 점검. a0·a1 = {trainer: st}."""
    market = main.mkt(market).key
    out = _Out(market)
    try:
        for tname in sorted(set(a0) | set(a1)):
            if tname not in a0 or tname not in a1:
                out.add("L16", "두 장부의 트레이너가 다름", None, tname)
                continue
            x, y = _plain(a0[tname]), _plain(a1[tname])
            dx, dy = [r["date"] for r in x["days"]], [r["date"] for r in y["days"]]
            if dx != dy:
                out.add("L16", "A0·A1 하루 기록 날짜가 다름", None, tname)
            if x["start_date"] != y["start_date"] or x["start_cash"] != y["start_cash"]:
                out.add("L16", "A0·A1 시작일·시작 금액이 다름", None, tname)
            rx = {r["date"]: r for r in x["days"]}
            for r in y["days"]:
                o = rx.get(r["date"])
                if o is None:
                    continue
                if o.get("screened") != r.get("screened"):
                    out.add("L17", "A0·A1 스크리너 후보가 다름", None, tname, r["date"])
                lx = {e["code"]: e for e in o.get("leader") or []}
                for e in r.get("leader") or []:
                    f = lx.get(e["code"])
                    if f is not None and (f.get("key") != e.get("key") or f.get("verdict") != e.get("verdict")):
                        out.add("L17", f"{e['code']} A0·A1 팀장 열쇠·판정이 다름", None, tname, r["date"])
            delist_x = sorted((f["code"], f["date"]) for f in x["fills"] if f.get("purpose") == "delist")
            delist_y = sorted((f["code"], f["date"]) for f in y["fills"] if f.get("purpose") == "delist")
            if delist_x != delist_y:
                out.add("L23", f"두 장부의 상장폐지 정리가 다름 {delist_x} vs {delist_y}", None, tname)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        out.add("L24", f"장부 모양이 깨져 짝 점검을 끝낼 수 없음: {type(e).__name__}: {e}")
    return out.items


def check_decisions(market, decisions, head=None) -> list:
    """판정 기록 L18: 열쇠 중복 없음, HEAD 에 적힌 (줄 수, 앞부분 sha256) 그대로."""
    market = main.mkt(market).key
    out = _Out(market)
    if decisions is None:
        return out.items
    seen = set()
    for r in decisions.records():
        k = r.get("key")
        if k in seen:
            out.add("L18", f"판정 기록 열쇠 중복 {k}")
        seen.add(k)
    if head is not None:
        n, sha = head
        have, got = decisions.prefix_digest(n)
        if have != n or got != sha:
            out.add("L18", f"판정 기록 앞 {n}줄이 HEAD 에 적은 것과 다름(지난 줄이 바뀜·사라짐)")
    return out.items


def _norm_ledger(st):
    """비교용: JSON 모양(지갑 dict). 하위 칸은 그대로(JSON 왕복한 값이면 == 로 비교 가능)."""
    return _plain(st)


def _check_transition(out, market, arm, tname, b, a, date, frames, idle, halted):
    def P(code, detail, when=None):
        out.add(code, detail, arm, tname, when or date)

    b, a = _norm_ledger(b), _norm_ledger(a)
    nb = len(b["fills"])
    if a["fills"][:nb] != b["fills"]:
        P("L8", "처리 전 체결 기록이 바뀜")
    if any(f["date"] != date for f in a["fills"][nb:]):
        P("L4", "새 체결의 날짜가 처리한 봉이 아님")
    ns = len(b["skips"])
    if a["skips"][:ns] != b["skips"]:
        P("L12", "처리 전 보류 기록이 바뀜")
    if any(s["date"] != date for s in a["skips"][ns:]):
        P("L12", "새 보류의 날짜가 처리한 봉이 아님")
    if a["days"][:-1] != b["days"] or len(a["days"]) != len(b["days"]) + 1 or a["days"][-1]["date"] != date:
        P("L16", "하루 기록이 '전날까지 그대로 + 오늘 한 줄'이 아님")
    if a["corp_actions"] != b["corp_actions"]:
        P("L23", "봉 처리 중 기업 행위 기록이 바뀜")
    if a["start_cash"] != b["start_cash"] or a["start_date"] != b["start_date"]:
        P("L8", "시작 금액·시작일이 바뀜")
    # 주문: 끝난 주문은 그대로, pending 은 그대로이거나 오늘 끝남, 새 주문은 오늘 생기고 pending
    no = len(b["orders"])
    for ob, oa in zip(b["orders"], a["orders"][:no]):
        if ob["status"] != "pending":
            if oa != ob:
                P("L14", f"끝난 주문 {ob['id']} 이 바뀜")
        elif oa != ob:
            same = {k: v for k, v in oa.items() if k not in ("status", "done_date", "why")} == \
                   {k: v for k, v in ob.items() if k not in ("status", "done_date", "why")}
            if not same or oa["status"] not in ORDER_STATUS[1:] or oa.get("done_date") != date:
                P("L14", f"주문 {ob['id']} 이 규칙 밖으로 바뀜")
    if len(a["orders"]) < no:
        P("L14", "주문 기록이 줄어듦")
    for o in a["orders"][no:]:
        if o["created_on"] != date or o["status"] != "pending":
            P("L14", f"새 주문 {o['id']} 이 오늘 생긴 pending 이 아님")
    before_pending = {h1.order_id(o) for o in b["pending"]}
    for f in a["fills"][nb:]:
        if f["kind"] == "idle":
            if f["price"] != idle.open:
                P("L3", f"지수 체결가 {f['price']!r} ≠ 그날 지수 시가 {idle.open!r}")
            continue
        if f["purpose"] == "delist":
            continue
        if f["order_id"] not in before_pending:
            P("L14", f"체결 {f['code']} 의 주문 {f['order_id']} 이 전날 끝에 대기 중이 아니었음")
        if f["code"] in halted:
            P("L6", f"거래정지 종목 {f['code']} 체결")
        if frames is not None:
            _check_stock_price(P, frames, f)
    row = a["days"][-1] if a["days"] else None
    if row is not None and row["date"] == date:
        if row["idle_open"] != idle.open or row["idle_close"] != idle.close:
            P("L3", "하루 기록의 지수 시가·종가가 그날 지수 봉과 다름")
        if sorted(row.get("halted") or ()) != sorted(halted):
            P("L6", "하루 기록의 정지 목록이 그날 정지 목록과 다름")
        if frames is not None:
            for c, px in row["marks"].items():
                df = frames.get(c)
                if df is None or len(df) == 0:
                    P("L7", f"{c} marks 를 맞춰 볼 시세가 없음")
                    continue
                last = float(df["Close"].iloc[-1])
                if px != last:
                    P("L7", f"{c} marks {px!r} ≠ 그날 이하 마지막 종가 {last!r}")


def check_day(market, date, before, after, frames, idle, calendar, halted, decisions, allowed, *, head=None,
              universe_sha256=None, meta_universe_sha256=None) -> list:
    """봉 date 처리 전후 장부 6개 점검 (h1.run_bar 가 저장 직전에 부른다).
    before/after = {arm: {trainer: st}}. frames = 그 실행이 쓴 확정 시세(date 이하로 자른 것).
    idle = 그날 IdleBar. calendar = 달력 날짜 목록(None 이면 달력 비교 생략). halted = 그날 정지 종목.
    decisions = DecisionLog. allowed = L22 허용 {(code_hash, env_key)} (None 이면 생략).
    head = HEAD 의 (판정 기록 줄 수, 앞부분 sha256) (None 이면 생략).
    universe_sha256·meta_universe_sha256 = 종목군 파일 지문과 meta 에 적힌 값(둘 다 주면 비교, L22)."""
    market = main.mkt(market).key
    halted = frozenset(halted or ())
    probs = []
    out = _Out(market)
    for arm in h1.ARMS:
        probs += check_ledger(market, arm, after[arm], calendar, decisions, allowed)
        for tname in h1.TRAINERS:
            try:
                _check_transition(out, market, arm, tname, before[arm][tname], after[arm][tname], date, frames,
                                  idle, halted)
            except (KeyError, TypeError, AttributeError, ValueError, IndexError) as e:
                out.add("L24", f"장부 모양이 깨져 전후 점검을 끝낼 수 없음: {type(e).__name__}: {e}", arm, tname, date)
            st = after[arm][tname]
            if st.get("last_date") != date:
                out.add("L16", f"last_date {st.get('last_date')} ≠ 처리한 봉 {date}", arm, tname, date)
    if calendar is not None and date not in calendar:
        out.add("L16", f"처리한 봉 {date} 이 달력에 없음", date=date)
    probs += out.items
    probs += check_pair(market, after["A0"], after["A1"], decisions)
    probs += check_decisions(market, decisions, head)
    if universe_sha256 is not None and meta_universe_sha256 is not None and universe_sha256 != meta_universe_sha256:
        probs.append(Problem("L", "L22", market, None, None, date, "종목군 파일 지문 ≠ meta.universe_sha256"))
    return probs
