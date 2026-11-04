"""
order_runner.py - 장부의 '대기 주문(pending)'을 증권사 지정가 주문으로 내고, 체결을 장부와 맞춰 본다 (K3)
---------------------------------------------------------------------------------------
docs/kr-broker-design.md §2 K-D2~K-D5, §3 의 order_runner 부분.

두 단계 실행(K-D2):
  1) 장 마감 후  `team.py` 가 신호를 state 의 pending 에 저장한다(장부 = paper_wallet, 정답).
  2) 다음 장 개장 직후  `python order_runner.py place ...`  → pending 을 지정가 주문으로 낸다.
  3) 장 마감 후  `python order_runner.py reconcile ...` → 그날 체결을 조회해 장부와 비교한 보고서를 쓴다.
  (자세한 시간표는 docs/broker-run.md)

초보자용 설명:
- 장부(paper_wallet)가 정답이다(K-D3). 증권사 모의계좌는 "주문이 정말 들어가고 체결되는가" 확인용.
  그래서 이 파일은 장부(state/*.json)를 **읽기만** 하고 절대 고치지 않는다.
- 지정가(K-D5) = 신호 봉 종가 × (1 ± 0.5%) 를 호가단위로 맞춘 값. 매수는 올림, 매도는 내림.
  → 다음날 시가가 조금 움직여도 체결될 여유를 두되, 너무 비싸게/싸게 사고팔지는 않게.
- 매수 수량 = 상한(예산×종목상한) 안에서 살 수 있는 수(shares_within_cap)와
  증권사 매수가능수량 중 **작은 값**. 0주면 주문을 내지 않고 사유를 기록한다.
- 매도 수량 = 장부에 있는 보유 수량.
- 주문은 **재시도하지 않는다**(K-D4). 같은 주문(client_id)이 두 번 나가는 게 제일 위험하기 때문.
  state/broker/<시장>-orders.jsonl 에 "보내는 중" 을 먼저 적고 나서 보내므로,
  보내다가 프로그램이 꺼져도 다음 실행에서 같은 주문을 다시 내지 않는다.
- 모의투자 기간 만료(mock_expired)·인증 오류(auth)가 나면 크게 알리고 남은 주문을 멈춘다.
  (그 외 오류는 그 주문만 실패로 적고 다음 주문으로 넘어간다.)

실행:
    python order_runner.py place     --market kr --broker paper
    python order_runner.py reconcile --market kr --broker paper [--date 2026-11-05]
"""

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import main                      # CONFIG(종목상한), load_prices
import markets                   # K4: round_to_tick, get_market, money
from paper_wallet import DEFAULT_FEE_RATE, DEFAULT_SLIPPAGE, shares_within_cap
from broker import Order, OrderResult   # K1: §3 의 자료형

ROOT = Path(__file__).parent
STATE_DIR = ROOT / "state"       # team 상태 파일과 주문 기록(state/broker/)이 있는 곳 (테스트에서 바꿔 끼움)
REPORTS_DIR = ROOT / "reports"   # reconcile 보고서(reports/broker/)

LIMIT_PAD = 0.005                # K-D5: 지정가 = 종가 × (1 ± 0.5%)
SIDES = {"매수": "buy", "매도": "sell"}
SIDE_KO = {"buy": "매수", "sell": "매도"}

# 이 오류가 나면 남은 주문도 어차피 다 실패하므로 멈춘다 (계좌 자체가 막힘)
STOP_KINDS = {"mock_expired", "auth"}
# 이 오류는 "증권사가 주문을 확실히 안 받았다"는 뜻 → 다음 거래일에는 다시 낼 수 있다(같은 날은 안 냄).
# network·unknown(또는 결과를 모름)은 실제로 들어갔을 수도 있으므로 **영원히** 다시 내지 않는다.
NOT_ACCEPTED_KINDS = {"rejected", "mock_expired", "auth", "rate_limit"}

FILLS_TRIES = 3                  # 체결 '조회'는 재시도해도 안전하다(주문이 아니니까)
SLEEP = time.sleep               # 테스트에서 기다리지 않게 바꿔 끼움


# ---------------- 경로 ----------------

