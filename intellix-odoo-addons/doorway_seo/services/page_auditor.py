# -*- coding: utf-8 -*-
"""Audit on-page SEO d'une ``website.page``.

Analyse statique du contenu (arch QWeb de la vue) + des champs SEO natifs
d'Odoo, calcule des métriques, une liste d'anomalies et un score /100.

Robuste : ne lève jamais ; en cas d'échec de parsing, renvoie un audit dégradé.
Réutilise ``lxml`` (déjà fourni par Odoo) avec repli sur une analyse par regex.
"""
import logging
import re

_logger = logging.getLogger(__name__)

META_TITLE_MAX = 60
META_TITLE_MIN = 30
META_DESC_MAX = 155
META_DESC_MIN = 70
MIN_WORD_COUNT = 300

# Pondération du score (total = 100).
WEIGHTS = {
    "meta_title": 15,
    "meta_description": 15,
    "keywords": 8,
    "h1": 12,
    "headings": 8,
    "alt": 10,
    "words": 10,
    "internal_links": 6,
    "jsonld": 8,
    "og": 4,
    "keyword_usage": 4,
}


def _strip_text(html):
    """Texte visible approximatif : retire balises/scripts/expressions QWeb."""
    if not html:
        return ""
    text = re.sub(r"(?is)<script.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_with_lxml(arch):
    try:
        from lxml import html as lxml_html
    except Exception:  # noqa: BLE001
        return None
    try:
        return lxml_html.fromstring(arch)
    except Exception:  # noqa: BLE001
        return None


def _analyze_structure(arch):
    """Renvoie (h1_count, heading_order, img_total, img_with_alt, internal_links).

    ``heading_order`` est la liste des niveaux de titres rencontrés (ex: [1,2,2,3]).
    """
    h1_count = 0
    heading_order = []
    img_total = 0
    img_with_alt = 0
    internal_links = 0

    tree = _parse_with_lxml(arch)
    if tree is not None:
        try:
            for el in tree.iter():
                tag = (el.tag if isinstance(el.tag, str) else "") or ""
                tag = tag.lower()
                if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    level = int(tag[1])
                    heading_order.append(level)
                    if level == 1:
                        h1_count += 1
                elif tag == "img":
                    img_total += 1
                    alt = (el.get("alt") or "").strip()
                    if alt:
                        img_with_alt += 1
                elif tag == "a":
                    href = (el.get("href") or "").strip()
                    if href.startswith("/") and not href.startswith("//"):
                        internal_links += 1
            return h1_count, heading_order, img_total, img_with_alt, internal_links
        except Exception:  # noqa: BLE001
            _logger.debug("page_auditor: lxml iter a échoué, repli regex")

    # Repli regex si lxml indisponible / arch non parsable.
    for m in re.finditer(r"(?i)<h([1-6])\b", arch or ""):
        level = int(m.group(1))
        heading_order.append(level)
        if level == 1:
            h1_count += 1
    imgs = re.findall(r"(?is)<img\b[^>]*>", arch or "")
    img_total = len(imgs)
    img_with_alt = sum(1 for tag in imgs if re.search(r'(?i)\balt\s*=\s*["\'][^"\']+', tag))
    internal_links = len(re.findall(r'(?i)<a\b[^>]*href\s*=\s*["\']/(?!/)', arch or ""))
    return h1_count, heading_order, img_total, img_with_alt, internal_links


def _heading_hierarchy_issues(heading_order):
    """Détecte les sauts de niveau (ex: h1 → h3) dans l'ordre du document."""
    issues = []
    prev = None
    for level in heading_order:
        if prev is not None and level > prev + 1:
            issues.append("Saut de niveau de titre (h%d après h%d)." % (level, prev))
        prev = level
    return issues


def _keyword_stats(text, keyword):
    if not keyword:
        return 0, 0.0
    words = text.lower().split()
    total = len(words) or 1
    kw = keyword.strip().lower()
    if not kw:
        return 0, 0.0
    count = len(re.findall(re.escape(kw), text.lower()))
    density = round(100.0 * count * len(kw.split()) / total, 2)
    return count, density


def audit_page(page, target_keyword=""):
    """Audite une ``website.page`` et renvoie un dict métriques/issues/score."""
    try:
        arch = page.arch or ""
    except Exception:  # noqa: BLE001
        arch = ""
    meta_title = (page.website_meta_title or "").strip()
    meta_desc = (page.website_meta_description or "").strip()
    meta_keywords = (page.website_meta_keywords or "").strip()
    og_img = (page.website_meta_og_img or "").strip()

    text = _strip_text(arch)
    word_count = len(text.split())
    h1_count, heading_order, img_total, img_with_alt, internal_links = _analyze_structure(arch)
    alt_coverage = round(100.0 * img_with_alt / img_total, 1) if img_total else 100.0
    has_jsonld = bool(re.search(r'(?i)application/ld\+json', arch))
    has_og = bool(og_img) or bool(meta_title and meta_desc)
    kw_count, kw_density = _keyword_stats(text, target_keyword)

    issues = []
    score = 0

    # Meta title
    if not meta_title:
        issues.append("Meta title (titre SEO) absent.")
    elif len(meta_title) > META_TITLE_MAX:
        issues.append("Meta title trop long (%d > %d caractères)." % (len(meta_title), META_TITLE_MAX))
        score += WEIGHTS["meta_title"] // 2
    elif len(meta_title) < META_TITLE_MIN:
        issues.append("Meta title court (%d < %d caractères recommandés)." % (len(meta_title), META_TITLE_MIN))
        score += int(WEIGHTS["meta_title"] * 0.7)
    else:
        score += WEIGHTS["meta_title"]

    # Meta description
    if not meta_desc:
        issues.append("Meta description absente.")
    elif len(meta_desc) > META_DESC_MAX:
        issues.append("Meta description trop longue (%d > %d caractères)." % (len(meta_desc), META_DESC_MAX))
        score += WEIGHTS["meta_description"] // 2
    elif len(meta_desc) < META_DESC_MIN:
        issues.append("Meta description courte (%d < %d caractères recommandés)." % (len(meta_desc), META_DESC_MIN))
        score += int(WEIGHTS["meta_description"] * 0.7)
    else:
        score += WEIGHTS["meta_description"]

    # Keywords
    if meta_keywords:
        score += WEIGHTS["keywords"]
    else:
        issues.append("Mots-clés meta non renseignés.")

    # H1
    if h1_count == 1:
        score += WEIGHTS["h1"]
    elif h1_count == 0:
        issues.append("Aucun H1 sur la page.")
    else:
        issues.append("Plusieurs H1 (%d) : un seul est recommandé." % h1_count)
        score += WEIGHTS["h1"] // 2

    # Hiérarchie des titres
    hierarchy_issues = _heading_hierarchy_issues(heading_order)
    if not hierarchy_issues:
        score += WEIGHTS["headings"]
    else:
        issues.extend(hierarchy_issues)

    # Couverture des alt
    if img_total == 0:
        score += WEIGHTS["alt"]
    else:
        score += int(WEIGHTS["alt"] * alt_coverage / 100.0)
        if alt_coverage < 100.0:
            issues.append(
                "Attributs alt incomplets : %d/%d images (%.0f%%)."
                % (img_with_alt, img_total, alt_coverage)
            )

    # Nombre de mots
    if word_count >= MIN_WORD_COUNT:
        score += WEIGHTS["words"]
    else:
        ratio = word_count / float(MIN_WORD_COUNT)
        score += int(WEIGHTS["words"] * ratio)
        issues.append("Contenu court (%d mots, < %d recommandés)." % (word_count, MIN_WORD_COUNT))

    # Liens internes
    if internal_links >= 1:
        score += WEIGHTS["internal_links"]
    else:
        issues.append("Aucun lien interne détecté.")

    # JSON-LD
    if has_jsonld:
        score += WEIGHTS["jsonld"]
    else:
        issues.append("Pas de données structurées JSON-LD.")

    # Open Graph
    if has_og:
        score += WEIGHTS["og"]
    else:
        issues.append("Open Graph incomplet (image OG / meta manquantes).")

    # Usage du mot-clé cible
    if target_keyword:
        if 0.3 <= kw_density <= 3.5 and kw_count >= 1:
            score += WEIGHTS["keyword_usage"]
        elif kw_count >= 1:
            score += WEIGHTS["keyword_usage"] // 2
            issues.append(
                "Densité du mot-clé « %s » à surveiller (%.2f%%)." % (target_keyword, kw_density)
            )
        else:
            issues.append("Mot-clé cible « %s » absent du contenu." % target_keyword)
    else:
        # Pas de mot-clé cible : on neutralise ce critère (points offerts).
        score += WEIGHTS["keyword_usage"]

    score = max(0, min(100, int(round(score))))

    metrics = {
        "meta_title_len": len(meta_title),
        "meta_desc_len": len(meta_desc),
        "has_keywords": bool(meta_keywords),
        "h1_count": h1_count,
        "heading_levels": heading_order,
        "img_total": img_total,
        "img_with_alt": img_with_alt,
        "alt_coverage": alt_coverage,
        "word_count": word_count,
        "internal_links": internal_links,
        "has_jsonld": has_jsonld,
        "has_og": has_og,
        "keyword_count": kw_count,
        "keyword_density": kw_density,
    }
    return {
        "url": page.url or "",
        "name": page.name or page.url or "Page",
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "meta_keywords": meta_keywords,
        "score": score,
        "issues": issues,
        "metrics": metrics,
        "content_excerpt": text[:1500],
    }
