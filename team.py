"""
team.py - 팀장 오케스트레이터: 하루치 '전체 의사결정 루프' (가상, 진짜 돈 $0)
------------------------------------------------------------------
운영모델을 한 번에 돌린다:
  ① 어제 낸 주문(pending)을 오늘(새 확정 봉) 시가로 체결
  ② screener → 트레이너별 '매수' 후보 (부하가 넓은 종목군에서 스스로 선별)
  ③ analyst(claude -p) → 후보 위험점검·veto·hold·확신도 (팀장인 나의 분석; 없으면 규칙 폴백)
  ④ 규칙 → 보유종목 매도 판단 + 서킷 브레이커 + 신규 매수 → 전부 '다음 거래일 시가' 주문으로 저장
  ⑤ state/team_<트레이너>.json 저장 (임시파일에 쓴 뒤 한 번에 교체)
트레이너별 1개 포트폴리오 지갑(여러 종목 보유). 미국 = 달러 지갑, 국내 = 원화 지갑 (시장별로 완전히 따로).

v1 규칙 (docs/v1-design.md):
- '처리했나'는 달력 날짜가 아니라 마지막 확정 봉 날짜(SPY 기준)로 판단(D2).
  세 트레이너가 모두 그 봉까지 처리됐으면 스캔도 하지 않고 바로 끝난다(N5).
- 후보도 보유도 주문도 없는 날은 저장하지 않는다 → 데이터가 늦게 고쳐져도 다시 돌릴 수 있다.
- 신호는 봉 t 종가, 체결은 봉 t+1 시가(D3). 상한 안에서 1주도 못 사면 매수 보류 + 사유 로그(D5).

실행: python team.py [N] [--market us|kr]   (N = 스크리너가 훑을 종목 수, 기본 40 / 시장 기본 us)
  국내(--market kr, docs/kr-broker-design.md K-D7~K-D11):
  - 종목군은 markets.KR_UNIVERSE (KOSPI 대형주 약 30개 고정), 기준 날짜·비교는 KODEX 200(069500)
  - 확정 봉은 한국 시간 16:00 기준, 비용 수수료 0.015%·매도세 0.20%·슬리피지 0.05%, 가상자금 1,000만원
  - 상태 파일은 state/kr/team_<트레이너>.json (미국 state/team_<트레이너>.json 과 섞이지 않음)
"""

import sys
import math
from dataclasses import asdict
from pathlib import Path

import main
import screener
import analyst
import markets
from paper_wallet import PaperWallet, Holding, shares_within_cap
from sprinter_brain import SprinterBrain
from marathoner_brain import MarathonerBrain
from pioneer_brain import PioneerBrain
from risk_guard import CircuitBreaker

STATE_DIR = Path(__file__).parent / "state"
BRAINS = {"마라토너": MarathonerBrain, "스프린터": SprinterBrain, "파이오니어": PioneerBrain}
MAX_POSITIONS = 5          # 트레이너당 최대 보유 종목 수(과집중 방지). 매수 대기 주문도 센다
CONV_MIN = 0.5             # 팀장 확신도 최소선. 팀장이 이보다 낮게 본 후보는 매수 보류(hold 취급)
START = "2024-06-01"       # 지표 워밍업


