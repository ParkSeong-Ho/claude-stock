"""
===========================================================
 AI 트레이너 가상매매 (학습 모드) - 내 컴퓨터에서 실행하는 메인 파일
===========================================================
진짜 돈은 절대 쓰지 않습니다. 실제 시세를 가져와 '가짜 지갑'으로 연습만 합니다.

▶ 실행 방법 (터미널에서):
    python main.py                # 미국 종목 (달러 지갑, 기본값)
    python main.py --market kr    # 국내 종목 (원화 지갑, KOSPI 대형주)

▶ 처음 한 번만 준비:
    pip install finance-datareader ta backtesting

이 파일이 하는 일:
  1) 실제 주가를 인터넷에서 가져온다 (미국: 애플, 엔비디아 … 달러 지갑 / 국내: 삼성전자 … 원화 지갑)
     ※ 시장마다 지갑이 따로라 원화와 달러는 절대 섞이지 않는다 (docs/kr-broker-design.md)
     ※ 아직 안 끝난(장중) 봉·종가가 빈 봉은 버리고 '확정 봉'만 쓴다 (국내는 거래정지일 봉도 버림)
  2) 세 트레이너(마라토너/스프린터/파이오니어)가 각자 규칙으로 가상매매
     ※ 오늘 종가로 판단 → 다음 거래일 시가로 체결 (현실처럼, 미래 데이터 안 봄)
  3) 결과를 정직하게 보여주고, 오류가 나면 안전하게 멈추고 기록한다

오류가 나면: 프로그램이 멈추고 error_log.txt 에 자세히 적힙니다.
그 파일을 Claude Code로 열어 "이 오류 고쳐줘"라고 하면 됩니다.
"""

import os
import sys
import argparse
import csv
import json
import math
import traceback
from pathlib import Path
from datetime import datetime, time
from zoneinfo import ZoneInfo

# --- 우리가 만든 부품들 ---
import metrics
import markets
from paper_wallet import PaperWallet, shares_within_cap
from sprinter_brain import SprinterBrain
from marathoner_brain import MarathonerBrain
from pioneer_brain import PioneerBrain
from risk_guard import CircuitBreaker


# ================= 설정 (여기 숫자만 바꾸면 됩니다) =================
CONFIG = {
    # v1은 미국 종목 전용 (D4). 지갑도 달러.
    "종목목록": {
        "애플": "AAPL",
        "마이크로소프트": "MSFT",
        "엔비디아": "NVDA",
        "알파벳": "GOOGL",
        "아마존": "AMZN",
    },
    "벤치마크": "SPY",          # "시장 전체를 샀으면?" 비교용 (S&P500 ETF, D7)
    "시작일": "2023-01-01",     # 이 날부터의 데이터로 연습
    "총_가상자금": 10_000,      # 가짜 돈 $10,000 (달러)
    "배분비율": {"마라토너": 0.60, "스프린터": 0.30, "파이오니어": 0.10},
    # 한 종목에 트레이너 예산의 몇 %까지 넣을지 (기획서 2-1). 위험할수록 작게.
    "종목상한": {"마라토너": 0.30, "스프린터": 0.20, "파이오니어": 0.15},
    # 서킷 브레이커: 누적/하루 손실이 이 한도를 넘으면 자동 전량정리+정지 (기획서 3.3)
    "서킷브레이커": {"누적한도": 0.10, "일일한도": 0.07},
}

# 국내(--market kr) 설정: 위 CONFIG 에서 종목목록·벤치마크·총자금만 바꿔 쓴다 (K-D7·K-D10).
# 배분비율·종목상한·서킷브레이커·시작일은 미국과 같은 값.
KR_STOCKS = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380",
    "NAVER": "035420",
    "KB금융": "105560",
}
# ================================================================

RESULTS_DIR = Path(__file__).parent / "results"  # 성적표·거래로그 CSV가 저장되는 곳

ET = ZoneInfo("America/New_York")   # 미국 동부시간 (뉴욕 증시 기준 시계)
MARKET_SETTLED = time(16, 15)       # 16:00 장 마감 + 여유 15분. 이 전의 '오늘 봉'은 아직 확정 아님
STATE_SCHEMA = "v1-usd-1"           # 상태 파일(state/*.json) 형식 버전. 다르면 예전 파일로 보고 새로 시작
STATE_SCHEMA_KR = "kr-krw-1"        # 국내(원화) 상태 파일(state/kr/*.json) 형식 버전 — 달러 파일과 절대 안 섞임


