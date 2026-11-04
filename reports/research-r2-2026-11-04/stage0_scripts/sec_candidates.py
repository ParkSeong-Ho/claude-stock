"""1단계: SEC XBRL frames 의 EntityPublicFloat(2013Q4~2014Q4, 10-K 표지의 '비계열 주주 보유 시가') 로 후보를 넓게 고른다.
- 공개유동시가(public float) ≥ $40B 인 회사 → 후보 (2014-12-31 시가총액 상위 20위 문턱은 약 $150B 대로 예상되므로 넉넉한 여유)
- CIK → 지금 티커 (SEC company_tickers.json). 지금 티커가 없으면 상장폐지/합병 가능성 → 따로 표시
- 2014-12-24 S&P500 스냅샷에 들어 있는지 표시
- snapshot 티커 중 CIK 를 못 찾은 것 개수도 출력
실행: python -I sec_candidates.py <data_us_pit>
"""
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
sec = d / "sec"
snap = set(json.loads((d / "sp500_members_2015-01-02.json").read_text())["tickers"])

pf = {}
names = {}
for q in ("CY2013Q4I", "CY2014Q1I", "CY2014Q2I", "CY2014Q3I", "CY2014Q4I"):
    p = sec / f"frames_dei_EntityPublicFloat_USD_{q}.json"
    j = json.loads(p.read_text())
    for x in j["data"]:
        cik = int(x["cik"])
        names[cik] = x["entityName"]
        if x["val"] > pf.get(cik, (0, ""))[0]:
            pf[cik] = (x["val"], x["end"])

tick = json.loads((sec / "company_tickers.json").read_text())
cik2t = {}
for v in tick.values():
    cik2t.setdefault(int(v["cik_str"]), []).append(v["ticker"])
t2cik = {t.replace("-", "."): c for c, ts in cik2t.items() for t in ts}

cands = sorted([(v[0], c) for c, v in pf.items() if v[0] >= 40e9], reverse=True)
print(f"public float >= $40B: {len(cands)}")
rows = []
for val, cik in cands:
    ts = cik2t.get(cik, [])
    insnap = [t for t in ts if t.replace("-", ".") in snap]
    rows.append({"cik": cik, "name": names[cik], "public_float": val, "pf_date": pf[cik][1],
                 "tickers_now": ts, "in_snapshot_by_current_ticker": insnap})
    print(f"{cik:>8d} {names[cik][:38]:38s} float ${val / 1e9:7.1f}B ({pf[cik][1]}) now={ts[:3]} snap={insnap}")
(sec / "candidates.json").write_text(json.dumps(rows, indent=1))

miss = sorted(t for t in snap if t not in t2cik)
print(f"\nsnapshot tickers without current SEC ticker→CIK match: {len(miss)}")
print(" ".join(miss))
# 스냅샷 티커 중 CIK 는 있는데 public float frames 에 없는 것
nopf = sorted(t for t in snap if t in t2cik and t2cik[t] not in pf)
print(f"\nsnapshot tickers with CIK but no public-float frame value: {len(nopf)}")
print(" ".join(nopf))
