#!/usr/bin/env python3
"""リサーチ事業部ニュースを新聞風の紙面にする（標準ライブラリのみ・外部API/課金なし）。

使い方:
  python3 news_paper.py <号JSON> [--out 出力先] [--slug 推測されにくい文字列] [--no-png] [--front] [--pdf]

出力（--out 既定: ./site）:
  <out>/<slug>/<YYYYMMDD>/index.html   全文（スマホ1段・PC多段）
  <out>/<slug>/<YYYYMMDD>/paper.png    紙面画像（PCレイアウト幅1280・1.5倍、LINE送信用）
  <out>/<slug>/<YYYYMMDD>/paper_s.png  紙面画像の縮小版（LINE プレビュー用）
  <out>/<slug>/<YYYYMMDD>/front.png    縦長の1面（1080x1440、--front 指定時）
  <out>/<slug>/<YYYYMMDD>/paper.pdf    保存用（--pdf 指定時）
  <out>/<slug>/index.html              バックナンバー一覧
  <out>/robots.txt                     検索エンジン避け
PNG/PDF は Google Chrome のヘッドレス機能で書き出す（Mac/Linux 自動検出）。
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date

PAPER_NAME = "AIカンパニー リサーチ新聞"
PUBLISHER = "AIカンパニー リサーチ事業部"
WEEKDAYS = "月火水木金土日"
# 天気欄の一言。号JSONに "weather" が無ければ号数で順番に使う
WEATHER = ["晴れ時々AI", "くもり時々GPU", "トークンの雨", "所により推論", "快晴・学習日和",
           "ところにより幻覚", "曇りのちファインチューニング", "にわかデプロイ", "南の風・プロンプト強し",
           "霧（コンテキスト長に注意）"]

CSS = r"""
:root{--paper:#f5f0e6;--ink:#1b1b1b;--sub:#555;--rule:#1b1b1b;--accent:#a8261b;--box:#ebe3d3}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#d9d3c7;color:var(--ink);
 font-family:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP","Noto Serif CJK JP",serif;line-height:1.75}
.sheet{max-width:1080px;margin:0 auto;background:var(--paper);padding:28px 22px 40px}
.mast{text-align:center;border-bottom:4px double var(--rule);padding-bottom:10px}
.mast .name{font-size:clamp(22px,6vw,64px);font-weight:900;letter-spacing:.06em;white-space:nowrap;line-height:1.2;margin:0}
.mast .meta{display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px 12px;
 border-top:1px solid var(--rule);margin-top:10px;padding-top:6px;font-size:13px;color:var(--sub)}
.kicker{display:inline-block;background:var(--accent);color:#fff;font-size:12px;font-weight:700;
 padding:1px 8px;letter-spacing:.1em;font-family:"Hiragino Sans","Noto Sans JP","Noto Sans CJK JP",sans-serif}
.top{padding:18px 0;border-bottom:2px solid var(--rule)}
.top h1{font-size:clamp(26px,5.6vw,50px);line-height:1.3;margin:8px 0 6px;font-weight:900}
.top .subhead{font-size:clamp(16px,3vw,22px);font-weight:700;color:var(--sub);margin:0 0 12px;
 border-left:5px solid var(--accent);padding-left:10px}
.lead{font-weight:700;font-size:17px;margin:0 0 10px}
.cols p{margin:0 0 .8em;text-indent:1em;font-size:16px}
.grid{display:grid;grid-template-columns:1fr;gap:0}
.story{padding:14px 0;border-bottom:1px solid var(--rule)}
.story h2{font-size:22px;line-height:1.4;margin:6px 0;font-weight:900}
.story p{margin:0;font-size:15px}
.side{display:grid;grid-template-columns:1fr;gap:16px;margin-top:18px}
.box{background:var(--box);padding:14px 16px;border-top:3px solid var(--rule)}
.box h3{margin:0 0 8px;font-size:15px;letter-spacing:.15em;
 font-family:"Hiragino Sans","Noto Sans JP","Noto Sans CJK JP",sans-serif}
.num{border-bottom:1px dotted #999;padding:6px 0}
.num b{display:block;font-size:26px;color:var(--accent);line-height:1.3}
.num span{font-size:14px}
.briefs ul{margin:0;padding-left:1.1em}.briefs li{font-size:15px;margin:4px 0}
.column p{margin:0;font-size:15px}
.foot{margin-top:24px;border-top:4px double var(--rule);padding-top:8px;font-size:12px;color:var(--sub);
 display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}
.foot a{color:var(--sub)}
.hl{color:inherit;text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:.2em;text-decoration-color:var(--sub)}
.hl:hover,.hl:focus-visible{text-decoration-thickness:2px;text-decoration-color:currentColor}
body.shot .hl{text-decoration:none}
@media (min-width:760px){
 .sheet{padding:40px 48px 56px}
 .cols{column-count:3;column-gap:28px;column-rule:1px solid #bbb}
 .grid{grid-template-columns:repeat(3,1fr);gap:0 28px}
 .story{border-bottom:none;position:relative}
 .grid .story:not(:nth-child(3n)):not(:last-child)::after{content:"";position:absolute;top:14px;bottom:0;right:-14px;border-right:1px solid #bbb}
 .side{grid-template-columns:1fr 1fr 1fr}
}
figure{margin:10px 0 12px}
figure .phwrap{position:relative}
figure .phwrap img.ph{position:absolute;inset:0;height:100%}
body.front .top .phwrap,body.front .top .phwrap .ph{height:270px}
figure .ph{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:var(--box);filter:saturate(.85) contrast(1.02)}
figure svg.ph{height:auto}
figcaption{font-size:11px;color:var(--sub);margin-top:3px;text-align:right;
 font-family:"Hiragino Sans","Noto Sans JP","Noto Sans CJK JP",sans-serif}
figcaption a{color:var(--sub)}
.top figure .ph{aspect-ratio:16/8}
@media (min-width:760px){
 .top .topwrap{display:grid;grid-template-columns:1.25fr 1fr;gap:0 28px;align-items:start}
 .top figure{margin-top:4px}
}
.grid .story:nth-child(n+4){border-top:1px solid var(--rule);padding-top:18px}
.more{margin-top:8px;border-top:2px solid var(--rule);padding-top:10px}
.more>h3{margin:0 0 6px;font-size:15px;letter-spacing:.15em;
 font-family:"Hiragino Sans","Noto Sans JP","Noto Sans CJK JP",sans-serif}
.more .list{display:grid;grid-template-columns:repeat(3,1fr);gap:0 28px}
.mini{display:grid;grid-template-columns:132px 1fr;gap:0 12px;padding:10px 0;border-bottom:1px dotted #999;align-items:start}
.mini figure{margin:0;grid-row:span 3}
.mini figcaption{display:none}
.mini .kicker{justify-self:start;font-size:11px}
.mini h4{margin:3px 0 2px;font-size:16px;line-height:1.4;font-weight:900}
.mini p{margin:0;font-size:13px;color:var(--sub);line-height:1.6}
/* LINE用の紙面画像（PCレイアウトを1枚に） */
body.shot{background:var(--paper)}
body.shot .sheet{max-width:none;width:1280px}
body.shot .foot a{display:none}
/* 1面PNG用（1080x1440固定、--front 指定時） */
body.front{background:var(--paper);width:1080px;height:1440px;overflow:hidden}
body.front .sheet{width:1080px;height:1440px;max-width:none;padding:36px 56px 40px;display:flex;flex-direction:column}
body.front .mast .name{font-size:64px}
body.front .mast .meta{font-size:18px}
body.front .top h1{font-size:52px}
body.front .top .subhead{font-size:26px}
body.front .lead{font-size:22px;line-height:1.7}
body.front .kicker{font-size:16px;padding:2px 10px}
body.front .fs{flex:1;display:flex;flex-direction:column;justify-content:space-around}
body.front .fs .story{border:none;border-bottom:1px solid #999;padding:12px 0;display:grid;grid-template-columns:230px 1fr;gap:0 22px;align-items:center}
body.front .fs .story figure{margin:0;grid-row:span 3}
body.front .fs .story figcaption{display:none}
body.front .top figure{margin:8px 0 10px}
body.front .top figure .ph{height:270px;aspect-ratio:auto}
body.front .top figcaption{font-size:13px}
body.front .lead{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
body.front .fs .story h2{font-size:29px;line-height:1.35;margin:4px 0 2px}
body.front .fs .story p{font-size:17px;color:var(--sub);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
body.front .fs .story .kicker{justify-self:start}
body.front .nums{display:flex;gap:16px;margin-top:14px}
body.front .nums div{flex:1;background:var(--box);border-top:3px solid var(--rule);padding:10px 12px}
body.front .nums b{display:block;font-size:34px;color:var(--accent);line-height:1.3}
body.front .nums span{font-size:15px}
body.front .cta{margin-top:16px;text-align:center;font-size:22px;font-weight:700;
 border:2px solid var(--rule);padding:10px;font-family:"Hiragino Sans","Noto Sans JP","Noto Sans CJK JP",sans-serif}
"""

e = html.escape


def date_line(d):
    y, m, dd = map(int, d.split("-"))
    wd = WEEKDAYS[date(y, m, dd).weekday()]
    return f"{y}年{m}月{dd}日（{wd}）"


def head(title):
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=1280">'
        '<meta name="robots" content="noindex,nofollow,noarchive">'
        f"<title>{e(title)}</title><style>{CSS}</style></head>"
    )


def masthead(issue):
    return (
        f'<header class="mast"><p class="name">{e(PAPER_NAME)}</p>'
        f'<div class="meta"><span>第{int(issue["issue_no"])}号</span>'
        f'<span>{date_line(issue["date"])}</span>'
        f'<span>{e(issue.get("weather") or WEATHER[(int(issue["issue_no"]) - 1) % len(WEATHER)])}</span></div></header>'
    )


# 記事は stories の先頭 MAIN_STORIES 本を写真付きの大枠、残りを「ほかのニュース」に小さく並べる
MAIN_STORIES = 6

PALETTE = ["#2f4b6e", "#7a3b2e", "#3e5f3a", "#6b5a2b", "#4b3a63", "#2e5e63"]


def fallback_svg(kicker):
    """画像が無い記事用の自前イラスト（著作権の心配がない）。カテゴリ名から色を決める。"""
    c = PALETTE[sum(map(ord, kicker)) % len(PALETTE)]
    lines = "".join(
        f'<line x1="{x}" y1="0" x2="{x-180}" y2="180" stroke="#fff" stroke-opacity=".07" stroke-width="10"/>'
        for x in range(0, 520, 34)
    )
    return (
        f'<svg class="ph" viewBox="0 0 320 180" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{e(kicker)}">'
        f'<rect width="320" height="180" fill="{c}"/>{lines}'
        f'<text x="160" y="{90 + min(44, 250 // max(len(kicker), 1)) * 0.35:.0f}" text-anchor="middle" font-size="{min(44, 250 // max(len(kicker), 1))}" font-weight="900" fill="#fff" fill-opacity=".9" '
        f'font-family="Hiragino Mincho ProN,Noto Serif CJK JP,serif" letter-spacing="6">{e(kicker)}</text></svg>'
    )


def source_name(item):
    img = item.get("image") or {}
    if item.get("source"):
        return item["source"]
    if img.get("credit"):
        return img["credit"]
    u = item.get("url") or img.get("link") or ""
    return urllib.parse.urlparse(u).netloc.removeprefix("www.") if u else ""


def ai_fill_images(issue, limit=6):
    """サムネイルが取れなかった記事に AI 画像（OpenAI）を作って入れる（syu 指示 2026-11-19）。
    鍵 secrets/openai.env が無ければ何もしない（自前イラストのまま）。画像は号フォルダの img/ に保存される。"""
    import base64, io, threading
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.path.join(here, "secrets", "openai.env")
    if not os.path.isfile(env):
        return 0
    key = dict(re.findall(r"^(\w+)=(.*)$", open(env, encoding="utf-8").read(), re.M)).get("OPENAI_API_KEY", "").strip()
    if not key:
        return 0
    todo = [it for it in [issue["top"]] + issue.get("stories", []) if not (it.get("image") or {}).get("src")][:limit]
    outdir = tempfile.mkdtemp(prefix="aiimg_")
    models = [m for m in os.environ.get("NEWS_AI_MODEL", "gpt-image-2,gpt-image-1.5").split(",") if m]

    def work(i, it):
        prompt = ("Editorial news illustration for a Japanese newspaper-style page. Topic: "
                  f"{it.get('kicker', '')} - {it['headline']}. Depict the theme symbolically with objects, places or "
                  "abstract shapes, muted newspaper-friendly colors. No text, no letters, no numbers, no logos, "
                  "no real or recognizable people, no brand products, no flags.")
        for model in models:
            body = {"model": model, "size": "1536x1024", "quality": os.environ.get("NEWS_AI_QUALITY", "low"),
                    "n": 1, "prompt": prompt}
            req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    raw = base64.b64decode(json.load(r)["data"][0]["b64_json"])
                break
            except urllib.error.HTTPError as ex:
                if ex.code not in (400, 404):
                    return
            except Exception:
                return
        else:
            return
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            h = int(im.width * 9 / 16)
            top = (im.height - h) // 2
            im = im.crop((0, top, im.width, top + h)).resize((1280, 720))
            path = os.path.join(outdir, f"ai_{i:02d}.jpg")
            im.save(path, "JPEG", quality=82)
        except Exception:
            path = os.path.join(outdir, f"ai_{i:02d}.png")
            open(path, "wb").write(raw)
        it["image"] = {"src": path, "ai": True}

    ths = [threading.Thread(target=work, args=(i, it)) for i, it in enumerate(todo)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    return sum(1 for it in todo if (it.get("image") or {}).get("ai"))


def figure(item):
    """元記事のサムネイルを直接表示（ホットリンク）。読み込めない時・画像が無い時は自前イラスト。
    item: {"url": 元記事URL, "source": 媒体名, "image": {"src": 画像URL}}（image は fetch_og_images が自動で埋める）"""
    img = item.get("image") or {}
    fb = fallback_svg(item.get("kicker", "NEWS"))
    if not img.get("src"):
        return f"<figure>{fb}</figure>"
    name = e(source_name(item))
    link = item.get("url") or img.get("link")
    cap = f'<a href="{e(link)}" rel="noopener">{name or "元記事"}</a>' if link else name
    if img.get("ai"):
        cap = "AI 生成のイメージ"
    return (
        f'<figure><div class="phwrap">{fb}<img class="ph" src="{e(img["src"])}" alt="" '
        'referrerpolicy="no-referrer" onerror="this.remove()"></div>'
        + (f"<figcaption>画像: {cap}</figcaption>" if cap else "")
        + "</figure>"
    )


def hl(item):
    """見出し文字列。元記事 url があれば参照元へのリンクにする（syu 指示 2026-11-13）。"""
    text = e(item["headline"])
    u = item.get("url")
    if not u:
        return text
    return f'<a class="hl" href="{e(u)}" target="_blank" rel="noopener">{text}</a>'


def fetch_og_image(url, timeout=8):
    """元記事ページから og:image / twitter:image の URL を取る（取れなければ空文字）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AIC research-news)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            h = r.read(400_000).decode(r.headers.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return ""
    for prop in ("og:image", "og:image:url", "twitter:image"):
        for pat in (rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]*content=["\']([^"\']+)',
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{prop}["\']'):
            m = re.search(pat, h, re.I)
            if m:
                return urllib.parse.urljoin(url, html.unescape(m.group(1)))
    return ""


# 今日の数字は固定 3 つ（syu 指示 2026-11-14）。公開時に Yahoo Finance から取得し、号 JSON の numbers を上書きする
MARKETS = [("^GSPC", "S&P500", "{:,.2f}", False), ("^N225", "日経平均", "{:,.0f}円", False), ("JPY=X", "ドル円", "{:.2f}円", True)]


def fetch_markets():
    import datetime as _dt
    jst = _dt.timezone(_dt.timedelta(hours=9))
    out = []
    for sym, name, fmt, live in MARKETS:
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=10d&interval=1d"
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                res = json.load(r)["chart"]["result"][0]
            m = res["meta"]
            price, t = m["regularMarketPrice"], m["regularMarketTime"]
            ex = _dt.timezone(_dt.timedelta(seconds=m.get("gmtoffset", 32400)))  # 取引所の現地時間で日付を比べる
            day = _dt.datetime.fromtimestamp(t, ex).date()
            prev = None
            for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
                if c is not None and _dt.datetime.fromtimestamp(ts, ex).date() < day:
                    prev = c
            chg = f"・{'▲' if price >= prev else '▼'}{abs(price / prev - 1) * 100:.2f}%" if prev else ""
            when = _dt.datetime.fromtimestamp(t, jst).strftime("%-m/%-d %H:%M 時点") if live \
                else f"{day.month}/{day.day} 終値"
            out.append({"value": fmt.format(price), "label": f"{name}（{when}{chg}）"})
        except Exception:
            out.append({"value": "—", "label": f"{name}（取得できず）"})
    return out


def fetch_og_images(issue):
    """url があって画像未指定の記事に、元記事のサムネイル URL を埋める。"""
    for item in [issue["top"]] + issue.get("stories", []):
        img = item.setdefault("image", {})
        if not img.get("src") and item.get("url"):
            src = fetch_og_image(item["url"])
            if src:
                img["src"] = src


def first_sentence(text):
    m = re.match(r"(.+?。)", text)
    return m.group(1) if m else text


def render_full(issue, archive_url=None, body_class=""):
    t = issue["top"]
    body = "".join(f"<p>{e(p)}</p>" for p in t["body"])
    stories = "".join(
        f'<article class="story">{figure(s)}<span class="kicker">{e(s["kicker"])}</span>'
        f'<h2>{hl(s)}</h2><p>{e(s["body"])}</p></article>'
        for s in issue.get("stories", [])[:MAIN_STORIES]
    )
    minis = "".join(
        f'<article class="mini">{figure(s)}<span class="kicker">{e(s["kicker"])}</span>'
        f'<h4>{hl(s)}</h4><p>{e(first_sentence(s["body"]))}</p></article>'
        for s in issue.get("stories", [])[MAIN_STORIES:]
    )
    nums = "".join(
        f'<div class="num"><b>{e(n["value"])}</b><span>{e(n["label"])}</span></div>'
        for n in issue.get("numbers", [])
    )
    briefs = "".join(f"<li>{e(b)}</li>" for b in issue.get("briefs", []))
    col = issue.get("column")
    col_html = (
        f'<div class="box column"><h3>{e(col["title"])}</h3><p>{e(col["body"])}</p></div>'
        if col else ""
    )
    back = f'<a href="{e(archive_url)}">バックナンバー</a>' if archive_url else ""
    return (
        head(f'{PAPER_NAME} 第{issue["issue_no"]}号')
        + f'<body class="{body_class}"><div class="sheet">'
        + masthead(issue)
        + f'<section class="top"><span class="kicker">{e(t["kicker"])}</span>'
        f'<h1>{hl(t)}</h1><p class="subhead">{e(t["subhead"])}</p>'
        f'<div class="topwrap"><div>{figure(t)}</div><p class="lead">{e(t["lead"])}</p></div>'
        f'<div class="cols">{body}</div></section>'
        + f'<section class="grid">{stories}</section>'
        + (f'<section class="more"><h3>ほかのニュース</h3><div class="list">{minis}</div></section>' if minis else "")
        + '<section class="side">'
        + (f'<div class="box"><h3>今日の数字</h3>{nums}</div>' if nums else "")
        + (f'<div class="box briefs"><h3>短信</h3><ul>{briefs}</ul></div>' if briefs else "")
        + col_html
        + "</section>"
        + f'<footer class="foot"><span>発行 {e(PUBLISHER)}</span>{back}</footer>'
        + "</div></body></html>"
    )


def render_front(issue):
    t = issue["top"]
    stories = "".join(
        f'<article class="story">{figure(s)}<span class="kicker">{e(s["kicker"])}</span>'
        f'<h2>{e(s["headline"])}</h2><p>{e(first_sentence(s["body"]))}</p></article>'
        for s in issue.get("stories", [])[:3]
    )
    nums = "".join(
        f'<div><b>{e(n["value"])}</b><span>{e(n["label"])}</span></div>'
        for n in issue.get("numbers", [])[:3]
    )
    return (
        head("front")
        + '<body class="front"><div class="sheet">'
        + masthead(issue)
        + f'<section class="top"><span class="kicker">{e(t["kicker"])}</span>'
        f'<h1>{e(t["headline"])}</h1><p class="subhead">{e(t["subhead"])}</p>'
        f'{figure(t)}<p class="lead">{e(t["lead"])}</p></section>'
        + f'<section class="fs">{stories}</section>'
        + '<div class="cta">▶ 全文はリンクから</div>'
        + "</div></body></html>"
    )


def render_index_items(items):
    """items: [{"dir": "YYYYMMDD", "date": "YYYY-MM-DD", "issue_no": n, "headline": "..."}]（新しい順に並べ替える）"""
    rows = []
    for i in sorted(items, key=lambda x: x["dir"], reverse=True):
        rows.append(
            f'<article class="story"><span class="kicker">第{int(i["issue_no"])}号</span>'
            f'<h2><a href="{e(i["dir"])}/" style="color:inherit">{e(i["headline"])}</a></h2>'
            f'<p>{date_line(i["date"])}</p></article>'
        )
    return (
        head(f"{PAPER_NAME} バックナンバー")
        + '<body><div class="sheet"><header class="mast">'
        f'<p class="name">{e(PAPER_NAME)}</p><div class="meta"><span>バックナンバー</span></div></header>'
        + "".join(rows)
        + f'<footer class="foot"><span>発行 {e(PUBLISHER)}</span></footer></div></body></html>'
    )


def index_item(issue):
    return {"dir": issue["date"].replace("-", ""), "date": issue["date"],
            "issue_no": int(issue["issue_no"]), "headline": issue["top"]["headline"]}


def render_index(slug_dir):
    items = []
    for d in os.listdir(slug_dir):
        p = os.path.join(slug_dir, d, "issue.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                items.append(index_item(json.load(f)))
    return render_index_items(items)


def find_chrome():
    cands = [
        os.environ.get("CHROME_PATH"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    import glob
    cands += sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")), reverse=True)
    cands += sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/headless_shell")), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def chrome_run(chrome, args, src):
    with tempfile.TemporaryDirectory() as prof:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--hide-scrollbars", f"--user-data-dir={prof}"] + args + ["file://" + os.path.abspath(src)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)


def page_height(chrome, src, width):
    """1回目の起動でページの高さを測る（JSで高さをDOMに書き込み、--dump-dom で読む）。"""
    with open(src, encoding="utf-8") as f:
        h = f.read()
    probe = src + ".probe.html"
    js = ("<script>window.addEventListener('load',()=>{const m=document.createElement('meta');"
          "m.id='ph';m.content=document.documentElement.scrollHeight;document.head.appendChild(m);});</script>")
    with open(probe, "w", encoding="utf-8") as f:
        f.write(h.replace("</head>", js + "</head>"))
    with tempfile.TemporaryDirectory() as prof:
        out = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={prof}",
             f"--window-size={width},1000", "--virtual-time-budget=5000", "--dump-dom", "file://" + os.path.abspath(probe)],
            check=True, capture_output=True, text=True, timeout=90).stdout
    os.remove(probe)
    m = re.search(r'id="ph" content="(\d+)"', out)
    return int(m.group(1)) if m else 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue")
    ap.add_argument("--out", default="site")
    ap.add_argument("--slug", default="research-news")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="元記事のサムネイルを取りに行かない")
    ap.add_argument("--front", action="store_true", help="縦長の1面PNG（1080x1440）も作る")
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()

    with open(a.issue, encoding="utf-8") as f:
        issue = json.load(f)
    slug_dir = os.path.join(a.out, a.slug)
    day = issue["date"].replace("-", "")
    d = os.path.join(slug_dir, day)
    os.makedirs(d, exist_ok=True)

    if not a.no_fetch:
        fetch_og_images(issue)
        issue["numbers"] = fetch_markets()
        n_ai = ai_fill_images(issue)
        if n_ai:
            print(f"ai_images={n_ai}", file=sys.stderr)

    # ローカル画像（JSON からの相対パス）は号フォルダの img/ にコピーして参照を張り替える
    base = os.path.dirname(os.path.abspath(a.issue))
    for item in [issue["top"]] + issue.get("stories", []):
        src = (item.get("image") or {}).get("src", "")
        if src and not re.match(r"^https?://", src):
            p = os.path.join(base, src)
            if os.path.isfile(p):
                os.makedirs(os.path.join(d, "img"), exist_ok=True)
                shutil.copy(p, os.path.join(d, "img", os.path.basename(p)))
                item["image"]["src"] = "img/" + os.path.basename(p)

    with open(os.path.join(d, "issue.json"), "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_full(issue, archive_url="../"))
    with open(os.path.join(slug_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(slug_dir))
    with open(os.path.join(a.out, "robots.txt"), "w") as f:
        f.write("User-agent: *\nDisallow: /\n")
    open(os.path.join(a.out, ".nojekyll"), "w").close()

    if not a.no_png or a.pdf or a.front:
        chrome = find_chrome()
        if not chrome:
            sys.exit("Chrome が見つかりません（CHROME_PATH で指定可。無い環境では pip install --user playwright && python3 -m playwright install chromium）。HTML のみ出力しました。")
        if not a.no_png:
            shot = os.path.join(d, "_shot.html")
            with open(shot, "w", encoding="utf-8") as f:
                f.write(render_full(issue, body_class="shot"))
            hgt = page_height(chrome, shot, 1280)
            chrome_run(chrome, [f"--window-size=1280,{hgt}", "--force-device-scale-factor=1.5",
                                "--virtual-time-budget=5000",
                                "--screenshot=" + os.path.abspath(os.path.join(d, "paper.png"))], shot)
            # LINE のプレビュー画像（1MB 以下が条件）
            chrome_run(chrome, [f"--window-size=1280,{hgt}", "--force-device-scale-factor=0.5",
                                "--virtual-time-budget=5000",
                                "--screenshot=" + os.path.abspath(os.path.join(d, "paper_s.png"))], shot)
            os.remove(shot)
        if a.front:
            front = os.path.join(d, "_front.html")
            with open(front, "w", encoding="utf-8") as f:
                f.write(render_front(issue))
            chrome_run(chrome, ["--window-size=1080,1440", "--screenshot=" + os.path.abspath(os.path.join(d, "front.png"))], front)
            os.remove(front)
        if a.pdf:
            chrome_run(chrome, ["--no-pdf-header-footer", "--print-to-pdf=" + os.path.abspath(os.path.join(d, "paper.pdf"))],
                       os.path.join(d, "index.html"))
    print(d)


if __name__ == "__main__":
    main()
