"""
screener.py - 부하(트레이너)가 넓은 종목군에서 자기 스타일 '매수' 후보를 스스로 찾는다.
------------------------------------------------------------------
각 brain의 decide()를 종목 전체의 최신봉에 돌려, 지금 '매수' 신호를 내는 종목을
트레이너별로 추출한다. = 운영모델의 1단계(부하가 후보 선별). 기존 brains 그대로 재사용.

출력: results/screener_<트레이너>.csv + 콘솔 요약 (이후 analyst.py가 이 후보를 분석).
실행: python screener.py [N] [--market us|kr]   (N = 스캔할 종목 수, 기본 50 / 시장 기본 us)

미국(us): S&P500에서 고정 seed로 섞어 N종목.
국내(kr): markets.KR_UNIVERSE (KOSPI 시가총액 상위 약 30개, 코드에 고정) 앞에서부터 N종목.
          KRX 전체 목록 조회(fdr.StockListing("KRX"))는 자주 멈춰서 쓰지 않는다(K-D7). main.load_prices 가 '확정 봉'만 주므로(D1)
후보의 가격·날짜는 마지막 확정 봉 기준이다. 실제 체결은 team.py 가 다음 거래일 시가로 한다(D3).

오래된 봉 후보 빼기 (M1, 2026-11-04): 마지막 봉이 '이번 스캔에서 가장 최근 봉 날짜'보다 앞인 종목
(= 그날 거래가 없음: 국내 거래정지일은 시세에서 빠지므로 정지 중 종목이 여기 걸림, 미국은 상장폐지·자료 지연)
은 후보로 내지 않는다. 정지 전 마지막 봉의 신호로 매일 새 주문을 내지 않으려고. team.py 도 기준 봉보다
오래된 후보는 한 번 더 뺀다.
"""

import sys
import csv
import random

import main
import markets
from sprinter_brain import SprinterBrain
from marathoner_brain import MarathonerBrain
from pioneer_brain import PioneerBrain

BRAINS = {"마라토너": MarathonerBrain, "스프린터": SprinterBrain, "파이오니어": PioneerBrain}
START = "2024-06-01"   # 지표 워밍업 충분(마라토너 MA60+) ~ 최신까지
SEED = 7


def universe(n, market="us"):
    """미국: S&P500에서 고정 seed로 섞어 n종목. (객관적 모집단, 승자 cherry-pick 방지)
    국내: KR_UNIVERSE(시가총액순 고정 목록) 앞에서 n종목 — 인터넷 조회 없음."""
    if main.mkt(market).key == "kr":
        return list(markets.KR_UNIVERSE.values())[:n]
    import FinanceDataReader as fdr
    syms = [s for s in fdr.StockListing("S&P500")["Symbol"].tolist() if isinstance(s, str)]
    random.seed(SEED)
    random.shuffle(syms)
    return syms[:n]


def scan(n=50, market="us"):
    """n종목을 스캔해 트레이너별 '매수' 후보 리스트를 돌려준다. market: "us"(기본) | "kr"."""
    m = main.mkt(market)
    found = {t: [] for t in BRAINS}
    used = 0
    latest = None                 # 이번 스캔에서 본 가장 최근 봉 날짜 (오래된 봉 후보를 빼는 기준)
    for code in (universe(n) if m.key == "us" else universe(n, m.key)):
        try:
            df = main.prices_for(m, code, START)
        except Exception:
            continue
        if len(df) < 70:          # 지표 워밍업 부족 종목 제외
            continue
        used += 1
        last = df.index[-1].date().isoformat()
        latest = last if latest is None or last > latest else latest
        for tname, cls in BRAINS.items():
            d = cls().add_indicators(df)
            action, reason = cls().decide(d, None)   # 보유 없음 기준 → 매수 신호만 본다
            if action == "매수":
                row = d.iloc[-1]
                found[tname].append({
                    "code": code,
                    "price": round(float(row["Close"]), 2),     # 신호 봉의 종가 (참고용, 체결가 아님)
                    "date": d.index[-1].date().isoformat(),      # 신호 봉 날짜 → 다음 봉 시가로 체결
                    "rsi": round(float(row["RSI"]), 1) if "RSI" in d.columns else None,
                    "reason": reason,
                })
    if latest:                    # 마지막 봉이 가장 최근 봉보다 앞인 종목(거래정지 등)의 후보는 뺀다
        found = {t: [c for c in cs if c["date"] >= latest] for t, cs in found.items()}
    return found, used


def save(found, market="us"):
    main.RESULTS_DIR.mkdir(exist_ok=True)
    prefix = "screener_" if main.mkt(market).key == "us" else "screener_kr_"
    for tname, cands in found.items():
        f = main.RESULTS_DIR / f"{prefix}{tname}.csv"
        with open(f, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp)
            w.writerow(["code", "date", "price", "rsi", "reason"])
            for c in cands:
                w.writerow([c["code"], c.get("date"), c["price"], c["rsi"], c["reason"]])


if __name__ == "__main__":
    _market, _rest = main.parse_market(sys.argv[1:])
    n = int(_rest[0]) if _rest else 50
    print(f"{'S&P500' if _market == 'us' else 'KOSPI 대형주(KR_UNIVERSE)'}에서 {n}종목 스캔 중...", flush=True)
    found, used = scan(n, _market)
    save(found, _market)
    print(f"사용 {used}종목. 트레이너별 '매수' 후보:")
    for t, cands in found.items():
        print(f"  {t:<8} {len(cands)}개 → {[c['code'] for c in cands][:10]}")
    print("results/screener_*.csv 저장 완료. (다음: analyst.py가 이 후보를 분석)")