def mkt(m=None):
    """시장 값 정리: None → 미국, "kr" → Market, Market → 그대로."""
    if m is None:
        return markets.MARKETS["us"]
    if isinstance(m, markets.Market):
        return m
    return markets.get_market(m)


def market_config(m=None):
    """시장별 설정 dict. 미국은 CONFIG 그 자체(지금과 똑같이), 국내는 CONFIG 를 복사해 세 값만 바꾼다."""
    m = mkt(m)
    if m.key == "us":
        return CONFIG
    return {**CONFIG, "종목목록": dict(KR_STOCKS), "벤치마크": m.benchmark, "총_가상자금": m.total_cash}


def schema_for(m=None):
    return STATE_SCHEMA if mkt(m).key == "us" else STATE_SCHEMA_KR


def usd(v, sign=True):
    """금액을 $ 로 표기. 예: +$1,234 / -$56 / $10,000"""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "계산 불가"
    if not sign:
        return f"${v:,.0f}"
    return f"{'+' if v >= 0 else '-'}${abs(v):,.0f}"


def fmt(m, v, sign=True):
    """시장 통화로 금액 표기. 미국은 예전 usd() 그대로(+$1,234), 국내는 +1,234,567원."""
    m = mkt(m)
    return usd(v, sign) if m.key == "us" else markets.money(m.key, v, sign)


def px_txt(m, px):
    """주가 한 개 표기. 미국 $123.45 / 국내 71,300원."""
    m = mkt(m)
    return f"${px:,.2f}" if m.key == "us" else markets.price_text(m.key, px)


def cash_word(m=None):
    """'진짜 돈 $0' / '진짜 돈 0원'."""
    return "$0" if mkt(m).key == "us" else "0원"


# ---------------- 데이터: 확정 봉만 (D1) ----------------

def confirmed_bars(df, now=None, market="us", cutoff=None):
    """'다 끝난(확정된) 봉'만 남긴다. 순수 함수 — 인터넷을 쓰지 않아서 테스트하기 쉽다.

    초보자용 설명:
    - 종가(Close)가 비어 있는(NaN) 행은 버린다. (yahoo가 장 마감 직후 거래량만 채운 행을 줌)
    - 국내(kr)만: 거래량(Volume)이 0 인 행도 버린다 = 거래정지일 (S0-2, 2026-11-04).
        네이버는 거래정지일에도 행을 준다. 모양은 'Open=High=Low=0, Close=직전 종가, Volume=0'
        또는 (삼성바이오로직스 2018-11-15~12-10) 'OHLC 전부 직전 종가, Volume=0'.
        이 행이 남으면 ① 거래가 없던 날 주문이 '체결'되고 ② 이동평균·RSI·20일 평균 거래량에
        거래 없는 날이 섞인다. 그래서 그 종목 시세에서는 그날이 '없던 날'이 된다.
        main·live 는 그 종목의 그날을 아예 처리하지 않는다(신호·체결·보유일수 없음).
        team 은 기준 날짜(KS200)마다 돌기 때문에, 그 종목의 마지막 봉이 기준 봉보다 앞이면
        평가만 하고 판단·보유일수를 건너뛴다(team.run_trainer ②). 체결은 다음 거래된 봉 시가.
        거래량이 비어 있는(NaN) 행은 '모름'이라 그대로 둔다. 미국은 예전과 똑같다(이 규칙 없음).
    - 마지막 봉의 날짜가 그 시장 시간으로 '오늘'인데 아직 확정 시각 전이면,
      그 봉은 아직 장중(미완성)이라 버린다.
        미국: 뉴욕 시간 16:15 전 (D1)   국내: 한국 시간 16:00 전 (K-D9)
        국내 벤치마크 KS200 만: 한국 시간 22:30 전 (cutoff="22:30", markets.py bench_cutoff 설명)
    now: 기준 시각. 없으면 지금. 시간대가 없는 값은 이 컴퓨터의 현지 시각으로 본다.
    market: "us"(기본) | "kr"
    cutoff: "HH:MM"(그 시장 현지시간)으로 확정 시각을 바꿔 쓸 때만. 없으면 시장 기본값.
    """
    if df is None or len(df) == 0:
        return df
    out = df[df["Close"].notna()]
    if len(out) == 0:
        return out
    m = mkt(market)
    if m.key == "kr" and "Volume" in out.columns:
        out = out[out["Volume"] != 0]          # 거래정지일(거래량 0) 행 버림. NaN != 0 이라 NaN 행은 남는다
        if len(out) == 0:
            return out
    if m.key == "us":
        tz, settled = ET, MARKET_SETTLED
    else:
        hh, mm = m.close_cutoff.split(":")
        tz, settled = ZoneInfo(m.tz), time(int(hh), int(mm))
    if cutoff:
        hh, mm = cutoff.split(":")
        settled = time(int(hh), int(mm))
    if now is None:
        now_local = datetime.now(tz)
    else:
        now_local = now.astimezone(tz)   # 시간대 없는 now 는 파이썬이 현지 시각으로 해석
    last_day = out.index[-1].date()
    if last_day == now_local.date() and now_local.time() < settled:
        out = out.iloc[:-1]
    return out


