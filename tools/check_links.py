#!/usr/bin/env python3
"""
check_links.py
يفحص كل روابط البطاقات في index.html فعليًا (HTTP request حقيقي) ويطلع تقرير
بالروابط الميتة/المشبوهة، بدل ما تفتحها وحدة وحدة يدويًا.

الاستخدام:
    pip install requests --break-system-packages   # غير مطلوب — stdlib فقط
    python3 check_links.py index.html

المخرجات:
    - طباعة تقرير مباشر بالتيرمنال
    - ملف link_report.json فيه كل النتائج التفصيلية
    - ملف broken_links.json فيه الروابط الميتة/المشبوهة فقط (ليسهل تتبعها)
"""

import re
import sys
import json
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

CARD_DEFS = [
    ("article", "comm-card"),
    ("a", "site-card"),
    ("article", "site-card"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",  # نتجنب gzip ليبقى الفحص بسيطًا مع urllib
}
TIMEOUT = 12
# بعض المواقع القديمة بشهادات SSL منتهية/مشوهة — نفحصها عاديًا بدل اعتبارها ميتة
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def load(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_cards(html: str):
    """يرجع [(اسم البطاقة, نوع البطاقة, [روابطها])]
    يتحمل الكلاسات بأي ترتيب (class="reveal comm-card") والاقتباسات المفردة/المزدوجة."""
    results = []
    for tag, cls in CARD_DEFS:
        # class="..." حيث \b{cls}\b موجود بأي موضع داخل قيمة الكلاس
        blocks = re.findall(
            rf'<{tag}\b[^>]*class=["\'][^"\']*\b{cls}\b[^"\']*["\'][^>]*>.*?</{tag}>',
            html, re.S,
        )
        for b in blocks:
            h3 = re.search(r"<h3>([^<]+)</h3>", b)
            name = h3.group(1).strip() if h3 else "بدون عنوان"
            hrefs = re.findall(r'href=["\'](https?://[^"\']+)["\']', b)
            results.append((name, cls, hrefs))
    return results


def check_url(url: str):
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
            return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return None, str(e)


def main(path: str):
    html = load(path)
    cards = extract_cards(html)

    all_urls = []
    for name, cls, hrefs in cards:
        for url in hrefs:
            all_urls.append((name, cls, url))

    unique = sorted({u for _, _, u in all_urls})
    print(f"عدد البطاقات: {len(cards)} | عدد الروابط الكلي: {len(all_urls)} | روابط فريدة: {len(unique)}\n")

    # فحص متوازٍ
    results_by_url = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(check_url, u): u for u in unique}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                status, err = fut.result()
            except Exception as e:
                status, err = None, str(e)
            results_by_url[u] = (status, err)

    report = []
    dead = []
    suspicious = []
    for name, cls, url in all_urls:
        status, err = results_by_url[url]
        entry = {"name": name, "type": cls, "url": url, "status": status, "error": err}
        report.append(entry)
        if status is None or (isinstance(status, int) and status >= 400):
            dead.append(entry)
        elif "discord.gg" in url and status not in (200,):
            suspicious.append(entry)

    if dead:
        print(f"❌ روابط ميتة/فاشلة ({len(dead)}):")
        for e in dead:
            print(f"  - [{e['type']}] {e['name']}: {e['url']}  →  {e['status'] or e['error']}")
    else:
        print("✅ ما فيه روابط ميتة واضحة.")

    if suspicious:
        print(f"\n⚠️ روابط ديسكورد تحتاج تأكيد يدوي ({len(suspicious)}) — بعض دعوات ديسكورد ترجع حالة غريبة حتى لو شغالة، تأكد بفتحها يدويًا:")
        for e in suspicious:
            print(f"  - [{e['type']}] {e['name']}: {e['url']}  →  {e['status']}")

    with open("link_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open("broken_links.json", "w", encoding="utf-8") as f:
        json.dump({"dead": dead, "suspicious": suspicious}, f, ensure_ascii=False, indent=2)
    print("\n📄 التقرير التفصيلي: link_report.json | الروابط المعطلة: broken_links.json")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    main(target)
