"""検索フォームの調査（一回限り）。結果は out/ に保存する。"""
import pathlib
import re
import sys
import time

sys.path.insert(0, "scripts")
import fetch  # noqa: E402

out = pathlib.Path("out")
out.mkdir(exist_ok=True)
log = []


def p(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    log.append(line)


body = fetch.req(fetch.INIT)
modal = dict(screenId="GECZTDFMDL", action="initDisp", codeAssistType="3", codeAssistItemCode="todohukenHidden",
             codeAssistItemName="todohukenNameLbl", onModal="true", codeAssistModalTitle="都道府県から選択",
             codeAssistText="", codeAssistLinkLabel="", codeAssistLinkURL="", codeAssistSelectableOne="false",
             codeAssistSelectableTwo="true", codeAssistSelectableThree="true", codeAssistSelectableFour="true",
             codeAssistSelectLimitOne="3", codeAssistSelectLimitTwo="3", codeAssistSelectLimitThree="5",
             codeAssistSelectLimitFour="5", codeAssistLimitTotalTwo="false", codeAssistLimitTotalThree="false",
             codeAssistLimitTotalFour="true", codeAssistMapKey="todoufukenMap", codeAssistCode="ID_todohukenHidden",
             codeAssistCodeName="ID_todohukenNameLbl", codeAssistFunc="TODOUFUKEN_FUNC", codeAssistDelimitTwo="false",
             codeAssistDelimitThree="true", codeAssistDelimitFour="false", selectedCodes="")
m = fetch.req(fetch.BASE + "/kensaku/ECZTDFMDL.do", modal)
(out / "modal.html").write_text(m, encoding="utf-8")
p("modal", len(m))
for hit in re.findall(r'<input[^>]*value="(34[^"]*)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{0,20})', m)[:60]:
    p("  ", hit)


def trial(label, extra):
    b = fetch.req(fetch.INIT)
    base = [(k, v) for k, v in fetch.inputs(b, hidden_only=True)
            if not k.startswith("fwList") and k not in ("todohukenHidden", "action", "screenId")]
    f = base + [("kjKbnRadioBtn", "1")] + extra + [("searchBtn", "検索する"), ("action", "searchBtn"), ("screenId", "GECA110010")]
    try:
        r = fetch.req(fetch.SEARCH, f)
    except SystemExit as e:
        p(label, "ERROR", e)
        return
    cs = fetch.cards(r)
    places = sorted({re.sub(r"\s.*", "", c["place"])[:12] for c in cs})
    p(label, "count=", fetch.count(r), "cards=", len(cs), "入力エラー" in r, places[:8])
    (out / f"trial_{label}.html").write_text(r, encoding="utf-8")


trial("pref34", [("todohukenHidden", "34")])
trial("city_comma", [("todohukenHidden", "34101,34103")])
trial("city_one", [("todohukenHidden", "34101")])
trial("pref34_new", [("todohukenHidden", "34"), ("jyoukenBox", "20260101001")])
(out / "log.txt").write_text("\n".join(log), encoding="utf-8")
