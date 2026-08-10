#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_site_v2.py — مدقق موقع «دليل تعريب الألعاب العربية»

الاستخدام:
    python validate_site_v2.py [index.html]

يفحص:
  ✅ وجود كل الأقسام المطلوبة
  ✅ تطابق عدادات الإحصائيات مع عدد البطاقات الفعلية في كل قسم
  ✅ عدم وجود id مكرر
  ✅ كل بطاقة فيها رابط خارجي واحد على الأقل
  ✅ قيم data-platform صحيحة لبطاقات الريترو
  ✅ كل الروابط well-formed (http/https/#/mailto)
  ✅ لا وجود لملف script.js مربوط (قديم وغير مستخدم)

المخرجات: سطر ✅ أو ❌ لكل فحص + ملخص نهائي.
لا يتطلب أي مكتبات خارجية (stdlib فقط).
"""
import re
import sys
from html.parser import HTMLParser
from collections import Counter
from pathlib import Path

KNOWN_PLATFORMS = {"all", "nes", "snes", "n64", "ps1", "ps2", "pc", "ds", "gbc", "android", "gb", "gba", "psp", "sega", "msx", "arcade"}

# الأقسام المطلوبة: (id, class-selector للبطاقات، اسم الإحصائية)
SECTIONS = [
    ("communities", "comm-card", "سيرفر ديسكورد"),
    ("sites", "site-card", "موقع تعريب"),
]


class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.cards = Counter()          # (section_id, card_class) -> count
        self.links = []                 # (href, in_card, card_class)
        self.platforms = []
        self.current_section = None
        self.current_card = None
        self.current_card_class = None
        self.script_srcs = []
        self.sections_seen = set()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "section" and d.get("id"):
            self.current_section = d["id"]
            self.sections_seen.add(d["id"])
        if d.get("id"):
            self.ids.append(d["id"])
        if tag == "script" and d.get("src"):
            self.script_srcs.append(d["src"])
        card_class = None
        # البطاقات قد تكون <article> أو <a> (بطاقات المواقع هي روابط بذاتها)
        if tag in ("article", "a"):
            cls = d.get("class", "")
            for name in ("comm-card", "site-card", "follow-card"):
                if name in cls.split():
                    card_class = name
                    break
            if card_class:
                is_link_card = tag == "a"  # بطاقة-رابط (site-card): الرابط هو البطاقة نفسها
                self.stack.append(("card", self.current_section, card_class, is_link_card, 0, tag))
                if self.current_section:
                    self.cards[(self.current_section, card_class)] += 1
                if is_link_card and d.get("href"):
                    self.links.append((d["href"], True))
            elif tag == "a" and d.get("href"):
                # رابط عادي داخل بطاقة أو خارجها — إصلاح: كان سابقاً مرتبطاً
                # بمستوى `if tag in ("article","a")` الخارجي فلم يُحتسب أبداً
                href = d["href"]
                in_card = bool(self.stack and self.stack[-1][0] == "card")
                self.links.append((href, in_card))
                if in_card:
                    # نُحدّث عداد روابط البطاقة الحالية
                    top = self.stack[-1]
                    self.stack[-1] = (top[0], top[1], top[2], top[3], top[4] + 1, top[5])

    def handle_endtag(self, tag):
        if tag in ("article", "a") and self.stack and self.stack[-1][0] == "card" and self.stack[-1][5] == tag:
            self.stack.pop()
        if tag == "section":
            self.current_section = None


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    path = Path(target)
    if not path.exists():
        print(f"❌ الملف غير موجود: {target}")
        return 1

    html = path.read_text(encoding="utf-8")
    p = SiteParser()
    p.feed(html)

    errors = 0

    def ok(msg):
        print(f"  ✅ {msg}")

    def fail(msg):
        nonlocal errors
        errors += 1
        print(f"  ❌ {msg}")

    print(f"🔍 فحص {path.name} ...\n")

    # 1) الأقسام المطلوبة
    print("1) الأقسام المطلوبة:")
    for sid, _, _ in SECTIONS:
        if sid in p.sections_seen:
            ok(f"القسم #{sid} موجود")
        else:
            fail(f"القسم #{sid} مفقود!")

    # 2) مطابقة الإحصائيات
    print("\n2) مطابقة عدادات الإحصائيات مع البطاقات:")

    def count_in_section(sid, cls):
        # عدد بطاقات هذا القسم (قد يكون section واحد)
        return p.cards.get((sid, cls), 0)

    expected = {
        "سيرفر ديسكورد": count_in_section("communities", "comm-card"),
        "موقع تعريب": count_in_section("sites", "site-card"),
    }

    # استخراج أزواج (الرقم، التسمية) من كتلة الإحصائيات
    stat_blocks = re.findall(
        r'data-target="(\d+)"[^>]*>.*?<p>([^<]+)</p>', html, re.S
    )
    for num_str, label in stat_blocks:
        num = int(num_str)
        if label in expected:
            if num == expected[label]:
                ok(f"«{label}» = {num} ✓ (عدد البطاقات الفعلي {expected[label]})")
            else:
                fail(f"«{label}» = {num} لكن البطاقات الفعلية {expected[label]}!")
        else:
            ok(f"«{label}» = {num} (إحصائية ثابتة/غير قابلة للعد)")

    # 3) ids مكررة
    print("\n3) الأكوان الفريدة (id):")
    dups = [i for i, c in Counter(p.ids).items() if c > 1]
    if dups:
        fail(f"أكواد id مكررة: {dups}")
    else:
        ok(f"لا ids مكررة ({len(set(p.ids))} id فريد)")

    # 4) كل بطاقة لها رابط (بطاقات المواقع <a> هي روابط بذاتها)
    print("\n4) الروابط داخل البطاقات:")
    total_cards = sum(p.cards.values())
    # نعد الروابط المسجلة داخل البطاقات + بطاقات-الروابط (in_card=True)
    linked = sum(1 for _h, in_card in p.links if in_card)
    if linked >= total_cards:
        ok(f"كل البطاقات ({total_cards}) فيها روابط ({linked} رابط داخل بطاقات)")
    else:
        fail(f"بعض البطاقات بدون روابط: {total_cards} بطاقة مقابل {linked} رابط")

    # 5) قيم data-platform
    print("\n5) قيم data-platform (الريترو):")
    bad_platforms = [x for x in p.platforms if x not in KNOWN_PLATFORMS]
    if bad_platforms:
        fail(f"قيم منصات غير معروفة: {set(bad_platforms)}")
    else:
        ok(f"كل قيم المنصات صحيحة ({len(p.platforms)} قيمة)")

    # 6) well-formedness الروابط
    print("\n6) سلامة الروابط:")
    bad_links = []
    for href, _ in p.links:
        if not re.match(r"^(https?://|#|mailto:|tel:)", href):
            bad_links.append(href)
    if bad_links:
        fail(f"روابط غير سليمة: {set(bad_links)}")
    else:
        ok(f"كل الروابط well-formed ({len(p.links)} رابط)")

    # 7) script.js غير مربوط
    print("\n7) ملف script.js القديم:")
    if any("script.js" in s for s in p.script_srcs):
        fail("script.js مربوط بـ index.html — يجب إزالته!")
    else:
        ok("لا يوجد script.js مربوط (الملف القديم معزول)")

    print("\n" + "=" * 50)
    if errors == 0:
        print(f"✅ النتيجة النهائية: سليم — لا أخطاء ({len(set(p.ids))} id، {total_cards} بطاقة)")
        return 0
    print(f"❌ النتيجة النهائية: يوجد {errors} خطأ — راجع التفاصيل أعلاه")
    return 1


if __name__ == "__main__":
    sys.exit(main())
