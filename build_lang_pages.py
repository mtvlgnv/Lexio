"""Prerender the homepage into per-language static files.

The UI language switcher (setUILang() in app.js) is entirely client-side —
it swaps [data-i18n] text via localStorage. That means the raw HTML search
engines crawl is always English, no matter how many languages the UI
dictionary covers. This script closes that gap by generating real,
independently-indexable pages at /es/, /fr/, /de/, etc: each is the
homepage with every [data-i18n]/[data-i18n-html] element already
substituted server-side, a localized <title>/meta description, a
translated FAQPage schema, and a full hreflang alternate network linking
every language version together (plus back to the English original).

Regenerate whenever static/index.html or the UI_T dictionary in
static/app.js changes — see deploy.sh, which runs this automatically.
Nothing here needs installing: lxml is already a transitive dependency
(via trafilatura) in .venv.
"""
import re
import sys
from pathlib import Path

import lxml.html
from lxml import etree

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
BASE_URL = "https://lexio.site"

LANGS = ["es", "fr", "de", "it", "pt", "nl", "ru", "zh", "ja", "ko"]
ALL_LANGS = ["en"] + LANGS

OG_LOCALE = {
    "en": "en_US", "es": "es_ES", "fr": "fr_FR", "de": "de_DE", "it": "it_IT",
    "pt": "pt_PT", "nl": "nl_NL", "ru": "ru_RU", "zh": "zh_CN", "ja": "ja_JP", "ko": "ko_KR",
}


