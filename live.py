"""
===========================================================
 라이브 가상매매 (매일 한 번 실행) - 진짜 돈 0원
===========================================================
main.py 는 과거 전체를 한 번에 훑는 백테스트.
live.py 는 '새 확정 봉'만 판단하고 그 결과를 저장해, 내일 이어서 돌린다.
→ 과거에 끼워맞추지 않은 '미래(포워드)' 검증. 기획서 3.4의 학습 모드.

▶ 실행 (하루 한 번, 미국 장 마감 뒤 추천 — 뉴욕 16:15 이후 = 한국 다음날 아침 6~7시쯤):
    python live.py
  국내 종목(원화 지갑)은 한국 시간 16:00 이후:
    python live.py --market kr     # 상태는 state/kr/ 에 따로 (달러 상태와 섞이지 않음)

  매일 자동으로 돌리고 싶으면 cron 한 줄 (예: 한국 시간 화~토 오전 7시):
    0 7 * * 2-6  cd /경로/files && python live.py >> live.log 2>&1
  너무 일찍 돌려도 괜찮아요: 아직 확정 안 된 봉은 버리고, 새 확정 봉이 없으면 아무것도 안 바꿔요.

상태는 state/ 폴더의 JSON에 저장됩니다. 지우면 처음부터 다시 시작해요.

v1 규칙 (docs/v1-design.md):
- '처리했나'는 달력 날짜가 아니라 **마지막 확정 봉의 날짜**로 판단(D2). 새 확정 봉이 없으면
  (주말·휴장·장중) 아무것도 저장하지 않고 끝난다. 그래서 몇 번을 돌려도 하루치가 중복되지 않는다(멱등).
- 오늘 종가로 낸 매수/매도 신호는 state 의 pending 에 저장 → 다음 실행 때 새 봉의 시가로 체결(D3).
- 예전(원화·수수료 0.015%) 상태 파일은 이어 쓰지 않고 *.old-날짜.json 으로 보관 후 새로 시작.
"""

import sys
import csv
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

import main  # CONFIG, load_prices, trade_day 재사용
import markets
from paper_wallet import PaperWallet, Holding
from sprinter_brain import SprinterBrain
from marathoner_brain import MarathonerBrain
from pioneer_brain import PioneerBrain
from risk_guard import CircuitBreaker

STATE_DIR = Path(__file__).parent / "state"   # 트레이너별 지갑·포지션 상태(JSON)


def _wallet_to_dict(w: PaperWallet) -> dict:
    return asdict(w)   # holdings 안의 Holding 도 dict 로 풀림


def _wallet_from_dict(d: dict) -> PaperWallet:
    w = PaperWallet(name=d["name"], cash=d["cash"], currency=d.get("currency", "USD"),
                    fee_rate=d["fee_rate"], sell_tax_rate=d["sell_tax_rate"], slippage=d["slippage"])
    w.holdings = {k: Holding(**v) for k, v in d["holdings"].items()}
    w.log = d["log"]
    return w


def _dir(mk=None):
    """상태 폴더. 미국 state/ (지금 그대로), 국내 state/kr/."""
    m = main.mkt(mk)
    return STATE_DIR if m.key == "us" else STATE_DIR / m.key


def _state_file(stock_name, name, mk=None):
    return _dir(mk) / f"{stock_name}_{name}.json"


def _equity_file(stock_name, name, mk=None):
    return _dir(mk) / f"{stock_name}_{name}_평가금액.csv"


def _load_state(stock_name, name, mk=None):
    """저장된 상태를 읽는다. 없거나 예전 형식이면 None (예전 파일은 보관용 이름으로 바뀜).
    국내는 형식 버전 + 지갑 통화(KRW)까지 맞아야 이어 쓴다."""
    m = main.mkt(mk)
    if m.key == "us":
        st = main.load_state_file(_state_file(stock_name, name), extra_old=[_equity_file(stock_name, name)])
    else:
        st = main.load_state_file(_state_file(stock_name, name, m), extra_old=[_equity_file(stock_name, name, m)],
                                  schema=main.schema_for(m), currency=m.currency)
    if st is None:
        return None
    st["wallet"] = _wallet_from_dict(st["wallet"])
    return st


def _save_state(stock_name, name, st, mk=None):
    m = main.mkt(mk)
    if st["wallet"].currency != m.currency:      # 원화·달러 섞임은 저장 단계에서도 막는다
        raise ValueError(f"{stock_name}/{name}: 지갑 통화 {st['wallet'].currency} ≠ 시장 통화 {m.currency}")
    data = {k: v for k, v in st.items() if k != "wallet"}
    data["wallet"] = _wallet_to_dict(st["wallet"])
    data["schema"] = main.schema_for(m)
    main.save_json_atomic(_state_file(stock_name, name, m), data)