def load_prices(code: str, start: str, now=None, market="us", allow_index=False):
    """실제 주가 데이터를 가져와 확정 봉만 돌려준다(D1·K-D9). 실패하면 친절한 메시지와 함께 알린다.
    market="kr" 이면 6자리 국내 코드만 받는다(달러 종목이 원화 지갑에 섞이지 않게).
    allow_index: 벤치마크 전용 문(load_benchmark 만 True 로 부른다). True 여도 풀어 주는 건
      '그 시장의 벤치마크 기호 딱 하나'(국내 "KS200" = KOSPI 200 가격지수)뿐이다.
      그 밖의 값(예: 미국 티커 "AAPL")은 여전히 국내 종목코드가 아니라서 거부한다.
    벤치마크 기호(code == 그 시장 benchmark)면 확정 시각은 그 시장 bench_cutoff 를 쓴다
    (국내 KS200 = 22:30 KST. 미국 SPY 는 bench_cutoff 가 없어 예전 그대로 16:15 ET)."""
    m = mkt(market)
    if m.key == "kr" and not markets.code_ok("kr", code):
        if not (allow_index and code == m.benchmark):
            raise ValueError(f"'{code}' 는 국내 6자리 종목코드가 아니에요 (국내 시장에는 국내 종목만).")
    try:
        import FinanceDataReader as fdr
    except ImportError:
        raise SystemExit(
            "\n[준비 필요] 라이브러리가 없어요. 터미널에 이걸 입력하세요:\n"
            "    pip install finance-datareader ta backtesting\n"
        )
    df = fdr.DataReader(code, start)
    if df is None or len(df) == 0:
        raise ValueError(f"'{code}' 데이터를 가져오지 못했어요. 종목코드나 인터넷 연결을 확인하세요.")
    # 거래량 칼럼 이름 정리 (파이오니어가 사용)
    if "Volume" not in df.columns and "거래량" in df.columns:
        df = df.rename(columns={"거래량": "Volume"})
    cutoff = m.bench_cutoff if code == m.benchmark else None
    df = confirmed_bars(df, now, m.key, cutoff)
    if len(df) == 0:
        raise ValueError(f"'{code}' 확정된 봉이 하나도 없어요.")
    return df


def prices_for(m, code, start):
    """시장별 시세 받기. 미국은 예전과 똑같이 load_prices(code, start) 로 부른다
    (테스트가 load_prices 를 가짜로 바꿔 끼워도 그대로 동작), 국내는 market="kr" 을 붙인다."""
    m = mkt(m)
    if m.key == "us":
        return load_prices(code, start)
    return load_prices(code, start, market=m.key)


# ---------------- 상태 파일 (live·team 공용) ----------------