def trainers():
    """트레이너 이름 목록 (배분비율 순서: 마라토너, 스프린터, 파이오니어)."""
    return list(main.CONFIG["배분비율"])


def state_path(market_key, trainer):
    """K-D11: 미국 state/team_<트레이너>.json (예전 그대로), 국내 state/kr/team_<트레이너>.json."""
    base = STATE_DIR if market_key == "us" else STATE_DIR / market_key
    return base / f"team_{trainer}.json"


def journal_path(market_key):
    return STATE_DIR / "broker" / f"{market_key}-orders.jsonl"


def report_path(market_key, day):
    return REPORTS_DIR / "broker" / f"{market_key}-{day}.md"


# ---------------- 작은 도우미 ----------------

def client_id(market, trainer, code, side, signal_date):
    """broker.Order.client_id 와 같은 규칙(§3). 주문을 만들기 전(보류 기록 등)에도 쓰려고 따로 둔다."""
    return f"{market}-{trainer}-{code}-{side}-{signal_date}"


def _get(obj, key, default=None):
    """dict 든 객체(PaperWallet 등)든 같은 방식으로 값 꺼내기."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _num(v):
    """숫자로 바꿔서 0보다 큰 정상 숫자면 그 값, 아니면 None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _to_dict(obj):
    if is_dataclass(obj):
        return asdict(obj)
    return dict(vars(obj))


def _money(market_key, v):
    try:
        return markets.money(market_key, v, sign=False)
    except Exception:
        return f"{v:,.2f}"


def _price(market_key, v):
    """주가 표시. 미국은 센트까지($123.45), 국내는 원 단위."""
    if v is None:
        return "-"
    if market_key == "us":
        return f"${v:,.2f}"
    return _money(market_key, v)


def _now(market_key, now=None):
    """시장 현지 시각. now 에 시간대가 없으면 그 시장의 현지 시각으로 본다."""
    tz = ZoneInfo(markets.get_market(market_key).tz)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def held_shares(st, code):
    """장부 보유 수량. positions 를 먼저 보고, 없으면 지갑 holdings 를 본다."""
    pos = (_get(st, "positions") or {}).get(code)
    n = _num(_get(pos, "shares")) if pos else None
    if n:
        return int(n)
    h = (_get(_get(st, "wallet") or {}, "holdings") or {}).get(code)
    n = _num(_get(h, "shares")) if h else None
    return int(n) if n else 0


def limit_price(market_key, close, side):
    """K-D5: 신호 봉 종가 × (1 ± 0.5%) → 호가단위. 매수는 올림(더 비싸게라도 사지게), 매도는 내림."""
    raw = close * (1 + LIMIT_PAD) if side == "buy" else close * (1 - LIMIT_PAD)
    return markets.round_to_tick(market_key, raw, side)


def _close_for(last_close, code, signal_date):
    """last_close 에서 종가 찾기. 키는 (종목, 신호일) 또는 종목 하나 — 둘 다 받아 준다."""
    v = last_close.get((code, signal_date))
    if v is None:
        v = last_close.get(code)
    return _num(v)


def _ask_buyable(buyable, code, price):
    """증권사 매수가능수량. 모르면(None·오류) None → 상한 계산만으로 정한다."""
    if buyable is None:
        return None
    try:
        v = buyable(code, price) if callable(buyable) else buyable.get(code)
    except Exception:
        return None
    if v is None:
        return None
    try:
        return max(int(v), 0)
    except (TypeError, ValueError):
        return None


# ---------------- ① 주문 만들기 (순수 함수) ----------------

