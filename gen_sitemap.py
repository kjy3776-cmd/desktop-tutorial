# -*- coding: utf-8 -*-
"""
gen_sitemap.py — apps_data.js 기준으로 sitemap.xml 자동 생성
auto_collect.py / fix_android.py 가 수집 후 호출한다.
"""
import os
import json
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_JS  = os.path.join(BASE_DIR, "apps_data.js")
SITEMAP  = os.path.join(BASE_DIR, "sitemap.xml")
SITE_URL = "https://innerapp.com"   # ★ 실제 도메인으로 수정


def generate():
    raw = open(DATA_JS, encoding="utf-8").read()
    raw = raw.split("=", 1)[1].strip().rstrip(";").strip()
    apps = json.loads(raw)
    today = datetime.date.today().isoformat()
    cats = sorted(set(a["cat"] for a in apps))

    def url(loc, pri):
        return (f"  <url>\n    <loc>{loc}</loc>\n"
                f"    <lastmod>{today}</lastmod>\n"
                f"    <priority>{pri}</priority>\n  </url>")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             url(f"{SITE_URL}/", "1.0")]
    for c in cats:
        lines.append(url(f"{SITE_URL}/?cat={c}", "0.8"))
    for a in apps:
        lines.append(url(f"{SITE_URL}/?id={a['id']}", "0.6"))
    lines.append("</urlset>")

    with open(SITEMAP, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return 1 + len(cats) + len(apps)


if __name__ == "__main__":
    n = generate()
    print(f"✅ sitemap.xml 생성 완료 — {n}개 URL")
