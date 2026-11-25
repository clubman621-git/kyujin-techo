"""検索フォームの構造を調べるための一回限りのスクリプト。
フォームのHTMLと、そこから読み込まれるJSを out/ に保存する。"""
import pathlib
import re
import time

import requests

BASE = "https://www.hellowork.mhlw.go.jp"
INIT = BASE + "/kensaku/GECA110010.do?action=initDisp&screenId=GECA110010"
UA = "Mozilla/5.0 (personal job-search notebook; 1 run/day)"

out = pathlib.Path("out")
out.mkdir(exist_ok=True)
s = requests.Session()
s.headers["User-Agent"] = UA
r = s.get(INIT, timeout=60)
print("form:", r.status_code, len(r.text))
(out / "form.html").write_text(r.text, encoding="utf-8")

for src in sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', r.text)))[:15]:
    if src.startswith("http") and BASE not in src:
        continue
    url = requests.compat.urljoin(r.url, src)
    time.sleep(2)
    try:
        js = s.get(url, timeout=60)
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", src.split("?")[0].split("/")[-1])
        (out / f"js_{name}").write_text(js.text, encoding="utf-8")
        print("js:", src, js.status_code, len(js.text))
    except Exception as e:  # noqa: BLE001
        print("js failed:", src, e)

names = re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', r.text)
print("fields:", len(names))
for n in sorted(set(names)):
    if re.search(r"(?i)todo|shi|siku|kinmu|syugyo|shugyo|basho|area|jyouken|kjKbn|Hidden", n):
        print("  ", n)