def build_orders(market_key, states, last_close, caps, buyable=None, skips=None):
    """team 상태들의 pending → 지정가 주문 목록. 파일·네트워크를 건드리지 않는다(순수 함수).

    states:     트레이너 → team 상태 dict (pending·wallet·positions·start_cash)
    last_close: 신호 봉 종가. {(종목, 신호일): 종가} 또는 {종목: 종가}
    caps:       트레이너 → 종목상한 비율 (main.CONFIG["종목상한"])
    buyable:    (선택) 증권사 매수가능수량. 함수 f(종목, 지정가) 또는 dict {종목: 주식 수}. 모르면 None.
    skips:      (선택) 리스트를 넘기면, 주문을 못 만든 이유를 여기에 dict 로 덧붙인다.
    """
    orders = []

    def skip(trainer, code, side, sd, reason):
        if skips is not None:
            skips.append({"client_id": client_id(market_key, trainer, code, side, sd),
                          "trainer": trainer, "code": code, "side": side,
                          "signal_date": sd, "reason": reason})

    for trainer, st in states.items():
        if not st:
            continue
        wallet = _get(st, "wallet") or {}
        fee = _get(wallet, "fee_rate", DEFAULT_FEE_RATE)
        slip = _get(wallet, "slippage", DEFAULT_SLIPPAGE)
        budget = _get(st, "start_cash")
        cap = caps.get(trainer)
        for p in _get(st, "pending") or []:
            code, sd = p.get("code"), p.get("signal_date")
            side = SIDES.get(p.get("action"))
            if side is None or not code or not sd:
                skip(trainer, code, side, sd, f"알 수 없는 주문 형식: {p!r}")
                continue
            close = _close_for(last_close, code, sd)
            if close is None:
                skip(trainer, code, side, sd, f"신호 봉({sd}) 종가를 못 구함")
                continue
            px = limit_price(market_key, close, side)

            if side == "sell":
                n = held_shares(st, code)
                if n <= 0:
                    skip(trainer, code, side, sd, "장부에 보유 수량이 없음")
                    continue
            else:
                if held_shares(st, code) > 0:
                    skip(trainer, code, side, sd, "장부에 이미 보유 중 (추가 매수 안 함)")
                    continue
                # 지정가로 계산: 실제 체결은 지정가 이하이므로, 이 수량이면 상한을 넘지 않는다
                n = shares_within_cap(budget, cap, px, fee, slip)
                if n <= 0:
                    limit = (budget or 0) * (cap or 0)
                    skip(trainer, code, side, sd,
                         f"상한 {_money(market_key, limit)} 안에서 1주도 못 삼 (지정가 {_price(market_key, px)})")
                    continue
                can = _ask_buyable(buyable, code, px)
                if can is not None and can < n:
                    if can <= 0:
                        skip(trainer, code, side, sd,
                             f"증권사 매수가능수량 0주 (상한 기준 {n}주, 지정가 {_price(market_key, px)})")
                        continue
                    n = can
            orders.append(Order(market=market_key, code=code, side=side, shares=int(n),
                                limit_price=px, trainer=trainer, signal_date=sd))
    return orders


# ---------------- 상태·주문 기록 읽기/쓰기 ----------------

def load_states(market_key, log=print):
    """트레이너별 team 상태(JSON 그대로). 파일이 없으면 빠진다. 장부는 읽기만 한다."""
    out = {}
    for t in trainers():
        path = state_path(market_key, t)
        if not path.exists():
            continue
        try:
            out[t] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log(f"  ⚠ {path.name} 을(를) 읽지 못해 건너뜀 ({type(e).__name__})")
    return out


def read_journal(market_key, log=print):
    """주문 기록(jsonl) 한 줄 = 한 사건. 깨진 줄은 건너뛴다(앞부분은 그대로 믿는다)."""
    path = journal_path(market_key)
    if not path.exists():
        return []
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            log(f"  ⚠ 주문 기록 {path.name} {i}번째 줄이 깨져 있어 건너뜀")
    return rows


