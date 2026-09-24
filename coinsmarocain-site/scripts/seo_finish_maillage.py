#!/usr/bin/env python3
"""SEO finish — maillage interne + URLs propres + densify contact + EN Also-read."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# href="/foo.html" → /foo ; href="index.html" → / ; keep query/hash
HTML_HREF_RE = re.compile(
    r'href=(["\'])((?:https?://coinsmarocain\.com)?/?(?:[\w./-]*)\.html)([^"\']*)\1',
    re.I,
)


def clean_html_href(match: re.Match) -> str:
    q = match.group(1)
    path = match.group(2)
    rest = match.group(3) or ""
    # strip domain if present
    path = re.sub(r"^https?://coinsmarocain\.com", "", path, flags=re.I)
    if path in ("index.html", "/index.html"):
        path = "/"
    elif path.endswith(".html"):
        path = path[: -len(".html")]
        if not path.startswith("/"):
            path = "/" + path
        if path.endswith("/index"):
            path = path[: -len("/index")] or "/"
    return f"href={q}{path}{rest}{q}"


def rewrite_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    new, n = HTML_HREF_RE.subn(clean_html_href, text)
    # also relative index.html without leading slash already handled
    new2 = re.sub(
        r'href=(["\'])index\.html([^"\']*)\1',
        lambda m: f"href={m.group(1)}/{m.group(2)}{m.group(1)}",
        new,
    )
    if new2 != text:
        path.write_text(new2, encoding="utf-8")
        return 1
    return 0


def patch_blog_related() -> int:
    """Deepen blog related-links toward event pillars + guide."""
    patches = {
        "feter-anniversaire-marrakech-riad-privatise.html": (
            '<li><a href="/evenements">Anniversaires &amp; célébrations à Marrakech</a></li>',
            '<li><a href="/evenements/anniversaires">Anniversaires &amp; célébrations à Marrakech</a></li>\n'
            '        <li><a href="/guide-marrakech">Guide escapades autour de Marrakech</a></li>',
        ),
        "team-building-marrakech-riad-privatise.html": (
            '<li><a href="/evenements">Team building &amp; retraites</a></li>',
            '<li><a href="/evenements/team-building-retraites">Team building &amp; retraites</a></li>\n'
            '        <li><a href="/guide-marrakech/imlil">Escapade Imlil (Atlas)</a></li>',
        ),
        "retraite-dirigeants-mastermind-marrakech.html": (
            '<li><a href="/evenements">Retraites &amp; mastermind</a></li>',
            '<li><a href="/evenements/team-building-retraites">Retraites &amp; team building</a></li>\n'
            '        <li><a href="/guide-marrakech">Guide escapades</a></li>',
        ),
        "mariage-intime-ou-grand-mariage.html": (
            '<li><a href="/evenements">Mariages à Marrakech</a></li>',
            '<li><a href="/evenements/mariages">Mariages à Marrakech</a></li>\n'
            '        <li><a href="/villas-riads-marrakech">Villas &amp; riads</a></li>',
        ),
        "tendances-mariage-2026-2027.html": (
            '<li><a href="/evenements">Mariages à Marrakech</a></li>',
            '<li><a href="/evenements/mariages">Mariages à Marrakech</a></li>\n'
            '        <li><a href="/guide-marrakech/souks-marrakech">Souks &amp; artisanat</a></li>',
        ),
        "organiser-evenement-reussi-checklist.html": (
            '<li><a href="/evenements">Organiser un événement à Marrakech</a></li>',
            '<li><a href="/evenements">Hub événements</a></li>\n'
            '        <li><a href="/evenements/galas-levees-de-fonds">Galas &amp; levées de fonds</a></li>\n'
            '        <li><a href="/contact">Nous contacter</a></li>',
        ),
        "marrakech-authentique-activites-locales.html": (
            '<li><a href="/activites">Activités à Marrakech</a></li>',
            '<li><a href="/activites">Activités à Marrakech</a></li>\n'
            '        <li><a href="/guide-marrakech">Guide escapades</a></li>\n'
            '        <li><a href="/carte">Marrakech en vidéo</a></li>',
        ),
        "marrakech-3-jours-itineraire.html": (
            '<li><a href="/activites">Activités à Marrakech</a></li>',
            '<li><a href="/activites">Activités à Marrakech</a></li>\n'
            '        <li><a href="/guide-marrakech">Guide escapades</a></li>\n'
            '        <li><a href="/activites/desert-agafay">Désert d\'Agafay</a></li>',
        ),
        "agafay-ou-ourika-comparatif.html": (
            '<li><a href="/activites.html">Voir toutes nos activités privées</a></li>',
            '<li><a href="/activites">Voir toutes nos activités privées</a></li>\n'
            '        <li><a href="/guide-marrakech">Guide escapades</a></li>',
        ),
    }
    n = 0
    for name, (old, new) in patches.items():
        path = ROOT / "blog" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if old in text and new.split("\n")[0] not in text.replace(old, ""):
            # avoid double-insert if already deepened
            if "/evenements/anniversaires" in text and name.startswith("feter"):
                continue
            if old in text:
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
                n += 1
        elif old in text:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            n += 1
    return n


def enrich_en_also_read() -> int:
    replacements = {
        "en/events/weddings.html": (
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/villas-riads">Villas &amp; Riads</a></li>'
            '<li><a href="/evenements/mariages">Version française</a></li></ul></div>',
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/blog/tendances-mariage-2026-2027">Wedding trends 2026–2027</a></li>'
            '<li><a href="/blog/mariage-intime-ou-grand-mariage">Intimate vs large wedding</a></li>'
            '<li><a href="/en/villas-riads">Villas &amp; Riads</a></li>'
            '<li><a href="/guide-marrakech">Marrakech day-trip guide</a></li>'
            '<li><a href="/evenements/mariages">Version française</a></li></ul></div>',
        ),
        "en/events/hen-stag.html": (
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/events/hen-stag-1001-nights">1001 Nights</a></li>'
            '<li><a href="/en/events/hen-stag-villa-pool">Villa pool</a></li>'
            '<li><a href="/evenements/evjf-evg">Version française</a></li></ul></div>',
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/events/hen-stag-1001-nights">1001 Nights</a></li>'
            '<li><a href="/en/events/hen-stag-villa-pool">Villa pool</a></li>'
            '<li><a href="/journee-piscine">Pool day</a></li>'
            '<li><a href="/guide-marrakech">Day-trip guide</a></li>'
            '<li><a href="/evenements/evjf-evg">Version française</a></li></ul></div>',
        ),
        "en/events/hen-stag-1001-nights.html": (
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/events/hen-stag">All hen &amp; stag</a></li>'
            '<li><a href="/evenements/evjf-1001-nuits">Version française</a></li></ul></div>',
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/events/hen-stag">All hen &amp; stag</a></li>'
            '<li><a href="/en/villas-riads">Villas &amp; Riads</a></li>'
            '<li><a href="/guide-marrakech/souks-marrakech">Souks of Marrakech</a></li>'
            '<li><a href="/evenements/evjf-1001-nuits">Version française</a></li></ul></div>',
        ),
        "en/events/hen-stag-villa-pool.html": (
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/events/hen-stag">All hen &amp; stag</a></li>'
            '<li><a href="/evenements/evjf-villa-piscine">Version française</a></li></ul></div>',
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/en/events/hen-stag">All hen &amp; stag</a></li>'
            '<li><a href="/journee-piscine">Pool day</a></li>'
            '<li><a href="/en/villas-riads">Villas &amp; Riads</a></li>'
            '<li><a href="/evenements/evjf-villa-piscine">Version française</a></li></ul></div>',
        ),
        "en/villas-riads.html": (
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/villas-riads-marrakech">French page /forfaits</a></li>'
            '<li><a href="/en/events/weddings">Weddings</a></li></ul></div>',
            '<div class="pillar-related"><h2>Also read</h2><ul>'
            '<li><a href="/villas-riads-marrakech">French page</a></li>'
            '<li><a href="/en/events/weddings">Weddings</a></li>'
            '<li><a href="/carte">Marrakech on video</a></li>'
            '<li><a href="/guide-marrakech">Day-trip guide</a></li>'
            '<li><a href="/contact">Contact</a></li></ul></div>',
        ),
    }
    n = 0
    for rel, (old, new) in replacements.items():
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if old in text:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            n += 1
        elif "Wedding trends 2026" in text or "Day-trip guide" in text:
            pass  # already enriched
        else:
            # try softer: if pillar-related exists but different, skip
            print(f"skip EN (pattern mismatch): {rel}")
    return n


def densify_contact() -> bool:
    path = ROOT / "contact.html"
    text = path.read_text(encoding="utf-8")
    marker = 'id="seo-extra-maillage"'
    if marker in text:
        return False
    block = """
      <aside id="seo-extra-maillage" style="max-width:640px;margin:0 auto 28px;padding:0 4px;line-height:1.65;color:#262220">
        <h2 style="font-family:Cardo,Georgia,serif;font-size:1.35rem">Préparer votre demande</h2>
        <p>Indiquez dates flexibles ou fermes, nombre d'adultes / enfants, et le fil rouge du séjour
        (villa privatisé, mariage, retraite, EVJF, escapade désert ou Atlas). Plus le contexte est clair,
        plus la première réponse de Yasmine est actionnable — souvent avec 1 à 2 pistes concrètes
        plutôt qu'un catalogue générique.</p>
        <p>Liens utiles avant d'écrire :
        <a href="/carte">Marrakech en vidéo</a> ·
        <a href="/villas-riads-marrakech">Villas &amp; riads</a> ·
        <a href="/evenements/mariages">Mariages</a> ·
        <a href="/evenements/team-building-retraites">Team building</a> ·
        <a href="/activites/desert-agafay">Agafay</a> ·
        <a href="/guide-marrakech">Guide escapades</a> ·
        <a href="/blog/">Blog</a>.</p>
      </aside>
