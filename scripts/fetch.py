"""ハローワークインターネットサービスから、就業場所が広島市中区・南区の求人を取得して data/jobs.json に保存する。

- 1日1回、検索結果の一覧ページだけを読む（求人の詳細ページや連絡先は取得しない）
- ページ間は3秒以上あける
- daily: 新着（直近3日）だけ ／ full: 掲載中の全件（初回や取りこぼし対策）
"""
import argparse
import datetime as dt
import html as htmlmod
import json
import pathlib
import re
import sys
import time

import requests

BASE = "https://www.hellowork.mhlw.go.jp"
SEARCH = BASE + "/kensaku/GECA110010.do"
INIT = SEARCH + "?action=initDisp&screenId=GECA110010"
UA = "Mozilla/5.0 (personal job-search notebook; 1 run/day; github.com/clubman621-git/kyujin-techo)"
WAIT = 3.0
MAX_PAGES = {"daily": 15, "full": 170}
DATA = pathlib.Path("data/jobs.json")
JST = dt.timezone(dt.timedelta(hours=9))
TARGET = ("広島市中区", "広島市南区")

# 検索条件（フォーム調査の結果に合わせて設定）
PREF = "34"  # 広島県
CITY_FIELDS = [("todohukenHidden", "34101,34103")]  # 広島市中区・南区（市区町村コード）
NEW_FIELDS = [("jyoukenBox", "20260101001")]        # 新着求人（直近3日）
DETAIL_PER_RUN = 80  # 町名を調べるために1回で開く詳細ページの上限

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "ja"})
_last = 0.0


def req(url, data=None):
    global _last
    gap = time.time() - _last
    if gap < WAIT:
        time.sleep(WAIT - gap)
    r = s.post(url, data=data, timeout=60) if data is not None else s.get(url, timeout=60)
    _last = time.time()
    r.raise_for_status()
    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
    if "システムエラー" in r.text[:3000]:
        sys.exit("サイトがシステムエラーを返しました（フォームの形が変わった可能性があります）")
    return r.text


def text(markup):
    markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup or "")
    markup = re.sub(r"(?i)<br\s*/?>|</div>|</p>|</li>", "\n", markup)
    markup = re.sub(r"(?s)<[^>]+>", " ", markup)
    out = re.sub(r"[ \t　]+", " ", htmlmod.unescape(markup))
    return re.sub(r"(?:\s*\n\s*)+", "\n", out).strip()


def inputs(body, hidden_only=False):
    out = []
    for m in re.finditer(r"<input([^>]*)>", body):
        a = m.group(1)
        n = re.search(r'name="([^"]+)"', a)
        if not n:
            continue
        t = (re.search(r'type="([^"]+)"', a) or [None, "text"])[1].lower()
        v = re.search(r'value="([^"]*)"', a)
        val = htmlmod.unescape(v.group(1)) if v else ""
        if t == "hidden" or (not hidden_only and ((t == "text" and val) or (t in ("radio", "checkbox") and re.search(r"\bchecked\b", a)))):
            out.append((n.group(1), val))
    return out


def to_date(s):
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", s or "")
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def yen(s):
    return int(s.replace(",", ""))


def cards(body):
    starts = [m.start() for m in re.finditer(r'<table class="kyujin\b', body)]
    out = []
    for i, st in enumerate(starts):
        c = body[st:starts[i + 1] if i + 1 < len(starts) else st + 40000]
        ident = re.search(r"(\d{5}-\d{7,8})</div>", c)
        if not ident:
            continue
        rows = {}
        for m in re.finditer(r'<td class="label_col">(.*?)</td>\s*<td class="data_col">(.*?)</td>', c, re.S):
            rows[text(m[1]).split("\n")[0].strip()] = text(m[2])
        head = c[:c.find('<tr class="kyujin_body">')] if '<tr class="kyujin_body">' in c else c[:3000]
        dates = dict(re.findall(r"(受付年月日|紹介期限日)</div>\s*<div>：?([^<]+)<", head))
        labels = list(dict.fromkeys(text(x) for x in re.findall(r'<span class="bg_label[^"]*">\s*<div>([^<]+)</div>', head)))
        labels = [x for x in labels if x != "新着"]
        detail = re.search(r'href="([^"]*action=dispDetailBtn[^"]*)"', c)
        salary = rows.get("賃金", "")
        sal = re.search(r"([\d,]+)円\s*[〜～~]\s*([\d,]+)円", salary) or re.search(r"([\d,]+)円", salary)
        mn = yen(sal[1]) if sal else None
        mx = yen(sal[2]) if sal and sal.lastindex and sal.lastindex >= 2 else None
        if mn is not None and mn < 30000:  # 時給・日給は月給の比較から外す
            mn = mx = None
        out.append({
            "id": ident[1],
            "title": rows.get("職種", "").split("\n")[0].strip(),
            "employer": rows.get("事業所名", "").split("\n")[0].strip(),
            "place": rows.get("就業場所", "").replace("\n", " "),
            "labels": labels,
            "salary_text": salary.replace("\n", " "),
            "salary_min": mn, "salary_max": mx,
            "hours": rows.get("就業時間", "").replace("\n", " "),
            "holidays": rows.get("休日", "").replace("\n", " "),
            "desc": rows.get("仕事の内容", ""),
            "received": to_date(dates.get("受付年月日")),
            "deadline": to_date(dates.get("紹介期限日")),
            "_detail": SEARCH + "?" + htmlmod.unescape(detail[1]).split("?", 1)[1] if detail else None,
        })
    return out