def append_journal(market_key, row):
    """한 줄 덧붙이고 디스크에 확실히 쓴다(fsync). '보내는 중'이 꺼지기 전에 남아 있어야 하니까."""
    path = journal_path(market_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _attempts(journal):
    """client_id → 그 주문의 시도 목록 [{date, done, ok, kind}]. 보류(skipped) 줄은 시도가 아님."""
    out = {}
    for r in journal:
        cid, status = r.get("client_id"), r.get("status")
        if not cid or status not in ("sending", "done"):
            continue
        tries = out.setdefault(cid, [])
        if status == "sending":
            tries.append({"date": r.get("date"), "done": False, "ok": None, "kind": None})
        else:
            res = r.get("result") or {}
            # 바로 앞의 '보내는 중'을 완료로 바꾼다 (없으면 새 시도로)
            open_try = next((x for x in reversed(tries) if not x["done"]), None)
            if open_try is None:
                open_try = {"date": r.get("date")}
                tries.append(open_try)
            open_try.update(done=True, ok=bool(res.get("ok")), kind=res.get("error_kind"))
    return out


def blocked_reason(tries, today):
    """이 주문을 오늘 내면 안 되는 이유(없으면 None). '두 번 나가는 것'을 막는 규칙이 전부 여기 있다."""
    for t in tries:
        if not t["done"]:
            return "지난 실행에서 결과를 모름 (보내다 멈춤) — 증권사 앱에서 직접 확인하세요. 다시 내지 않음"
        if t["ok"]:
            return "이미 낸 주문"
        if t["kind"] not in NOT_ACCEPTED_KINDS:
            return f"지난 시도가 {t['kind'] or '알 수 없는'} 오류 — 들어갔을 수도 있어 다시 내지 않음"
        if t["date"] == today:
            return f"오늘 이미 시도했다가 거절됨({t['kind']}) — 재시도 안 함"
    return None


def signal_close(market_key, code, signal_date):
    """신호 봉(signal_date) 종가. 시세를 다시 받아 그 날짜 행의 종가를 쓴다. 못 구하면 None."""
    try:
        start = (_date.fromisoformat(signal_date) - timedelta(days=14)).isoformat()
        df = main.load_prices(code, start)
    except BaseException as e:     # load_prices 는 라이브러리 없으면 SystemExit 을 던진다
        if isinstance(e, KeyboardInterrupt):
            raise
        return None
    for ts, row in df.iterrows():
        if ts.date().isoformat() == signal_date:
            return _num(row["Close"])
    return None


# ---------------- ② 주문 내기 ----------------

BANNER = "!" * 64


def _warn_stop(kind, left, log):
    log(BANNER)
    if kind == "mock_expired":
        log(" 🛑 KIS 모의투자 기간이 끝났어요 (오류 40910000). 주문이 들어가지 않았습니다.")
        log("    KIS 홈페이지 → 모의투자 → 상시 모의투자 신청에서 기간을 다시 신청하세요.")
    else:
        log(" 🛑 증권사 인증 오류 — 앱 키/시크릿/계좌번호(.env) 또는 토큰을 확인하세요.")
    log(f"    남은 주문 {left}건은 내지 않고 멈춥니다. (기록 안 함 → 고친 뒤 다시 place 하면 나감)")
    log(BANNER)


def place(market_key, broker, now=None, close_fn=None, log=print):
    """pending → 지정가 주문. 실제로 보낸 주문의 OrderResult 목록을 돌려준다.

    now:      기준 시각(테스트용). 없으면 지금. 시간대 없으면 그 시장 현지 시각.
    close_fn: 신호 봉 종가 구하는 함수 f(market_key, 종목, 신호일) (테스트용). 기본은 시세를 받아 옴.
    """
    now = _now(market_key, now)
    today = now.date().isoformat()
    stamp = now.isoformat(timespec="seconds")
    log(f"[place] 시장 {market_key} · 브로커 {getattr(broker, 'name', '?')} · 현지 {stamp}")
    if now.weekday() >= 5:
        log("  주말이라 주문을 내지 않아요. (휴장일 거절도 기록되므로 평일 장중에만 돌리세요)")
        return []

    states = load_states(market_key, log)
    attempts = _attempts(read_journal(market_key, log))

    # 이미 냈거나 낼 수 없는 주문은 미리 뺀다 → 종가·매수가능수량을 괜히 묻지 않음
    todo = {}
    for t, st in states.items():
        keep = []
        for p in st.get("pending") or []:
            side = SIDES.get(p.get("action"))
            cid = client_id(market_key, t, p.get("code"), side, p.get("signal_date"))
            why = blocked_reason(attempts.get(cid, []), today)
            if why:
                log(f"  건너뜀 {cid}: {why}")
            else:
                keep.append(p)
        if keep:
            todo[t] = {**st, "pending": keep}
    if not todo:
        log("  낼 주문이 없어요.")
        return []

    close_fn = close_fn or signal_close
    last_close = {}
    for st in todo.values():
        for p in st["pending"]:
            key = (p.get("code"), p.get("signal_date"))
            if key not in last_close and all(key):
                last_close[key] = close_fn(market_key, *key)

    skips = []
    orders = build_orders(market_key, todo, last_close, main.CONFIG["종목상한"],
                          buyable=lambda code, px: broker.buyable_shares(market_key, code, px),
                          skips=skips)

    # 보류 사유 기록 (주문이 아니므로 다음 실행에서 다시 계산해도 안전. 같은 사유는 한 번만 적음)
    old = {(r.get("client_id"), r.get("date"), r.get("reason"))
           for r in read_journal(market_key, log) if r.get("status") == "skipped"}
    for s in skips:
        log(f"  보류 {s['client_id']}: {s['reason']}")
        if (s["client_id"], today, s["reason"]) not in old:
            append_journal(market_key, {"status": "skipped", "date": today, "time": stamp, **s})

    results = []
    for i, order in enumerate(orders):
        cid = order.client_id
        row = {"client_id": cid, "date": today, "time": stamp, "order": _to_dict(order)}
        append_journal(market_key, {"status": "sending", **row})   # 보내기 '전에' 먼저 적는다
        try:
            res = broker.place(order)
        except Exception as e:   # 프로토콜상 던지면 안 되지만, 던져도 멈추지 않고 기록
            res = OrderResult(client_id=cid, ok=False, broker_order_id=None,
                              error_kind=getattr(e, "kind", None) or "unknown",
                              message=f"{type(e).__name__}: {e}")
        append_journal(market_key, {"status": "done", **row, "result": _to_dict(res)})
        results.append(res)
        what = f"{SIDE_KO[order.side]} {order.code} {order.shares}주 @ {_price(market_key, order.limit_price)}"
        if res.ok:
            log(f"  주문 OK  {order.trainer} {what} (주문번호 {res.broker_order_id})")
        else:
            log(f"  주문 실패 {order.trainer} {what} — {res.error_kind}: {res.message}")
            if res.error_kind in STOP_KINDS:
                _warn_stop(res.error_kind, len(orders) - i - 1, log)
                break
    ok = sum(r.ok for r in results)
    log(f"  끝: 보냄 {len(results)}건 (성공 {ok}, 실패 {len(results) - ok}) · 보류 {len(skips)}건")
    return results


# ---------------- ③ 체결 맞춰 보기 ----------------

def _fetch_fills(broker, market_key, day, log):
    """그날 체결 조회. 조회는 재시도해도 안전하므로 network·rate_limit 이면 몇 번 더 묻는다."""
    for n in range(1, FILLS_TRIES + 1):
        try:
            return list(broker.fills(market_key, day)), None
        except Exception as e:
            kind = getattr(e, "kind", None) or "unknown"
            if kind in ("network", "rate_limit") and n < FILLS_TRIES:
                log(f"  체결 조회 실패({kind}) — {n}번째, 잠시 뒤 다시 조회")
                SLEEP(2 ** n)
                continue
            if kind in STOP_KINDS:
                _warn_stop(kind, 0, log)
            return [], f"{kind}: {type(e).__name__}: {e}"
    return [], "unknown"


def _ledger_entry(st, code, side, day):
    """장부(지갑 log)에서 그날 그 종목의 체결(또는 보류) 한 건. 없으면 None (team.py 가 아직 안 돔)."""
    if not st:
        return None
    wallet = st.get("wallet") or {}
    kind = SIDE_KO[side]
    hit = None
    for e in wallet.get("log") or []:
        if str(e.get("시각", ""))[:10] != day or e.get("종목") != code:
            continue
        if e.get("종류") == kind or (side == "buy" and e.get("종류") == "보류"):
            hit = e
    if hit is None:
        return None
    if hit.get("종류") == "보류":
        return {"skipped": True, "reason": hit.get("사유", "")}
    n = int(hit.get("수량") or 0)
    amt = float(hit.get("금액") or 0)
    fee = wallet.get("fee_rate", DEFAULT_FEE_RATE)
    slip = wallet.get("slippage", DEFAULT_SLIPPAGE)
    tax = wallet.get("sell_tax_rate", 0.0)
    pos = (st.get("positions") or {}).get(code)
    if side == "buy" and pos and pos.get("buy_date") == day:
        px = float(pos["buy_price"])          # 매수 시가 그대로 남아 있음
    elif n > 0:                               # 금액(비용·세금 포함)에서 시가를 거꾸로 계산
        per = (1 + slip) * (1 + fee) if side == "buy" else (1 - slip) * (1 - fee - tax)
        px = amt / (n * per)
    else:
        px = None
    return {"skipped": False, "shares": n, "price": px, "amount": amt}


def reconcile(market_key, broker, date=None, log=print):
    """그날(date, 시장 현지 날짜) 낸 주문 ↔ 증권사 체결 ↔ 장부를 비교해 보고서를 쓴다. 보고서 경로를 돌려준다.
    장부는 고치지 않는다(K-D3). 몇 번 돌려도 같은 보고서를 다시 쓸 뿐이다."""
    day = date or _now(market_key).date().isoformat()
    journal = read_journal(market_key, log)
    states = load_states(market_key, log)

    # 그날 시도한 주문 (client_id 별 마지막 상태)
    orders = {}
    for r in journal:
        if r.get("date") != day or r.get("status") not in ("sending", "done"):
            continue
        cur = orders.setdefault(r["client_id"], {"order": r.get("order") or {}, "result": None})
        if r["status"] == "sending":
            cur["result"] = None
        else:
            cur["result"] = r.get("result") or {}
    skips = {}
    for r in journal:
        if r.get("date") == day and r.get("status") == "skipped":
            skips[r["client_id"]] = r

    fills, fill_err = _fetch_fills(broker, market_key, day, log)
    by_id = {}
    for f in fills:
        by_id.setdefault(str(_get(f, "broker_order_id")), []).append(f)
    used = set()

    rows, counts = [], {}
    for cid, o in orders.items():
        od, res = o["order"], o["result"]
        side, code, want = od.get("side"), od.get("code"), int(od.get("shares") or 0)
        trainer = od.get("trainer", "?")
        got_n, got_px = 0, None
        if res is None:
            status = "결과 불명"
        elif not res.get("ok"):
            status = f"주문 오류({res.get('error_kind')})"
        else:
            boid = str(res.get("broker_order_id"))
            mine = [f for f in by_id.get(boid, []) if _get(f, "code") == code]
            used.add(boid)
            got_n = sum(int(_get(f, "shares") or 0) for f in mine)
            if got_n:
                got_px = sum(int(_get(f, "shares")) * float(_get(f, "price")) for f in mine) / got_n
            if got_n == 0:
                status = "미체결"
            elif got_n < want:
                status = "부분체결"
            else:
                status = None          # 장부와 비교해서 정한다
        led = _ledger_entry(states.get(trainer), code, side, day)
        if status is None:
            if led is None:
                status = "체결 (장부 미반영)"
            elif led["skipped"]:
                status = "장부는 보류"
            elif led["shares"] != got_n:
                status = "수량 다름"
            else:
                status = "일치"
        counts[status] = counts.get(status, 0) + 1
        if led is None:
            led_txt = "미반영"
        elif led["skipped"]:
            led_txt = f"보류 ({led['reason']})"
        else:
            led_txt = f"{led['shares']}주 @ {_price(market_key, led['price'])}"
        gap = "-"
        if got_px and led and not led["skipped"] and led.get("price"):
            gap = f"{(got_px / led['price'] - 1) * 100:+.2f}%"
        rows.append((trainer, code, SIDE_KO.get(side, side), want,
                     _price(market_key, od.get("limit_price")),
                     f"{got_n}주 @ {_price(market_key, got_px)}" if got_n else "0주",
                     led_txt, gap, status,
                     (res or {}).get("message", "") if res is not None and not res.get("ok") else ""))

    extra = [f for boid, fs in by_id.items() if boid not in used for f in fs]

    mk = markets.get_market(market_key)
    lines = [
        f"# 브로커 체결 맞춰 보기 — {market_key.upper()} {day}",
        "",
        f"- 브로커: `{getattr(broker, 'name', '?')}` · 통화 {mk.currency} · "
        f"작성 {datetime.now().isoformat(timespec='seconds')}",
        "- 장부(paper_wallet)가 정답이에요(K-D3). 이 보고서는 **차이를 기록**할 뿐 장부를 고치지 않아요.",
        "- 장부 가격 = 다음 봉 시가(비용·세금 빼기 전). 브로커 가격 = 실제 체결 평균가.",
        "",
        "## 요약",
        "",
        f"- 그날 낸 주문 {len(orders)}건 · 보류(주문 안 냄) {len(skips)}건 · 체결 내역 {len(fills)}줄",
    ]
    if counts:
        lines.append("- " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if fill_err:
        lines.append(f"- ⚠ 체결 조회 실패: {fill_err} → 아래 '미체결'은 실제와 다를 수 있어요")
    if any(r[6] == "미반영" for r in rows):
        lines.append("- '장부 미반영' = team.py 가 아직 이 날 봉을 처리하지 않음. team.py 실행 뒤 reconcile 을 다시 돌리면 채워져요.")
    lines += ["", "## 주문별", ""]
    if rows:
        lines.append("| 트레이너 | 종목 | 구분 | 주문 수량 | 지정가 | 브로커 체결 | 장부 체결 | 가격 차이 | 상태 | 메모 |")
        lines.append("|---|---|---|---:|---:|---|---|---:|---|---|")
        for r in rows:
            lines.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    else:
        lines.append("그날 낸 주문이 없어요.")
    lines += ["", "## 미체결·오류", ""]
    bad = [r for r in rows if r[8] in ("미체결", "부분체결", "결과 불명") or r[8].startswith("주문 오류")]
    if bad:
        for r in bad:
            memo = f" — {r[9]}" if r[9] else ""
            lines.append(f"- {r[0]} {r[2]} {r[1]} {r[3]}주: **{r[8]}**{memo}")
        if any(r[8] == "결과 불명" for r in bad):
            lines.append("- '결과 불명' 은 보내다 멈춘 주문이에요. 증권사 앱에서 실제로 들어갔는지 꼭 확인하세요.")
    else:
        lines.append("없음")
    lines += ["", "## 보류 (주문 안 냄)", ""]
    if skips:
        for s in skips.values():
            lines.append(f"- {s.get('trainer')} {SIDE_KO.get(s.get('side'), s.get('side'))} "
                         f"{s.get('code')}: {s.get('reason')}")
    else:
        lines.append("없음")
    lines += ["", "## 주문 기록에 없는 체결", ""]
    if extra:
        for f in extra:
            lines.append(f"- {SIDE_KO.get(_get(f, 'side'), _get(f, 'side'))} {_get(f, 'code')} "
                         f"{_get(f, 'shares')}주 @ {_price(market_key, _num(_get(f, 'price')))} "
                         f"(주문번호 {_get(f, 'broker_order_id')}) — 손으로 낸 주문인지 확인")
    else:
        lines.append("없음")

    path = report_path(market_key, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"[reconcile] {market_key} {day}: 주문 {len(orders)}건 · 체결 {len(fills)}줄 → {path}")
    return str(path)


# ---------------- 명령줄 ----------------

def cli(argv=None):
    ap = argparse.ArgumentParser(description="pending → 증권사 지정가 주문 / 체결 맞춰 보기")
    ap.add_argument("cmd", choices=["place", "reconcile"])
    ap.add_argument("--market", required=True, choices=["us", "kr"])
    ap.add_argument("--broker", default="paper", choices=["paper", "kis"])
    ap.add_argument("--date", help="reconcile 할 날짜 YYYY-MM-DD (시장 현지 날짜, 기본 오늘)")
    args = ap.parse_args(argv)
    if args.date:
        try:
            _date.fromisoformat(args.date)
        except ValueError:
            ap.error("--date 는 YYYY-MM-DD 형식이어야 해요")

    from broker import make_broker   # kis 는 여기서 늦게 import 된다 (K1)
    b = make_broker(args.broker)

    if args.cmd == "place":
        if args.date:
            print("  (참고) place 는 --date 를 쓰지 않아요. 항상 '지금' 기준으로 냅니다.")
        results = place(args.market, b)
        if any(not r.ok and r.error_kind in STOP_KINDS for r in results):
            return 2
        return 1 if any(not r.ok for r in results) else 0
    reconcile(args.market, b, args.date)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