def _load_ui_t():
    """Parse the UI_T dict straight out of app.js so this script can never
    drift out of sync with the actual translations shipped to the browser."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    m = re.search(r"const UI_T = \{(.*?)\n\};", js, re.DOTALL)
    if not m:
        raise RuntimeError("Could not find UI_T block in app.js")
    body = m.group(1)
    result = {}
    for line in body.splitlines():
        lm = re.match(r"\s*(\w+):\s*\{", line)
        if not lm:
            continue
        lang = lm.group(1)
        # Values are JS string literals — single-quoted normally, but
        # double-quoted wherever the source contains an apostrophe (avoids
        # escaping it). Match both styles; group(2) is None iff group(3) matched.
        d = {}
        for m2 in re.finditer(r"(\w+):(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")", line):
            key = m2.group(1)
            if m2.group(2) is not None:
                raw, quote = m2.group(2), "'"
            else:
                raw, quote = m2.group(3), '"'
            val = raw.replace(f"\\{quote}", quote).replace("\\\\", "\\")
            d[key] = val
        result[lang] = d
    return result


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def _set_inner_html(el, html_str: str):
    for child in list(el):
        el.remove(child)
    el.text = None
    frag = lxml.html.fragments_fromstring(html_str)
    if frag and isinstance(frag[0], str):
        el.text = frag[0]
        frag = frag[1:]
    for node in frag:
        el.append(node)


def _hreflang_block(lang: str) -> str:
    lines = ['  <!-- hreflang — full alternate-language network -->']
    for code in ALL_LANGS:
        href = f"{BASE_URL}/" if code == "en" else f"{BASE_URL}/{code}/"
        lines.append(f'  <link rel="alternate" hreflang="{code}" href="{href}">')
    lines.append(f'  <link rel="alternate" hreflang="x-default" href="{BASE_URL}/">')
    return "\n".join(lines)


def build_lang_page(lang: str, ui_t: dict, meta: dict):
    t = ui_t.get(lang, {})
    en = ui_t.get("en", {})
    missing = []

    tree = lxml.html.fromstring((STATIC / "index.html").read_text(encoding="utf-8"))

    for el in tree.xpath("//*[@data-i18n]"):
        key = el.get("data-i18n")
        val = t.get(key)
        if val is None:
            missing.append(key)
            val = en.get(key, "")
        el.text = val

    for el in tree.xpath("//*[@data-i18n-html]"):
        key = el.get("data-i18n-html")
        val = t.get(key)
        if val is None:
            missing.append(key)
            val = en.get(key, "")
        _set_inner_html(el, val)

    tree.set("lang", lang)

    head = tree.xpath("//head")[0]
    m = meta[lang]
    title_el = head.xpath(".//title")[0]
    title_el.text = m["title"]
    for xp in [
        './/meta[@name="description"]',
        './/meta[@property="og:title"]',
        './/meta[@property="og:description"]',
        './/meta[@name="twitter:title"]',
        './/meta[@name="twitter:description"]',
    ]:
        els = head.xpath(xp)
        if not els:
            continue
        el = els[0]
        if "title" in (el.get("property") or el.get("name") or ""):
            el.set("content", m["title"])
        else:
            el.set("content", m["description"])

    og_url = head.xpath('.//meta[@property="og:url"]')
    if og_url:
        og_url[0].set("content", f"{BASE_URL}/{lang}/")
    og_locale = head.xpath('.//meta[@property="og:locale"]')
    if og_locale:
        og_locale[0].set("content", OG_LOCALE.get(lang, "en_US"))

    canonical = head.xpath('.//link[@rel="canonical"]')
    if canonical:
        canonical[0].set("href", f"{BASE_URL}/{lang}/")

    # Replace hreflang <link> block (raw string swap — simplest given lxml
    # doesn't preserve comment placement well for this kind of block edit)
    html_str = lxml.html.tostring(tree, encoding="unicode", doctype="<!DOCTYPE html>")
    html_str = re.sub(
        r'  <!-- hreflang.*?-->\n(?:  <link rel="alternate"[^\n]*\n)+',
        _hreflang_block(lang) + "\n",
        html_str,
        flags=re.DOTALL,
    )

    # Translated FAQPage JSON-LD (mirrors what's on the English page, just
    # with translated + HTML-stripped Q/A text and inLanguage set to this page).
    faq_items = []
    for i in range(1, 10):
        q = t.get(f"faq{i}Q") or en.get(f"faq{i}Q", "")
        a_raw = t.get(f"faq{i}A") or en.get(f"faq{i}A", "")
        faq_items.append(
            '      {\n'
            '        "@type": "Question",\n'
            f'        "name": {_json_str(q)},\n'
            '        "acceptedAnswer": {\n'
            '          "@type": "Answer",\n'
            f'          "text": {_json_str(_strip_html(a_raw))}\n'
            '        }\n'
            '      }'
        )
    new_faq_block = (
        '  <script type="application/ld+json">\n'
        '  {\n'
        '    "@context": "https://schema.org",\n'
        '    "@type": "FAQPage",\n'
        f'    "inLanguage": "{lang}",\n'
        '    "mainEntity": [\n' + ",\n".join(faq_items) + "\n    ]\n"
        "  }\n"
        "  </script>"
    )
    html_str = re.sub(
        r'  <script type="application/ld\+json">\s*\{\s*"@context": "https://schema\.org",\s*"@type": "FAQPage".*?</script>',
        new_faq_block,
        html_str,
        count=1,
        flags=re.DOTALL,
    )

    # Prime currentUILang before app.js runs, so trending-month / pro-price
    # / anything else dynamic renders in this page's language immediately
    # instead of waiting on a (possibly absent) localStorage preference.
    html_str = html_str.replace(
        '<script src="/app.js',
        f"<script>window.LEXIO_LANG='{lang}';</script>\n<script src=\"/app.js",
        1,
    )

    out_dir = STATIC / lang
    out_dir.mkdir(exist_ok=True)
    (out_dir / "index.html").write_text(html_str, encoding="utf-8")

    if missing:
        uniq = sorted(set(missing))
        print(f"  [{lang}] WARNING: {len(uniq)} key(s) fell back to English: {uniq}")
    return len(missing)


def _json_str(s: str) -> str:
    import json
    return json.dumps(s, ensure_ascii=False)


def update_english_hreflang():
    """The English original also needs the full alternate set, not just
    self + x-default, so crawlers landing there discover every language."""
    path = STATIC / "index.html"
    html_str = path.read_text(encoding="utf-8")
    new_str = re.sub(
        r'  <!-- hreflang.*?-->\n(?:  <link rel="alternate"[^\n]*\n)+',
        _hreflang_block("en") + "\n",
        html_str,
        flags=re.DOTALL,
    )
    if new_str != html_str:
        path.write_text(new_str, encoding="utf-8")
        print("Updated hreflang block on static/index.html")


def main():
    sys.path.insert(0, str(ROOT))
    from i18n_meta import META  # noqa

    ui_t = _load_ui_t()
    total_missing = 0
    for lang in LANGS:
        n = build_lang_page(lang, ui_t, META)
        total_missing += n
        print(f"Built static/{lang}/index.html" + (f" ({n} fallback keys)" if n else ""))

    update_english_hreflang()

    if total_missing:
        print(f"\n{total_missing} total fallback substitutions — check warnings above.")
    else:
        print(f"\nAll {len(LANGS)} language pages built cleanly, no fallbacks.")


if __name__ == "__main__":
    main()
