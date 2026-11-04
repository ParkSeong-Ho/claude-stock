"""주식 지식 노트(주식지식노트.html)에 들어갈 차트 데이터를 만든다.

모든 숫자는 저장소에 이미 있는 데이터에서 온다(인터넷 안 씀).
- R0 미국 시세: research-2026-11-04 브랜치 reports/research-2026-11-04/data/
- R2 결과·국내 시세: research-r2-2026-11-04 브랜치 reports/research-r2-2026-11-04/
지표는 트레이너 브레인의 add_indicators() 를 그대로 불러 계산한다(트레이너가 보는 숫자와 같게).

실행(저장소 루트에서): python docs/knowledge/build_data.py
결과: docs/knowledge/주식지식노트.html 의 /*__DATA__*/ 자리에 JSON 을 넣은 완성 파일.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marathoner_brain import MarathonerBrain  # noqa: E402
from sprinter_brain import SprinterBrain      # noqa: E402
from pioneer_brain import PioneerBrain        # noqa: E402

R0 = "origin/research-2026-11-04:reports/research-2026-11-04"
R2 = "origin/research-r2-2026-11-04:reports/research-r2-2026-11-04"
HERE = Path(__file__).resolve().parent


def git_bytes(spec: str) -> bytes:
    out = subprocess.run(["git", "-C", str(ROOT), "show", spec], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show 실패: {spec}\n{out.stderr.decode()[:300]}")
    return out.stdout


def read_csv(spec: str, **kw) -> pd.DataFrame:
    b = git_bytes(spec)
    comp = "gzip" if spec.endswith(".gz") else None
    return pd.read_csv(io.BytesIO(b), compression=comp, encoding="utf-8-sig", **kw)


def r(x, n=2):
    return None if pd.isna(x) else round(float(x), n)


# ---------------------------------------------------------------- 1. 차트 읽기: AAPL 2023~2024
px = read_csv(f"{R0}/data/AAPL.csv.gz", index_col=0, parse_dates=True)
m = MarathonerBrain().add_indicators(px.copy())
s = SprinterBrain().add_indicators(px.copy())
p = PioneerBrain().add_indicators(px.copy())
W0, W1 = "2023-01-03", "2024-12-31"
win = px.loc[W0:W1].index
price = []
for d in win:
    price.append({"d": d.strftime("%Y-%m-%d"), "c": r(px.at[d, "Close"]), "o": r(px.at[d, "Open"]),
                  "ma5": r(s.at[d, "MA5"]), "ma20": r(m.at[d, "MA20"]), "ma60": r(m.at[d, "MA60"]),
                  "rsi": r(m.at[d, "RSI"], 1), "vol": int(px.at[d, "Volume"]),
                  "vavg": int(p.at[d, "VolAvg20"]) if not pd.isna(p.at[d, "VolAvg20"]) else None})

trades = read_csv(f"{R2}/results/trades.csv.gz")
us_a0 = trades[trades["run"] == "us|100k|A0|전체 2015-26"].copy()
aapl = us_a0[(us_a0["code"] == "AAPL") & (us_a0["entry_date"] >= W0) & (us_a0["entry_date"] <= W1)]
aapl_tr = [{"trainer": t.sleeve, "sig": t.signal_date, "in": t.entry_date, "inp": r(t.entry_price),
            "out": None if pd.isna(t.exit_date) else t.exit_date, "outp": r(t.exit_price),
            "why_in": t.signal_reason, "why_out": None if pd.isna(t.exit_reason) else t.exit_reason}
           for t in aapl.itertuples()]

# ---------------------------------------------------------------- 2. 다음 날 시가: 신호 종가 → 체결 시가 차이
closes = {}
gaps = []
for t in us_a0.itertuples():
    if t.code not in closes:
        closes[t.code] = read_csv(f"{R0}/data/{t.code}.csv.gz", index_col=0, parse_dates=True)
    c = closes[t.code]
    sd, ed = pd.Timestamp(t.signal_date), pd.Timestamp(t.entry_date)
    if sd in c.index and ed in c.index:
        gaps.append(float(c.at[ed, "Open"] / c.at[sd, "Close"] - 1))
g = pd.Series(gaps)
gap_stats = {"n": int(len(g)), "mean_abs": r(g.abs().mean() * 100, 2), "median_abs": r(g.abs().median() * 100, 2),
             "share_over_1pct": r((g.abs() > 0.01).mean() * 100, 1), "max_up": r(g.max() * 100, 1),
             "max_down": r(g.min() * 100, 1)}
bins = [-0.06, -0.03, -0.02, -0.01, -0.005, 0, 0.005, 0.01, 0.02, 0.03, 0.06]
hist = pd.cut(g.clip(-0.0599, 0.0599), bins=bins).value_counts(sort=False)
gap_hist = [{"lo": r(iv.left * 100, 1), "hi": r(iv.right * 100, 1), "n": int(n)} for iv, n in hist.items()]

# ---------------------------------------------------------------- 3. 비용: 스프린터
FEE, SLIP = 0.001, 0.0005
sp = us_a0[(us_a0["sleeve"] == "스프린터") & us_a0["exit_price"].notna()].copy()
sp["gross"] = sp["exit_price"] / sp["entry_price"] - 1
sp["net"] = (sp["exit_price"] * (1 - SLIP) * (1 - FEE)) / (sp["entry_price"] * (1 + SLIP) * (1 + FEE)) - 1


def kind(reason: str) -> str:
    if "목표" in reason or "달성" in reason:
        return "익절"
    if "손절" in reason:
        return "손절"
    if "지났" in reason or "정리" in reason:
        return "시간 정리"
    return "기타"


sp["kind"] = sp["exit_reason"].astype(str).map(kind)
sprinter = {"n": int(len(sp)), "win_gross": r((sp["gross"] > 0).mean() * 100, 1),
            "win_net": r((sp["net"] > 0).mean() * 100, 1), "avg_gross": r(sp["gross"].mean() * 100, 2),
            "avg_net": r(sp["net"].mean() * 100, 2),
            "kinds": [{"k": k, "n": int(n), "avg_net": r(sp.loc[sp["kind"] == k, "net"].mean() * 100, 2)}
                      for k, n in sp["kind"].value_counts().items()],
            "breakeven_design": r((0.015 + 0.003) / (0.05 + 0.015) * 100, 1)}

# ---------------------------------------------------------------- 4. 쉬는 돈: 일별 평가액 (주 1회로 줄임)
def curve(market: str, total: str, arm: str):
    df = read_csv(f"{R2}/results/daily_full/{market}_{total}_{arm}_전체 2015-26.csv.gz")
    df = pd.concat([df.iloc[::5], df.iloc[[-1]]])
    df = df.drop_duplicates("date")
    v = df["value"].astype(float)
    peak = v.cummax()
    return {"d": df["date"].tolist(), "v": [r(x, 0) for x in v], "dd": [r(x * 100, 1) for x in (v / peak - 1)],
            "stock": [r(x * 100, 0) for x in df["stock_frac"]] if "stock_frac" in df else None}


curves = {}
for mk, tot in (("us", "100k"), ("us_pit", "100k"), ("kr", "100m")):
    curves[mk] = {arm: curve(mk, tot, arm) for arm in ("A0", "A1", "A2", "IDX")}

summary = read_csv(f"{R2}/results/summary.csv")
summary = summary[summary["total"].isin(["100k", "100m"])]
full = summary[summary["period"] == "전체 2015-26"]
fullrows = [{"m": t.market, "arm": t.config, "ret": r(t["return"] * 100, 1), "mdd": r(t["mdd"] * 100, 1),
             "stock": r(t["stock_frac_mean"] * 100, 0), "ew": r(t["ew_bh_return"] * 100, 1)}
            for _, t in full.iterrows() if t["config"] in ("A0", "A1", "A2", "IDX")]

regime_rows = [{"m": t["market"], "arm": t["config"], "p": t["period"], "ret": r(t["return"] * 100, 1)}
               for _, t in summary.iterrows() if t["config"] in ("A0", "A1", "A1T", "A2", "IDX")]

# ---------------------------------------------------------------- 5. 무작위 대조
rnd = read_csv(f"{R2}/results/random.csv")
rnd = rnd[rnd["run"].str.endswith("전체 2015-26")]
random_rows = [{"m": t["run"].split("|")[0], "g": t["group"], "actual": r(t["actual"], 0),
                "mean": r(t["random_mean"], 0), "sd": r(t["random_sd"], 0), "pct": r(t["pct_below"] * 100, 0),
                "trades": int(t["trades"])} for _, t in rnd.iterrows()]

# ---------------------------------------------------------------- 6. 069500(분배금 반영) vs KS200(가격지수)
k69 = read_csv(f"{R2}/data/kr/069500.csv.gz", index_col=0, parse_dates=True)["Close"]
ks = read_csv(f"{R2}/data/kr/KS200.csv.gz", index_col=0, parse_dates=True)["Close"]
both = pd.concat([k69.rename("k69"), ks.rename("ks")], axis=1).dropna().loc["2015-01-02":]
both = both / both.iloc[0] * 100
both = pd.concat([both.iloc[::5], both.iloc[[-1]]])
both = both[~both.index.duplicated()]
bench = {"d": [d.strftime("%Y-%m-%d") for d in both.index], "k69": [r(x, 1) for x in both["k69"]],
         "ks": [r(x, 1) for x in both["ks"]]}

# ---------------------------------------------------------------- 7. 거래정지 예: 삼성전자 2018 액면분할
sam = read_csv(f"{R2}/data/kr/005930.csv.gz", index_col=0, parse_dates=True).loc["2018-04-25":"2018-05-09"]
halt = [{"d": d.strftime("%Y-%m-%d"), "o": r(x.Open, 0), "c": r(x.Close, 0), "v": int(x.Volume)}
        for d, x in sam.iterrows()]

DATA = {"price": price, "aapl_trades": aapl_tr, "gap": gap_stats, "gap_hist": gap_hist, "sprinter": sprinter,
        "curves": curves, "full": fullrows, "regimes": regime_rows, "random": random_rows, "bench": bench,
        "halt": halt}

tpl = (HERE / "주식지식노트.template.html").read_text(encoding="utf-8")
out = tpl.replace("/*__DATA__*/null", json.dumps(DATA, ensure_ascii=False, separators=(",", ":")))
(HERE / "주식지식노트.html").write_text(out, encoding="utf-8")
print("데이터 크기", len(json.dumps(DATA, ensure_ascii=False)) // 1024, "KB")
print("gap", gap_stats)
print("sprinter", sprinter)
print("AAPL trades", len(aapl_tr), [ (t['trainer'], t['in'], t['out']) for t in aapl_tr][:12])
print("halt", halt)