def save_json_atomic(path, obj):
    """JSON을 임시파일에 다 쓴 뒤 한 번에 바꿔치기(os.replace). 저장 중에 꺼져도 파일이 반쯤 깨지지 않는다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def retire_old_file(path):
    """예전 형식 파일을 지우지 않고 이름만 바꿔 보관한다. 예: x.json → x.old-20261104-0130.json"""
    path = Path(path)
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = path.with_name(f"{path.stem}.old-{stamp}{path.suffix}")
    os.replace(path, dst)
    return dst


def load_state_file(path, extra_old=(), schema=None, currency=None):
    """상태 JSON을 읽는다. 스키마 버전이 지금과 다르면(예: 원화·수수료 0.015% 시절 파일)
    호환하지 않고 보관용 이름으로 바꾼 뒤 None(=새로 시작)을 돌려준다. extra_old 의 파일도 같이 보관.
    schema: 기대하는 형식 버전(없으면 미국 STATE_SCHEMA). currency: 주면 지갑 통화도 같아야 이어 쓴다."""
    schema = schema or STATE_SCHEMA
    path = Path(path)
    if not path.exists():
        return None
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = None
    if isinstance(st, dict) and st.get("schema") == schema and (
            currency is None or (st.get("wallet") or {}).get("currency", "USD") == currency):
        return st
    moved = retire_old_file(path)
    for p in extra_old:
        retire_old_file(p)
    print(f"  (예전 형식 상태 파일 → {moved.name if moved else '?'} 로 보관하고 새로 시작해요)")
    return None


# ---------------- 하루치 매매 (백테스트·live 공용, D3·D5) ----------------

def _bar_date(window):
    return window.index[-1].date().isoformat()


def open_price(bar):
    """체결가 = 그날 시가(Open). 시가가 없으면(칸 없음·빈칸·NaN·0 이하) None = '이 봉에서는 체결 불가'.

    초보자용 설명 (S0-2, 2026-11-04 변경):
    - 예전에는 시가가 비면 종가로 대신 체결했다. 그런데 국내 거래정지일 행은
      'Open=0, Close=직전 종가, Volume=0' 이라서, 거래가 하나도 없던 날 직전 종가로
      '체결된' 것처럼 장부에 남았다(실제로는 불가능한 체결).
    - 이제는 종가로 대신하지 않고 None 을 돌려준다. 부르는 쪽(fill_pending, team.run_trainer)은
      주문을 지우지 않고 그대로 남겨 두었다가 '다음 거래된 봉'의 시가에 체결한다.
    """
    o = bar.get("Open") if hasattr(bar, "get") else None
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    return o if math.isfinite(o) and o > 0 else None


def fill_pending(st, code, bar, date, cash, cap, mk=None):
    """어제 낸 주문(st['pending'])을 오늘 시가로 체결한다. 사람이 읽을 문장을 돌려준다(없으면 None).
    st: {"wallet", "position", "pending", ...} — 이 함수가 직접 고친다.
    매수 주식 수는 '상한 안에서 비용까지 내고 살 수 있는 만큼'(D5). 0주면 보류로 기록.
    오늘 봉에 시가가 없으면(open_price 가 None) 체결하지 않고 주문을 그대로 남긴다 → 다음 거래된 봉에서 다시."""
    pending = st.get("pending")
    if not pending:
        return None
    px = open_price(bar)
    if px is None:
        # 주의: 주문을 지우기(st["pending"] = None) '전에' 확인한다. 시가 없는 봉에서는 주문이 살아 있어야 한다.
        return f"{pending.get('action', '주문')} 주문 대기 — {date} 시가 없음(체결 불가), 다음 거래된 봉 시가로 미룸"
    st["pending"] = None
    wallet, position = st["wallet"], st.get("position")
    if pending["action"] == "매수":
        if position is not None:
            return None
        n = shares_within_cap(cash, cap, px, wallet.fee_rate, wallet.slippage)
        if n <= 0:
            why = f"상한 {fmt(mk, cash * cap, False)} 안에서 1주도 못 삼 (시가 {px_txt(mk, px)})"
            wallet.skip(code, why, date)
            st["skips"] = st.get("skips", 0) + 1
            return "매수 보류 — " + why
        if not wallet.buy(code, px, n, date):
            why = f"현금 부족 (필요 {fmt(mk, px * n, False)}, 보유 {fmt(mk, wallet.cash, False)})"
            wallet.skip(code, why, date)
            st["skips"] = st.get("skips", 0) + 1
            return "매수 보류 — " + why
        st["position"] = {"buy_price": px, "days_held": 0, "shares": n, "buy_date": date}
        st["buys"] = st.get("buys", 0) + 1
        return f"매수 체결 {n}주 @ {px_txt(mk, px)} (시가)"
    if pending["action"] == "매도" and position is not None:
        if wallet.sell(code, px, position["shares"], date):
            st["closed"] = st.get("closed", 0) + 1
            if px > position["buy_price"]:
                st["wins"] = st.get("wins", 0) + 1
            st["position"] = None
            return f"매도 체결 {position['shares']}주 @ {px_txt(mk, px)} (시가, {pending.get('reason', '')})"
    return None


def trade_day(st, brain, window, code, cash, cap, breaker=None, indicators=None, mk=None):
    """봉 하나(window 의 마지막 봉)를 처리한다. 순서:
      ① 어제 낸 주문을 오늘 시가로 체결 (D3)
      ② 오늘 종가로 서킷 브레이커 검사 → 걸리면 '내일 시가 전량 매도' 주문 + 정지 (D6 동작 유지)
      ③ 오늘 종가로 판단 → 매수/매도 신호는 '내일 시가' 주문으로 st['pending']에 저장
    st 는 이 함수가 직접 고친다. 사람이 읽을 문장을 돌려준다."""
    date = _bar_date(window)
    bar = window.iloc[-1]
    msgs = []
    if st.get("position") is not None:
        st["position"]["days_held"] += 1          # 어제부터 들고 있던 것만 하루 늘림
    filled = fill_pending(st, code, bar, date, cash, cap, mk)
    if filled:
        msgs.append(filled)

    wallet = st["wallet"]
    price = float(bar["Close"])
    cols = [c for c in (indicators or ["MA5", "MA20", "MA60", "RSI"]) if c in window.columns]
    if bar[cols].isnull().any():
        msgs.append("지표가 아직 부족해서 관망.")
        st["prev_value"] = wallet.value({code: price})
        return " / ".join(msgs)

    today_value = wallet.value({code: price})
    hit = None
    if not st.get("stopped") and breaker is not None:
        hit = breaker.check(cash, st.get("prev_value"), today_value)
    if hit is not None:
        st["stopped"] = True
        st["breaker_reason"] = hit
        if st.get("position") is not None:       # 들고 있으면 내일 시가에 전량 강제 정리
            st["pending"] = {"action": "매도", "signal_date": date, "reason": "서킷 브레이커"}
        else:
            st["pending"] = None
        st["last_reason"] = "🛑 서킷 브레이커: " + hit
        msgs.append(st["last_reason"])
    elif st.get("stopped"):
        msgs.append("이미 정지됨 (서킷 브레이커 발동 후 재개 대기).")
    else:
        action, reason = brain.decide(window, st.get("position"))
        st["last_reason"] = reason
        msgs.append(f"{action} — {reason}")
        if action == "매수" and st.get("position") is None:
            st["pending"] = {"action": "매수", "signal_date": date, "reason": reason}
        elif action == "매도" and st.get("position") is not None:
            st["pending"] = {"action": "매도", "signal_date": date, "reason": reason}
        if st.get("pending"):
            msgs.append(f"→ 다음 거래일 시가에 {st['pending']['action']} 주문")
    st["prev_value"] = wallet.value({code: price})
    return " / ".join(msgs)


def _max_drawdown(curve):
    """평가금액 곡선에서 최대 낙폭(MDD)을 계산. 고점 대비 가장 깊이 빠진 비율(음수)."""
    if not curve:
        return 0.0
    peak = curve[0]
    mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)  # 지금이 고점 대비 몇 % 아래인가
    return mdd


def make_wallet(name, mk=None):
    """시장에 맞는 빈 가짜 지갑. 미국은 예전 기본값 그대로(달러), 국내는 원화 + 국내 비용(K-D8)."""
    m = mkt(mk)
    if m.key == "us":
        return PaperWallet(name=name)
    return PaperWallet(name=name, currency=m.currency, fee_rate=m.fee_rate,
                       sell_tax_rate=m.sell_tax_rate, slippage=m.slippage)


def new_state(name, cash, date=None, mk=None):
    """트레이너 한 명의 빈 상태(가짜 지갑 + 포지션 없음)."""
    wallet = make_wallet(name, mk)
    wallet.deposit(cash, date)
    return {"wallet": wallet, "position": None, "pending": None, "prev_value": None,
            "stopped": False, "breaker_reason": None, "last_reason": "판단할 만큼 데이터가 쌓이지 않았어요.",
            "buys": 0, "closed": 0, "wins": 0, "skips": 0}


def run_one_trainer(name, brain, df, cash, cap, code, breaker=None, mk=None):
    """트레이너 한 명이 이 종목을 가상매매. 정직한 성적표를 돌려준다.
    cap: 이 종목에 넣을 수 있는 예산 비율 (기획서 종목상한).
    체결 규칙(D3): 봉 t 종가로 신호 → 봉 t+1 시가로 체결. 마지막 봉의 신호는 미체결로 남는다.
    breaker: 서킷 브레이커. 매일 decide 전에 검사해 한도 넘으면 다음 시가 전량정리+정지."""
    df = brain.add_indicators(df)
    st = new_state(name, cash, df.index[0].date().isoformat() if len(df) else None, mk)
    equity_curve = []          # 하루하루 평가금액 (MDD·검증용)
    need = 60 if isinstance(brain, MarathonerBrain) else 20

    for day in range(need, len(df)):
        window = df.iloc[: day + 1]
        trade_day(st, brain, window, code, cash, cap, breaker, mk=mk)
        price = float(window["Close"].iloc[-1])
        equity_curve.append((_bar_date(window), st["wallet"].value({code: price})))

    wallet, position = st["wallet"], st["position"]
    last_price = float(df["Close"].iloc[-1]) if len(df) else 0.0
    final = wallet.value({code: last_price})
    still = position is not None
    unreal = (last_price - position["buy_price"]) * position["shares"] if still else 0.0
    closed, wins = st["closed"], st["wins"]
    return {
        "name": name, "profit": final - cash, "buys": st["buys"], "closed": closed, "wins": wins,
        "win_rate": (wins / closed * 100) if closed else None,
        "still_holding": still, "unrealized": unreal,
        "mdd": _max_drawdown([v for _, v in equity_curve]),
        "last_reason": st["last_reason"],
        "stopped": st["stopped"], "breaker_reason": st["breaker_reason"],
        "pending": st["pending"],      # 마지막 봉 신호(아직 체결 안 됨) 또는 None
        "skips": st["skips"],          # 매수 보류 횟수 (사유는 log 에)
        "log": wallet.log,
        "equity_curve": equity_curve,
    }


def save_logs(stock_name, r):
    """이 트레이너의 거래내역과 일별 평가금액을 results/ 폴더에 CSV로 저장."""
    RESULTS_DIR.mkdir(exist_ok=True)
    base = f"{stock_name}_{r['name']}"
    with open(RESULTS_DIR / f"{base}_거래내역.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["시각", "종류", "종목", "수량", "금액", "통화", "사유"])
        for e in r["log"]:
            w.writerow([e["시각"], e["종류"], e["종목"], e["수량"], e["금액"],
                        e.get("통화", ""), e.get("사유", "")])
    with open(RESULTS_DIR / f"{base}_평가금액.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["날짜", "평가금액"])
        for d, v in r["equity_curve"]:
            w.writerow([d, round(v, 2)])


def load_benchmark(start, mk=None):
    """벤치마크(미국 SPY / 국내 KOSPI 200 가격지수 KS200) 시세를 한 번만 받는다.
    실패하면 None (비교 줄에 '계산 불가').
    국내 벤치마크는 2026-11-04 에 KODEX 200(069500) → KS200 으로 바뀌었다(S0-1, markets.py 설명).
    KS200 은 지수 기호라 6자리 종목코드가 아니므로, 이 함수만 allow_index=True 로 받는다."""
    m = mkt(mk)
    if m.key == "us":
        try:
            return load_prices(CONFIG["벤치마크"], start)
        except Exception as e:
            print(f"  (벤치마크 {CONFIG['벤치마크']} 받기 실패: {type(e).__name__} — SPY 비교는 계산 불가로 표시)")
            return None
    label = markets.BENCH_NAMES[m.key]
    try:
        return load_prices(m.benchmark, start, market=m.key, allow_index=True)
    except Exception as e:
        print(f"  (벤치마크 {label} [{m.benchmark}] 받기 실패: {type(e).__name__} — {label} 비교는 계산 불가로 표시)")
        return None


def _ok_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def compare_line_market(mk, name, profit, bh, bench_ret, budget):
    """metrics.compare_line 의 시장별 판(국내용). 금액은 그 시장 통화, 벤치마크 이름도 그 시장 것.
    예: '마라토너 +412,000원 | 그냥 들고 있었으면 +1,950,000원 | KOSPI 200(가격지수) +38% → 패'
    판정 규칙은 metrics.compare_line 과 같다(둘 다 이기면 승, 둘 다 지면 패, 하나만 이기면 반반)."""
    m = mkt(mk)
    label = markets.BENCH_NAMES[m.key]
    me = fmt(m, profit) if _ok_num(profit) else "계산 불가"
    bh_profit = bh.get("profit") if isinstance(bh, dict) else None
    bh_txt = fmt(m, bh_profit) if _ok_num(bh_profit) else "계산 불가"
    b_txt = f"{bench_ret * 100:+.0f}%" if _ok_num(bench_ret) else "계산 불가"
    line = f"{name} {me} | 그냥 들고 있었으면 {bh_txt} | {label} {b_txt}"
    if not _ok_num(profit):
        return line + " → 판정 불가"
    results = []
    if _ok_num(bh_profit):
        results.append(("들고있기", profit > bh_profit))
    if _ok_num(bench_ret) and _ok_num(budget):
        results.append((label, profit > bench_ret * budget))
    if not results:
        return line + " → 판정 불가"
    if all(w for _, w in results):
        verdict = "승"
    elif not any(w for _, w in results):
        verdict = "패"
    else:
        verdict = "반반(" + "·".join(f"{n} {'승' if w else '패'}" for n, w in results) + ")"
    return f"{line} → {verdict}"


def _buy_and_hold(seg, budget, m):
    """시장 비용으로 buy&hold. 국내는 매도세(0.2%)까지 빼서 트레이너와 같은 조건으로 맞춘다."""
    if m.key == "us":
        return metrics.buy_and_hold(seg, budget)
    bh = metrics.buy_and_hold(seg, budget, fee_rate=m.fee_rate, slippage=m.slippage)
    if bh and bh["shares"] > 0 and m.sell_tax_rate:
        closes = seg["Close"].dropna() if hasattr(seg, "columns") else seg.dropna()
        tax = bh["shares"] * float(closes.iloc[-1]) * (1 - m.slippage) * m.sell_tax_rate
        bh = {**bh, "profit": bh["profit"] - tax, "return": (bh["profit"] - tax) / budget}
    return bh


def compare(name, profit, prices, budget, spy, start=None, end=None, mk=None):
    """D7 비교 한 줄: 같은 투입액으로 그냥 들고 있기(buy&hold) + SPY 대비.
    start 를 주면(live·team) '시작 봉 다음 봉 시가'에 산 것으로 본다 — 트레이너도 시작 봉 종가에서
    처음 판단하고 다음 시가에야 체결할 수 있으니 같은 조건. SPY 는 시작 봉 종가 → 마지막 종가."""
    if start is None:
        seg = prices
    else:
        ds = [x.date().isoformat() for x in prices.index]
        seg = prices[[start < x <= end for x in ds]]
        if len(seg) == 0:
            return f"{name} {fmt(mk, profit)} | 비교는 다음 확정 봉부터 (시작 봉 {start})"
    m = mkt(mk)
    bh = _buy_and_hold(seg, budget, m)
    s = start or (bh["start"] if bh else None)
    e = end or (bh["end"] if bh else None)
    spy_ret = metrics.benchmark_return(spy, s, e) if (spy is not None and s and e) else None
    if m.key == "us":
        return metrics.compare_line(name, profit, bh, spy_ret, budget)
    return compare_line_market(m, name, profit, bh, spy_ret, budget)


def main(market="us"):
    m = mkt(market)
    cfg = market_config(m)
    label = markets.BENCH_NAMES[m.key]
    print("=" * 55)
    print(f" AI 트레이너 가상매매 (학습 모드) — 진짜 돈 {cash_word(m)}"
          + ("" if m.key == "us" else " · 국내 종목(원화 지갑)"))
    print("=" * 55)

    total = cfg["총_가상자금"]
    ratios = cfg["배분비율"]
    caps = cfg["종목상한"]
    cb = cfg["서킷브레이커"]
    breaker = CircuitBreaker(cum_limit=cb["누적한도"], day_limit=cb["일일한도"])
    brains = {
        "마라토너": MarathonerBrain(),
        "스프린터": SprinterBrain(),
        "파이오니어": PioneerBrain(),
    }
    spy = load_benchmark(cfg["시작일"], m)     # 벤치마크는 한 번만 받아서 모든 종목 비교에 재사용

    for 종목명, code in cfg["종목목록"].items():
        print(f"\n▼ [{종목명}] 데이터 불러오는 중...")
        df = prices_for(m, code, cfg["시작일"])
        print(f"  {len(df)}일치 확정 봉 ({df.index[0].date()} ~ {df.index[-1].date()})  ※ 체결은 다음 거래일 시가")

        print(f"  {'트레이너':<8}{'순손익':>12}{'매수':>5}{'완료':>5}{'승률':>7}{'MDD':>7}{'보유중':>7}")
        for name, brain in brains.items():
            cash = total * ratios[name]
            r = run_one_trainer(name, brain, df, cash, caps[name], code, breaker, mk=m)
            wr = f"{r['win_rate']:.0f}%" if r["win_rate"] is not None else "-"
            mdd = f"{r['mdd']*100:.0f}%"   # 고점 대비 최대 낙폭 (얼마나 깊이 물렸나)
            hold = "예" if r["still_holding"] else "아니오"
            print(f"  {r['name']:<8}{fmt(m, r['profit']):>12}{r['buys']:>5}{r['closed']:>5}{wr:>7}{mdd:>7}{hold:>7}")
            if r["still_holding"]:
                print(f"      └ 아직 안 판 평가손익 {fmt(m, r['unrealized'])} 포함 (팔아야 확정)")
            if r["pending"]:
                p = r["pending"]
                print(f"      └ 미체결 주문: {p['action']} ({p['signal_date']} 신호 → 다음 거래일 시가, 아직 없음)")
            if r["skips"]:
                last = next((e.get("사유") for e in reversed(r["log"]) if e["종류"] == "보류"), "")
                print(f"      └ 매수 보류 {r['skips']}회 (최근 사유: {last})")
            if r["stopped"]:
                print(f"      └ {r['breaker_reason']}")
            print(f"      └ 마지막 판단: {r['last_reason']}")
            print(f"      └ 비교: {compare(name, r['profit'], df, cash * caps[name], spy, mk=m)}")
            save_logs(종목명 if m.key == "us" else f"kr_{종목명}", r)

    print("\n" + "=" * 55)
    print("※ 이건 가상매매입니다. 진짜 돈은 들어가지 않았습니다.")
    print(f"※ '비교'는 같은 투입액(예산×종목상한)으로 첫날 사서 들고 있기·{label} 와 견준 것. 이겼다는 말은 이 숫자로만.")
    print("※ 결과가 좋아도 미래 수익을 보장하지 않습니다. 여러 종목·기간으로 계속 검증하세요.")
    print(f"※ 거래내역·일별 평가금액이 '{RESULTS_DIR.name}' 폴더에 CSV로 저장됐어요.")
    print("=" * 55)


def parse_market(argv=None):
    """명령줄에서 --market us|kr 만 읽는다(기본 us). 나머지 인자는 그대로 돌려준다."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--market", choices=sorted(markets.MARKETS), default="us")
    ns, rest = ap.parse_known_args(argv)
    return ns.market, rest


if __name__ == "__main__":
    try:
        _market, _ = parse_market(sys.argv[1:])
        main(_market)
    except SystemExit:
        raise
    except Exception:
        # 오류가 나면 안전하게 멈추고, 자세히 기록한다
        err = traceback.format_exc()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n[{stamp}]\n{err}\n")
        print("\n" + "!" * 55)
        print(" 오류가 발생해서 안전하게 멈췄어요. (돈은 절대 안 나갔어요)")
        print(" 자세한 내용이 error_log.txt 에 저장됐어요.")
        print(" 그 파일을 Claude Code로 열어 '이 오류 고쳐줘'라고 하세요.")
        print("!" * 55)
        sys.exit(1)