"""
    needle = '<aside id="contact-seo"'
    if needle not in text:
        return False
    path.write_text(text.replace(needle, block + "\n    " + needle, 1), encoding="utf-8")
    return True


def enrich_fr_event_pillars() -> int:
    """Add guide + cross-pillar links where thin."""
    adds = {
        "evenements/anniversaires.html": (
            '<li><a href="/villas-riads-marrakech">Villas &amp; Riads</a></li></ul></div>',
            '<li><a href="/villas-riads-marrakech">Villas &amp; Riads</a></li>'
            '<li><a href="/guide-marrakech">Guide escapades</a></li>'
            '<li><a href="/journee-piscine">Journée piscine</a></li></ul></div>',
        ),
        "evenements/evjf-evg.html": (
            '<li><a href="/journee-piscine">Journée piscine</a></li></ul></div>',
            '<li><a href="/journee-piscine">Journée piscine</a></li>'
            '<li><a href="/guide-marrakech">Guide escapades</a></li>'
            '<li><a href="/villas-riads-marrakech">Villas &amp; riads</a></li></ul></div>',
        ),
        "evenements/galas-levees-de-fonds.html": (
            '<li><a href="/evenements">Hub événements</a></li></ul></div>',
            '<li><a href="/evenements">Hub événements</a></li>'
            '<li><a href="/villas-riads-marrakech">Villas &amp; riads</a></li>'
            '<li><a href="/contact">Contact / devis</a></li></ul></div>',
        ),
        "evenements/mariages.html": (
            '<li><a href="/villas-riads-marrakech">Villas &amp; Riads</a></li></ul></div>',
            '<li><a href="/villas-riads-marrakech">Villas &amp; Riads</a></li>'
            '<li><a href="/guide-marrakech">Guide escapades</a></li>'
            '<li><a href="/carte">Marrakech en vidéo</a></li></ul></div>',
        ),
    }
    n = 0
    for rel, (old, new) in adds.items():
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if old in text and "/guide-marrakech" not in text[text.find("pillar-related") : text.find("pillar-related") + 500]:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            n += 1
        elif old in text and "Guide escapades" not in text:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            n += 1
    return n


def main() -> None:
    cleaned = 0
    for path in ROOT.rglob("*.html"):
        if "/proof" in str(path) or "/proofs" in str(path) or "/node_modules" in str(path):
            continue
        cleaned += rewrite_file(path)
    blog_n = patch_blog_related()
    en_n = enrich_en_also_read()
    fr_n = enrich_fr_event_pillars()
    contact = densify_contact()
    print(
        f"OK clean_html_files={cleaned} blog_related={blog_n} "
        f"en_also={en_n} fr_pillars={fr_n} contact={contact}"
    )


if __name__ == "__main__":
    main()
