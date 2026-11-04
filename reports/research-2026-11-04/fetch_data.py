"""
연구용 시세 받기 (research-2026-11-04)
---------------------------------------
미국 대형주 20개 + SPY 를 FinanceDataReader 로 2015-01-01부터 받아 data/ 에 저장한다.
- 설계 D1: Close 가 NaN 인 행(아직 확정 안 된 봉)은 버린다.
  마지막 봉 날짜가 미국 동부시간 '오늘'이고 지금이 16:15 ET 이전이면 그 봉도 버린다.
- 한 번 받아 저장해 두면 다른 스크립트는 인터넷 없이 같은 숫자로 다시 돌릴 수 있다(재현성).

실행(저장소 루트에서):  ~/.venv-cs/bin/python reports/research-2026-11-04/fetch_data.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
START = "2015-01-01"

# 종목 목록 — 고른 방법은 REPORT.md '1. 종목' 참고.
# 1~13위: Wikipedia 'List of public corporations by market capitalization' 의
#         '1조 달러 기업' 표 중 S&P500 미국 기업 (2026-11-04 접속).
# 14~20위: 위 표에 없는 다음 순위 — 2026년 중반 기준 근사(외부 순위 사이트 접속 불가).
UNIVERSE = {
    "NVDA": "엔비디아", "AAPL": "애플", "GOOGL": "알파벳", "MSFT": "마이크로소프트",
    "AMZN": "아마존", "META": "메타", "AVGO": "브로드컴", "TSLA": "테슬라",
    "BRK-B": "버크셔해서웨이", "LLY": "일라이릴리", "WMT": "월마트", "MU": "마이크론",
    "AMD": "AMD", "JPM": "JP모건", "ORCL": "오라클", "V": "비자", "MA": "마스터카드",
    "NFLX": "넷플릭스", "XOM": "엑슨모빌", "COST": "코스트코",
}
BENCH = "SPY"


def confirmed_bars(df, now=None):
    """D1: Close NaN 행 제거 + 장 마감(16:15 ET) 전이면 오늘 봉 제거."""
    df = df[df["Close"].notna()].copy()
    now = now or datetime.now(ZoneInfo("America/New_York"))
    if len(df) and df.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 15):
        df = df.iloc[:-1]
    return df


def main():
    DATA.mkdir(exist_ok=True)
    info = {"받은_시각_UTC": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M"), "시작일": START, "종목": {}}
    for code in list(UNIVERSE) + [BENCH]:
        raw = fdr.DataReader(code, START)
        n_raw = len(raw)
        df = confirmed_bars(raw)
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        bad_open = int(df["Open"].isna().sum() + (df["Open"] <= 0).sum())
        df.to_csv(DATA / f"{code}.csv.gz", float_format="%.6f")
        info["종목"][code] = {"이름": UNIVERSE.get(code, "S&P500 ETF"), "행수": len(df),
                             "버린_행": n_raw - len(df), "Open_이상": bad_open,
                             "처음": str(df.index[0].date()), "마지막": str(df.index[-1].date())}
        print(f"{code:6s} {len(df):5d}행 (버림 {n_raw - len(df)})  {df.index[0].date()} ~ {df.index[-1].date()}")
    (DATA / "universe.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
