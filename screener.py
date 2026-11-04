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

scan() = 시세 받기 + scan_frames() (H1 설계 §3.4, 2026-11-04):
- scan_frames(frames, order, asof, min_bars, brains) 는 '이미 받은 시세'만으로 판단한다(인터넷 없음).
  H1 은 시세를 한 번 받아 두고 봉마다 asof(그 날짜 이하로 자르기)를 바꿔 가며 부른다.
- scan() 은 예전처럼 종목군을 받아 받기에 실패한 종목은 건너뛰고, 받은 시세로 scan_frames 를 부른다.
  판단 구현은 scan_frames 하나뿐이라 둘의 결과가 어긋날 수 없다. 바깥 동작은 예전과 같다(tests/golden 으로 확인).
"""

import sys
import csv
import random
from datetime import date

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


def _check_asof(asof):
    """asof 는 None 이거나 'YYYY-MM-DD' 10자리 날짜 글자여야 한다. 글자로 날짜를 비교하므로
    '2026-10-7' 같은 값을 받으면 조용히 미래 봉을 보게 된다 → 바로 ValueError (2a 검토 A-8)."""
    if asof is None:
        return
    ok = isinstance(asof, str) and len(asof) == 10
    if ok:
        try:
            ok = date.fromisoformat(asof).isoformat() == asof
        except ValueError:
            ok = False
    if not ok:
        raise ValueError(f"asof 는 'YYYY-MM-DD' 10자리 날짜여야 해요 (받은 값: {asof!r})")


def scan_frames(frames, order, asof=None, min_bars=70, brains=None):
    """이미 받은 시세로 트레이너별 '매수' 후보를 찾는다. 인터넷을 쓰지 않는다.

    frames: {종목코드: 확정 봉 시세 DataFrame}. order 에 있는데 frames 에 없거나 값이 None 인 종목은
            받기 실패로 보고 건너뛴다(세지도 않음. team._prices 캐시처럼 실패를 None 으로 담아 넘겨도 된다).
    order: 훑는 순서(= 후보 목록의 순서).
    asof: 'YYYY-MM-DD'(10자리). 주면 각 시세를 그 날짜 이하로 자른 뒤 판단한다(미래 봉을 보지 않게).
          None 이면 자르지 않음. 다른 모양이면 ValueError.
    min_bars: 이보다 봉이 적은 종목은 지표 워밍업 부족으로 빼고, 세지도 않는다(기본 70).
    brains: {트레이너: 브레인 클래스}. None 이면 이 모듈의 BRAINS (부를 때의 값).
    돌려주는 값: (found, used) — found = {트레이너: [후보 dict, ...]}, used = 판단한 종목 수.
    후보 dict 는 code·price(종가 소수 2자리)·date(신호 봉)·rsi(소수 1자리, 없으면 None)·reason.
    마지막 봉이 이번 스캔의 가장 최근 봉보다 앞인 종목(거래정지 등)의 후보는 뺀다(M1)."""
    _check_asof(asof)
    brains = BRAINS if brains is None else brains
    found = {t: [] for t in brains}
    used = 0
    latest = None                 # 이번 스캔에서 본 가장 최근 봉 날짜 (오래된 봉 후보를 빼는 기준)
    for code in order:
        df = frames.get(code)
        if df is None:
            continue              # 받기 실패한 종목
        if asof is not None:
            df = df[[x.date().isoformat() <= asof for x in df.index]]
        if len(df) < min_bars:    # 지표 워밍업 부족 종목 제외
            continue
        used += 1
        last = df.index[-1].date().isoformat()
        latest = last if latest is None or last > latest else latest
        for tname, cls in brains.items():
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


def scan(n=50, market="us"):
    """n종목을 스캔해 트레이너별 '매수' 후보 리스트를 돌려준다. market: "us"(기본) | "kr".
    시세를 받고(실패한 종목은 건너뜀) scan_frames 로 판단한다."""
    m = main.mkt(market)
    codes = universe(n) if m.key == "us" else universe(n, m.key)
    frames = {}
    for code in codes:
        try:
            frames[code] = main.prices_for(m, code, START)
        except Exception:
            continue
    return scan_frames(frames, codes)


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
