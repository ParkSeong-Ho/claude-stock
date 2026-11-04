"""
R2 stage0b: 국내 시세 받기
- markets.KR_UNIVERSE 전 종목 + 069500(KODEX 200)
- FinanceDataReader DataReader(code, start, end) — 6자리 코드는 FDR 내부에서 NaverDailyReader 로 감
  (main.load_prices 와 같은 fdr.DataReader 호출, end 만 고정)
- D1/K-D9: Close NaN 행 제거, 마지막 봉이 KST 오늘이고 16:00 전이면 제거
- 저장 형식: 이전 연구(fetch_data.py)와 같음 — 인덱스 이름 없음, Open,High,Low,Close,Volume, float_format %.6f
실행: /root/.venv-cs/bin/python -I fetch_kr.py <repo_root> <out_dir>
"""
import json
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import FinanceDataReader as fdr
import pandas as pd

START = "2014-06-01"
END = "2026-11-03"
KST = ZoneInfo("Asia/Seoul")


def load_universe(repo_root):
    # markets.py 는 표준 라이브러리만 쓴다 → 경로만 추가해서 import (저장소 파일은 건드리지 않음)
    sys.path.insert(0, str(repo_root))
    import markets
    sys.path.pop(0)
    return dict(markets.KR_UNIVERSE)


def confirmed_bars_kr(df, now=None):
    df = df[df["Close"].notna()].copy()
    now = now or datetime.now(KST)
    if len(df) and df.index[-1].date() == now.date() and now.time() < dtime(16, 0):
        df = df.iloc[:-1]
    return df


def main():
    repo_root = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    uni = load_universe(repo_root)
    names = {c: n for n, c in uni.items()}
    codes = list(uni.values()) + ["069500"]
    names["069500"] = "KODEX 200"
    info = {"받은_시각_UTC": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M"),
            "출처": f"FinanceDataReader {fdr.__version__} DataReader(code, start, end) → NAVER fchart (sise.nhn, count=6000)",
            "시작일": START, "종료일": END, "종목": {}}
    for code in codes:
        for attempt in range(3):
            try:
                raw = fdr.DataReader(code, START, END)
                break
            except Exception as e:  # 네트워크 일시 오류 재시도
                print(f"{code} 재시도 {attempt + 1}: {e}")
                time.sleep(2)
        else:
            info["종목"][code] = {"이름": names[code], "오류": "받기 실패"}
            continue
        if raw is None or len(raw) == 0:
            info["종목"][code] = {"이름": names[code], "오류": "빈 데이터"}
            print(f"{code} 빈 데이터")
            continue
        n_raw = len(raw)
        n_nan = int(raw["Close"].isna().sum())
        df = confirmed_bars_kr(raw)
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        for c in ["Open", "High", "Low", "Close"]:
            df[c] = df[c].astype("float64")
        df["Volume"] = df["Volume"].astype("int64")
        df.index.name = None
        bad_open = int(df["Open"].isna().sum() + (df["Open"] <= 0).sum())
        zero_vol = int((df["Volume"] == 0).sum())
        df.to_csv(out / f"{code}.csv.gz", float_format="%.6f")
        info["종목"][code] = {"이름": names[code], "행수": len(df), "버린_행": n_raw - len(df),
                             "Close_NaN_행": n_nan, "Open_이상": bad_open, "거래량0_행": zero_vol,
                             "처음": str(df.index[0].date()), "마지막": str(df.index[-1].date())}
        print(f"{code} {names[code]:10s} {len(df):5d}행 NaN {n_nan} 버림 {n_raw - len(df)} "
              f"{df.index[0].date()} ~ {df.index[-1].date()} Open이상 {bad_open} 거래량0 {zero_vol}")
        time.sleep(0.3)
    (out / "universe.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