def town_of(detail_url):
    """詳細ページの就業場所から町名だけを取り出す（番地・連絡先は保存しない）。"""
    body = req(detail_url)
    for m in re.finditer(r'<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>', body, re.S):
        if "就業場所" in text(m[1]):
            addr = text(m[2]).replace("\n", " ")
            t = re.search(r"広島市(?:中|南)区\s*([^\d０-９\s\-－（(、,]+?)(?:[\d０-９一二三四五六七八九十]+丁目|[\d０-９]|\s|$)", addr)
            if t:
                return t[1]
    return ""


def count(body):
    m = re.search(r"検索結果\s*([\d,]+)\s*件", text(body))
    return int(m[1].replace(",", "")) if m else None


def search(mode):
    body = req(INIT)
    base = [(k, v) for k, v in inputs(body, hidden_only=True) if not k.startswith("fwList") and k not in ("todohukenHidden", "action", "screenId")]
    fields = base + [("kjKbnRadioBtn", "1")] + CITY_FIELDS
    if mode == "daily":
        fields += NEW_FIELDS
    fields += [("searchBtn", "検索する"), ("action", "searchBtn"), ("screenId", "GECA110010")]
    body = req(SEARCH, fields)
    total = count(body)
    print(f"検索結果 {total} 件")
    found, page = {}, 1
    while True:
        new = 0
        for c in cards(body):
            if c["id"] not in found:
                found[c["id"]] = c
                new += 1
        if new == 0 or (total and len(found) >= total) or page >= MAX_PAGES[mode]:
            break
        page += 1
        f = [(k, v) for k, v in inputs(body) if k != "searchBtn"]
        f += [(f"fwListNaviBtn{page}", str(page)), ("action", f"fwListNaviBtn{page}")]
        body = req(SEARCH, f)
    print(f"{page} ページ読み込み、{len(found)} 件取得")
    return list(found.values()), total, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "full"], default="daily")
    a = ap.parse_args()
    got, total, _ = search(a.mode)
    got = [j for j in got if any(t in j["place"] for t in TARGET)]
    print(f"中区・南区の求人 {len(got)} 件")

    now = dt.datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    old, latest = {}, None
    if DATA.exists():
        try:
            prev_data = json.loads(DATA.read_text(encoding="utf-8"))
            old = {j["id"]: j for j in prev_data.get("jobs", [])}
            latest = prev_data.get("latest_new")
        except (ValueError, KeyError):
            old = {}
    fresh = 0
    for j in got:
        prev = old.get(j["id"])
        j["first_seen"] = prev["first_seen"] if prev else today
        j["last_seen"] = today
        if prev and prev.get("town") is not None:
            j["town"] = prev["town"]
        fresh += prev is None
        old[j["id"]] = j
    # 町名がまだ分からない求人の詳細ページを、新しいものから上限件数まで開く
    opened = 0
    for j in sorted(got, key=lambda j: j["first_seen"], reverse=True):
        if opened >= DETAIL_PER_RUN or j.get("town") is not None or not j.get("_detail"):
            continue
        try:
            j["town"] = town_of(j["_detail"])
        except (requests.RequestException, SystemExit) as e:
            print("詳細ページを読めませんでした:", j["id"], e)
            break
        opened += 1
    print(f"詳細ページ {opened} 件で町名を確認")
    for j in old.values():
        j.pop("_detail", None)
    # 紹介期限を過ぎたもの、full で見つからなかったものは外す
    keep = []
    for j in old.values():
        if j.get("deadline") and j["deadline"] < today:
            continue
        if a.mode == "full" and j.get("last_seen") != today:
            continue
        keep.append(j)
    keep.sort(key=lambda j: (j.get("first_seen", ""), j.get("received") or ""), reverse=True)
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps({"updated": now.isoformat(timespec="minutes"), "latest_new": today if fresh else latest,
                                "jobs": keep}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"新着 {fresh} 件、保存 {len(keep)} 件")


if __name__ == "__main__":
    main()