def to_conviction(v):
    """팀장 확신도를 숫자로. 문자열("0.7")도 받아 주고, 숫자로 못 바꾸면 None(=무의견)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v.strip()) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def keep_candidate(c):
    """매수 후보를 남길지. 팀장 확신도가 CONV_MIN 미만이면 보류. conviction=None(팀장 부재)이면 통과(안전원칙)."""
    conv = to_conviction(c.get("conviction"))
    return conv is None or conv >= CONV_MIN


def _path(tname, mk=None):
    """상태 파일 경로. 미국 state/team_<트레이너>.json (지금 그대로), 국내 state/kr/team_<트레이너>.json."""
    m = main.mkt(mk)
    if m.key == "us":
        return STATE_DIR / f"team_{tname}.json"
    return STATE_DIR / m.key / f"team_{tname}.json"


def _wallet_from_dict(d):
    w = PaperWallet(name=d["name"], cash=d["cash"], currency=d.get("currency", "USD"),
                    fee_rate=d["fee_rate"], sell_tax_rate=d["sell_tax_rate"], slippage=d["slippage"])
    w.holdings = {k: Holding(**v) for k, v in d["holdings"].items()}
    w.log = d["log"]
    return w


def _load(tname, mk=None):
    """상태 읽기. 없거나 예전 형식(원화 시절)이면 None — 예전 파일은 보관용 이름으로 바뀐다.
    국내는 형식 버전 + 지갑 통화(KRW)까지 맞아야 이어 쓴다 (달러 지갑이 섞여 들어오면 보관 후 새로 시작)."""
    m = main.mkt(mk)
    if m.key == "us":
        st = main.load_state_file(_path(tname))
    else:
        st = main.load_state_file(_path(tname, m), schema=main.schema_for(m), currency=m.currency)
    if st is not None:
        st["wallet"] = _wallet_from_dict(st["wallet"])
    return st


def _save(tname, st, mk=None):
    m = main.mkt(mk)
    if st["wallet"].currency != m.currency:      # 원화·달러 섞임은 저장 단계에서도 막는다
        raise ValueError(f"{tname}: 지갑 통화 {st['wallet'].currency} ≠ 시장 통화 {m.currency} — 저장 안 함")
    data = {k: v for k, v in st.items() if k != "wallet"}
    data["wallet"] = asdict(st["wallet"])
    data["schema"] = main.schema_for(m)
    main.save_json_atomic(_path(tname, m), data)


def _new_state(tname, cash, bar_date, mk=None):
    wallet = main.make_wallet(tname, mk)
    wallet.deposit(cash, bar_date)
    return {"wallet": wallet, "positions": {}, "pending": [], "prev_value": None, "stopped": False,
            "last_date": None, "start_cash": cash, "start_date": bar_date}


def _prices(code, cache, mk=None):
    """종목 시세(확정 봉). 같은 실행 안에서는 한 번만 받는다. 실패하면 None."""
    if code not in cache:
        try:
            cache[code] = main.prices_for(mk, code, START)
        except Exception:
            cache[code] = None
    return cache[code]


def _dates(df):
    return [d.date().isoformat() for d in df.index]


def _at(m, px):
    """로그용 체결가 표기: 미국 '@123.45'(예전 그대로), 국내 '@71,300원'."""
    return f"@{px:.2f}" if m.key == "us" else f"@{markets.price_text(m.key, px)}"


def run_trainer(tname, cash, cap, breaker, screened, bar_date, st=None, cache=None, mk=None):
    """이 트레이너의 새 확정 봉(bar_date) 하루: 주문 체결 → 보유관리 → 서킷 → 신규 주문.
    (사람이 읽을 한 줄, 상태) 를 돌려준다. mk: 시장(없으면 미국)."""
    m = main.mkt(mk)
    cache = {} if cache is None else cache
    brain = BRAINS[tname]()
    if st is None:
        st = _load(tname, m)
    if st is None:
        st = _new_state(tname, cash, bar_date, m)
    if st["last_date"] and st["last_date"] >= bar_date:
        return f"{tname}: 확정 봉 {bar_date} 이미 처리됨 (멱등).", st

    wallet, positions = st["wallet"], st["positions"]
    budget = st["start_cash"]
    logs, prices, changed = [], {}, False
    held_before = set(positions)

    # ① 어제 낸 주문을 '신호 다음 거래일' 시가로 체결 (D3)
    still = []
    for order in st["pending"]:
        code = order["code"]
        df = _prices(code, cache, m)
        nxt = None
        if df is not None:
            ds = _dates(df)
            idx = [i for i, d in enumerate(ds) if order["signal_date"] < d <= bar_date]
            nxt = (df.iloc[idx[0]], ds[idx[0]]) if idx else None
        if nxt is None:
            still.append(order)          # 다음 봉이 아직 없음 → 다음 실행에서 다시
            continue
        bar, d = nxt
        px = main.open_price(bar)
        changed = True
        if order["action"] == "매수" and code not in positions:
            n = shares_within_cap(budget, cap, px, wallet.fee_rate, wallet.slippage)
            if n <= 0:
                why = f"상한 {main.fmt(m, budget * cap, False)} 안에서 1주도 못 삼 (시가 {main.px_txt(m, px)})"
                wallet.skip(code, why, d); logs.append(f"보류 {code}({why})")
            elif wallet.buy(code, px, n, d):
                positions[code] = {"buy_price": px, "days_held": 0, "shares": n, "buy_date": d}
                tip = f" 팀장:{order['note']}" if order.get("note") else ""
                logs.append(f"매수 {code}x{n}{_at(m, px)}{tip}")
            else:
                why = f"현금 부족 (필요 {main.fmt(m, px * n, False)}, 보유 {main.fmt(m, wallet.cash, False)})"
                wallet.skip(code, why, d); logs.append(f"보류 {code}(현금 부족)")
        elif order["action"] == "매도" and code in positions:
            pos = positions[code]
            if wallet.sell(code, px, pos["shares"], d):
                logs.append(f"매도 {code}{_at(m, px)}({order.get('reason', '')[:14]})")
                del positions[code]
    st["pending"] = still

    # ② 보유 종목: 오늘 종가로 평가하고 매도 판단 → 내일 시가 주문
    pending_codes = {o["code"] for o in st["pending"]}
    for code, pos in positions.items():
        df = _prices(code, cache, m)
        if df is None:
            continue
        d = brain.add_indicators(df)
        d = d[[x <= bar_date for x in _dates(d)]]
        if len(d) == 0:
            continue
        prices[code] = float(d["Close"].iloc[-1])
        changed = True
        if code in held_before:
            pos["days_held"] = pos.get("days_held", 0) + 1
        if code in pending_codes:
            continue
        action, reason = brain.decide(d, pos)
        if action == "매도":
            st["pending"].append({"code": code, "action": "매도", "signal_date": bar_date, "reason": reason})
            logs.append(f"매도주문 {code}({reason[:14]})")

    # ③ 서킷 브레이커 (포트폴리오 단위, D6 동작 유지 — 단 정리는 다음 시가)
    if not st["stopped"]:
        hit = breaker.check(st["start_cash"], st["prev_value"], wallet.value(prices))
        if hit:
            st["pending"] = [{"code": c, "action": "매도", "signal_date": bar_date, "reason": "서킷 브레이커"}
                             for c in positions]
            st["stopped"] = True; changed = True
            logs.append("🛑서킷:" + hit[:20] + " → 다음 시가 전량 정리")

    # ④ 신규 후보 → 팀장 분석(veto·hold·확신도) → 내일 시가 매수 주문
    pending_buys = [o for o in st["pending"] if o["action"] == "매수"]
    if not st["stopped"] and len(positions) + len(pending_buys) < MAX_POSITIONS:
        busy = set(positions) | {o["code"] for o in st["pending"]}
        cands = [c for c in screened if c["code"] not in busy]
        if cands:
            analysis = analyst.analyze(tname, cands)          # 팀장 분석; 부재 시 None → 규칙 폴백
            verdicts = {k: (v or {}).get("verdict") for k, v in (analysis or {}).items()}
            cands = analyst.apply(cands, analysis)            # veto 는 여기서 빠진다
            kept = []
            for c in cands:
                c = {**c, "conviction": to_conviction(c.get("conviction"))}
                if verdicts.get(c["code"]) == "hold":
                    wallet.skip(c["code"], "팀장 hold", bar_date); changed = True
                    logs.append(f"보류 {c['code']}(팀장 hold)")
                elif not keep_candidate(c):
                    why = f"팀장 확신도 낮음 ({c['conviction']:.2f} < {CONV_MIN})"
                    wallet.skip(c["code"], why, bar_date); changed = True
                    logs.append(f"보류 {c['code']}(확신도 {c['conviction']:.2f})")
                else:
                    kept.append(c)
            kept.sort(key=lambda c: c.get("conviction") or 0, reverse=True)
            slots = MAX_POSITIONS - len(positions) - len(pending_buys)
            for c in kept[:max(slots, 0)]:
                st["pending"].append({"code": c["code"], "action": "매수",
                                      "signal_date": c.get("date") or bar_date,
                                      "reason": c.get("reason", ""), "note": c.get("note")})
                logs.append(f"매수주문 {c['code']}")
                changed = True

    if not changed:
        # 후보·보유·주문이 모두 없음 → 날짜를 저장하지 않는다(나중에 데이터가 고쳐지면 다시 돌 수 있게)
        return f"{tname}: 후보·보유·주문 없음 → 저장 안 함 (기준 봉 {bar_date})", st

    value_now = wallet.value(prices)
    st["prev_value"] = value_now
    st["last_date"] = bar_date
    _save(tname, st, m)
    body = "; ".join(logs) if logs else "변화 없음"
    n_pending = len(st["pending"])
    return (f"{tname}: [{bar_date}] 평가 {main.fmt(m, value_now, False)} | 보유 {len(positions)}종목"
            f" | 대기주문 {n_pending} | {body}" + (" [정지]" if st["stopped"] else "")), st


def _summary(states, spy, mk=None):
    """D7: 트레이너별 '시작일부터 지금까지' 손익을 같은 돈으로 벤치마크(SPY / KODEX 200) 들고 있기와 비교."""
    m = main.mkt(mk)
    label = markets.BENCH_NAMES[m.key]
    print("-" * 60)
    print(f"시작일부터 비교 (같은 투입액으로 {label} 들고 있기 · {label} 수익률):")
    for tname, st in states.items():
        if not st or not st.get("last_date") or st.get("prev_value") is None:
            print(f"  {tname}: 아직 처리한 봉이 없어 비교 불가")
            continue
        profit = st["prev_value"] - st["start_cash"]
        if spy is None:
            print(f"  {tname} {main.fmt(m, profit)} | {label} 계산 불가")
            continue
        print("  " + main.compare(tname, profit, spy, st["start_cash"], spy, st["start_date"], st["last_date"],
                                  mk=m))


def run(n=40, market="us"):
    m = main.mkt(market)
    cfg = main.market_config(m)
    print("=" * 60)
    print(f" 팀장 일일 루프 (가상, 진짜 돈 {main.cash_word(m)})" + ("" if m.key == "us" else " · 국내 종목(원화 지갑)"))
    print("=" * 60)
    total = cfg["총_가상자금"]; ratios = cfg["배분비율"]; caps = cfg["종목상한"]
    cb = cfg["서킷브레이커"]; breaker = CircuitBreaker(cb["누적한도"], cb["일일한도"])
    if m.key == "us":
        spy = main.load_benchmark(START)     # 기준 날짜(마지막 확정 봉) + D7 비교. 한 번만 받는다
    else:
        spy = main.load_benchmark(START, m)  # 국내: KODEX 200(069500)
    bar_date = spy.index[-1].date().isoformat() if spy is not None and len(spy) else None
    states = {t: _load(t, m) for t in BRAINS}

    # N5: 세 트레이너가 모두 이 확정 봉까지 처리됐으면 스캔하지 않고 끝
    if bar_date and all(st and st.get("last_date") and st["last_date"] >= bar_date for st in states.values()):
        print(f"마지막 확정 봉 {bar_date} — 세 트레이너 모두 이미 처리됨. 스캔 생략 (멱등).")
        _summary(states, spy, m)
        return states

    print(f"① 스크리너 {n}종목 스캔 중... (기준 확정 봉 {bar_date or '?'})", flush=True)
    found, used = screener.scan(n) if m.key == "us" else screener.scan(n, market=m.key)
    print(f"  스캔 {used}종목 완료. 트레이너별 후보: " +
          ", ".join(f"{t} {len(found.get(t, []))}" for t in BRAINS))
    if bar_date is None:   # SPY를 못 받았으면 후보들의 봉 날짜로 대신
        ds = [c.get("date") for cs in found.values() for c in cs if c.get("date")]
        bar_date = max(ds) if ds else None
    if bar_date is None:
        print("기준 날짜(마지막 확정 봉)를 정하지 못했어요 → 아무것도 저장하지 않고 끝.")
        return states
    print("②~④ 트레이너별 체결·분석·판단:")
    cache = {}
    for tname in BRAINS:
        cash = total * ratios[tname]
        line, states[tname] = run_trainer(tname, cash, caps[tname], breaker, found.get(tname, []),
                                          bar_date, st=states[tname], cache=cache, mk=m)
        print("  " + line)
    _summary(states, spy, m)
    print("=" * 60)
    where = "state/team_*.json" if m.key == "us" else f"state/{m.key}/team_*.json"
    print(f"※ 가상매매. 상태 {where} 저장 → 다음 확정 봉에서 이어짐. 오늘 주문은 다음 시가 체결.")
    print("※ analyst는 claude 없으면 규칙 폴백.")
    return states


if __name__ == "__main__":
    _market, _rest = main.parse_market(sys.argv[1:])
    if _rest and _rest[0] == "check":     # python team.py check → 네트워크 없이 필터만 점검
        assert keep_candidate({"code": "A"})                          # 팀장 부재(키 없음) → 통과(안전원칙)
        assert keep_candidate({"code": "A", "conviction": None})      # 팀장 무의견 → 통과(안전원칙)
        assert keep_candidate({"code": "A", "conviction": 0.8})       # 확신 높음 → 통과
        assert keep_candidate({"code": "A", "conviction": 0.5})       # 경계값(=CONV_MIN) → 통과
        assert not keep_candidate({"code": "A", "conviction": 0.3})   # 확신 낮음 → 보류
        assert keep_candidate({"code": "A", "conviction": "높음"})     # 숫자 아님 → 무의견 취급 → 통과
        assert not keep_candidate({"code": "A", "conviction": "0.3"}) # 문자열 숫자도 변환
        print("[PASS] team 매수 후보 확신도 필터 점검 통과")
    else:
        run(int(_rest[0]) if _rest else 40, _market)