def _append_equity(stock_name, name, date_str, value, mk=None):
    _dir(mk).mkdir(parents=True, exist_ok=True)
    f = _equity_file(stock_name, name, mk)
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp)
        if new:
            w.writerow(["날짜", "평가금액"])
        w.writerow([date_str, round(value, 2)])


def step_one(name, brain, cap, code, stock_name, cash, breaker, prices=None, mk=None):
    """이 트레이너·이 종목의 '새 확정 봉'들을 처리하고 상태를 저장. 사람이 읽을 한 줄을 돌려준다.
    prices: 미리 받아 둔 시세(같은 종목을 트레이너마다 다시 받지 않으려고). 없으면 여기서 받는다.
    mk: 시장(없으면 미국).
    st: 돌려주는 두 번째 값 — 요약(D7)에 쓰는 지금 상태."""
    m = main.mkt(mk)
    raw = prices if prices is not None else main.prices_for(m, code, main.CONFIG["시작일"])
    df = brain.add_indicators(raw)
    latest = df.index[-1].date().isoformat()

    st = _load_state(stock_name, name, m)
    if st is None:
        st = main.new_state(name, cash, latest, m)
        st["last_date"] = None
        st["start_date"] = latest
    last_date = st.get("last_date")

    # D2: 마지막으로 처리한 확정 봉 이후의 봉만. 처음이면 가장 최근 봉 하나만.
    dates = [d.date().isoformat() for d in df.index]
    if last_date is None:
        todo = [len(df) - 1]
    else:
        todo = [i for i, d in enumerate(dates) if d > last_date]
    if not todo:
        return (f"{stock_name}/{name}: 새 확정 봉 없음 (마지막 처리 {last_date}). 저장 안 하고 끝.", st)

    msgs = []
    for i in todo:
        window = df.iloc[: i + 1]
        msg = main.trade_day(st, brain, window, code, cash, cap, breaker, mk=m)
        value = st["wallet"].value({code: float(window["Close"].iloc[-1])})
        _append_equity(stock_name, name, dates[i], value, m)
        msgs.append(msg)
    st["last_date"] = dates[todo[-1]]
    _save_state(stock_name, name, st, m)
    value_now = st["wallet"].value({code: float(df["Close"].iloc[-1])})
    extra = f" (밀린 봉 {len(todo)}개 처리)" if len(todo) > 1 else ""
    return (f"[{st['last_date']}] {stock_name}/{name}: {msgs[-1]} | 평가금액 {main.fmt(m, value_now, False)}{extra}", st)


def run(market="us"):
    m = main.mkt(market)
    cfg = main.market_config(m)
    label = markets.BENCH_NAMES[m.key]
    print("=" * 55)
    print(f" 라이브 가상매매 (새 확정 봉) — 진짜 돈 {main.cash_word(m)}"
          + ("" if m.key == "us" else " · 국내 종목(원화 지갑)"))
    print("=" * 55)
    total = cfg["총_가상자금"]
    ratios = cfg["배분비율"]
    caps = cfg["종목상한"]
    cb = cfg["서킷브레이커"]
    breaker = CircuitBreaker(cum_limit=cb["누적한도"], day_limit=cb["일일한도"])
    brains = {"마라토너": MarathonerBrain(), "스프린터": SprinterBrain(), "파이오니어": PioneerBrain()}
    if m.key == "us":
        spy = main.load_benchmark(cfg["시작일"])   # SPY 는 한 번만
    else:
        spy = main.load_benchmark(cfg["시작일"], m)   # KODEX 200 도 한 번만

    summary = []
    for 종목명, code in cfg["종목목록"].items():
        prices = main.prices_for(m, code, cfg["시작일"])   # 종목당 한 번만 받기
        for name, brain in brains.items():
            cash = total * ratios[name]
            line, st = step_one(name, brain, caps[name], code, 종목명, cash, breaker, prices, mk=m)
            print(line)
            if st.get("start_date") and st.get("last_date"):
                value = st["wallet"].value({code: float(prices["Close"].iloc[-1])})
                summary.append(f"{종목명}/" + main.compare(
                    name, value - cash, prices, cash * caps[name], spy, st["start_date"], st["last_date"], mk=m))

    if summary:
        print("-" * 55)
        print(f"시작일부터 지금까지 비교 (같은 투입액으로 들고 있기 · {label}):")
        for s in summary:
            print("  " + s)
    print("=" * 55)
    print(f"※ 가상매매입니다. 상태는 {'state/' if m.key == 'us' else 'state/' + m.key + '/'} 폴더에 저장돼 다음 확정 봉에서 이어집니다.")
    print("※ 오늘 신호는 다음 거래일 시가에 체결돼요(다음 실행 때).")
    print("=" * 55)


if __name__ == "__main__":
    try:
        _market, _ = main.parse_market(sys.argv[1:])
        run(_market)
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n[{stamp}] (live.py)\n{err}\n")
        print("\n오류로 안전하게 멈췄어요. error_log.txt 를 Claude Code로 열어 '고쳐줘'라고 하세요.")
        sys.exit(1)
