#!/usr/bin/env python3
"""Wrap carte theme SEO in <main> + densify unique copy (layer2 duplicate_content)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Unique SEO bodies — disjoint vocabulary per theme (audit uses full <main> text)
SEO = {
    "carte/bien-etre.html": """    <main id="cm-seo-main">
    <details id="seo-dense" class="cm-seo-fold" open>
      <summary>En savoir plus — hammams, spas et rituels</summary>
      <div class="cm-seo-fold-body">
        <h2>Route bien-être : vapeur, gommage et cabines filmées</h2>
        <p>Ce filtre ne liste pas des chambres ni des restaurants. Il regroupe hammams traditionnels, spas de riad et villas avec salle de soins. Chaque pin montre le rituel (savon noir, gommage, masque argile) ou l’espace (tadelakt, hammam chauffé, table de massage) en vidéo courte — pas une grille tarifaire anonyme.</p>
        <h2>Quand réserver un créneau soin plutôt qu’un séjour</h2>
        <p>Après une journée Agafay poussiéreuse, le matin d’un EVJF calme, ou entre deux visites médina : on cherche un créneau mixte ou non-mixte, une durée de rituel et parfois une privatisation duo. Pour dormir sur place, passez au filtre <a href="/carte/hebergement">hébergement</a> ; pour un banquet, au filtre <a href="/carte/evenements">événements</a>.</p>
        <h2>Ce que Yasmine valide avant de proposer un soin</h2>
        <p>Accueil réel, hygiène visible, langue du thérapeute, durée du protocole et possibilité de privatiser la cabine. Adresses partenaires filmées : <a href="/lieux/dar-sacada">Dar Sacada</a>, <a href="/lieux/casa-alma">Casa Alma</a>. Médina et Guéliz pour les hammams à pied ; palmeraie pour les spas feutrés. Escapades : <a href="/guide-marrakech">guide</a>.</p>
      </div>
    </details>
    </main>
""",
    "carte/route-gourmande.html": """    <main id="cm-seo-main">
    <details id="seo-dense" class="cm-seo-fold">
      <summary>En savoir plus — tables et restaurants</summary>
      <div class="cm-seo-fold-body">
        <h2>Route gourmande : assiettes, rooftops et bruit de salle</h2>
        <p>Ici seuls les restaurants et tables d’exception comptent : menu dégustation, cuisine marocaine contemporaine, rooftop lanterné ou table d’hôtes. La vidéo sert à entendre le service, sentir l’éclairage du patio et le rythme de salle — pas seulement le plat photographié.</p>
        <h2>Privatiser une salle vs dîner à la carte</h2>
        <p>Groupe d’amis, dîner d’affaires, suite d’adresses sur plusieurs soirs : précisez effectif, contrainte sans alcool ou enfants, budget par personne. Pour un traiteur de mariage dans une villa, utilisez plutôt <a href="/carte/evenements">lieux événementiels</a> et le hub <a href="/evenements">événements</a> — ce n’est pas le même brief qu’une réservation de restaurant.</p>
        <h2>Médina, Guéliz, Hivernage, palmeraie</h2>
        <p>Médina pour l’immersion ; Guéliz / Hivernage pour un service plus international ; domaines en palmeraie pour les dîners longue table. Yasmine vérifie la disponibilité réelle auprès du partenaire ; les adresses restent confidentielles jusqu’à un projet engagé. Escapades côte ou Atlas : <a href="/guide-marrakech">guide des escapades</a>.</p>
      </div>
    </details>
    </main>
""",
    "en/map/wellness.html": """    <main id="cm-seo-main">
    <details id="seo-dense" class="cm-seo-fold">
      <summary>More about hammams, spas &amp; massage</summary>
      <div class="cm-seo-fold-body">
        <h2>Wellness trail: steam, scrub rituals, treatment rooms on film</h2>
        <p>This filter is only for hammams, riad spas and partner massage cabins — not bedrooms and not dinner tables. Pins open short clips of heated steam rooms, black-soap scrub stations, clay masks and therapist flow so you judge the ritual before booking a slot.</p>
        <h2>Book a treatment window, not a night</h2>
        <p>After dusty Agafay, for a quiet hen-party morning, or between medina walks: you need mixed or women-only hours, ritual length and sometimes a private duo cabin. For overnight beds use <a href="/en/map/stay">stay</a>; for banquet logistics use <a href="/en/map/events">event venues</a>.</p>
        <h2>What Yasmine checks before suggesting a spa</h2>
        <p>Real welcome, visible hygiene, therapist language, protocol duration and privatisation options — never an anonymous marketplace listing. Walkable hammams in the medina and Guéliz; quieter spas in the palmeraie. Longer day trips: <a href="/en/guide-marrakech">day-trip guide</a>.</p>
      </div>
    </details>
    </main>
""",
    "en/map/food.html": """    <main id="cm-seo-main">
    <details id="seo-dense" class="cm-seo-fold">
      <summary>More about restaurants &amp; tables</summary>
      <div class="cm-seo-fold-body">
        <h2>Food trail: tasting menus, rooftops, room tone on video</h2>
        <p>Only restaurants and exceptional tables appear here — contemporary Moroccan kitchens, lanterned patios, rooftop service, host tables. Clips show plating pace, ambient noise and true evening light, not a staged dish photo alone.</p>
        <h2>Room buyout versus à-la-carte dinner</h2>
        <p>Share headcount, no-alcohol or child constraints and a per-person budget. Multi-night restaurant hopping is fine; wedding catering inside a private villa is a different brief — switch to <a href="/en/map/events">event venues</a> and the <a href="/en/events">events</a> hub.</p>
        <h2>Medina, Guéliz, Hivernage, palmeraie dining</h2>
        <p>Medina for immersion; Guéliz / Hivernage for international service; palmeraie estates for long-table dinners. Yasmine confirms real availability; addresses stay confidential until the project is serious. Coast or Atlas ideas: <a href="/en/guide-marrakech">day-trip guide</a>.</p>
      </div>
    </details>
    </main>
""",
    "en/map/stay.html": """    <main id="cm-seo-main">
    <details id="seo-dense" class="cm-seo-fold">
      <summary>More about stays on the map</summary>
      <div class="cm-seo-fold-body">
        <h2>Overnight villas &amp; riads — beds first, on video</h2>
        <p>Use this filter when you need bedrooms for a night or a week: partner villas and riads, room-by-room or full-house. Watch daylight in suites, outdoor lounges and real pool scale before asking for dates and capacity. This is not a restaurant list and not an event permit desk.</p>
        <h2>What privatising a stay means</h2>
        <p>Often the whole property is yours — kitchen hours, pool, house staff — not a hotel corridor. Tell us headcount, children’s ages and preferred zone (medina, palmeraie, Ourika, Agafay). Editorial ideas: <a href="/en/villas-riads">villas &amp; riads</a>. If you need a banquet floor plan, open <a href="/en/map/events">event venues</a>.</p>
        <h2>Video before you lock nights</h2>
        <p>Neighbour noise, patio size, winter sun: a twenty-second field clip beats brochure stills. Budget and calendar come after Yasmine shortlists filmed options — addresses remain confidential until you engage.</p>
      </div>
    </details>
    </main>
""",
    "en/map/events.html": """    <main id="cm-seo-main">
    <details id="seo-dense" class="cm-seo-fold">
      <summary>More about event venues</summary>
      <div class="cm-seo-fold-body">
        <h2>Ceremony, cocktail and dancefloor venues — not hotel rooms</h2>
        <p>These pins are built for groups: wedding ceremony, cocktail hour, seated dinner, dancefloor or a privatised pool day. Films show guest flow, patio capacity and parking — logistics that a simple overnight riad may never support.</p>
        <h2>Quote for privatisation within 48 hours</h2>
        <p>Send date, headcount, occasion (intimate wedding, hen/stag, birthday, retreat, mastermind) and mood (medina, palmeraie, Agafay). Yasmine returns one to three filmed options plus a budget band and any permit notes. Guest bedrooms alone belong under <a href="/en/map/stay">stay</a>; programmes live on the <a href="/en/events">events</a> hub.</p>
        <h2>Why “events” ≠ “stay”</h2>
        <p>Partners here accept external vendors (catering, sound, décor) and privatisation rules. A cute overnight courtyard without banquet load-in is the wrong tool — pick the stay filter for sleep, this filter for the celebration machine.</p>
      </div>
    </details>
    </main>
""",
}


def replace_seo_block(html: str, new_block: str) -> str:
    # Remove existing main wrapper around seo if present
    html = re.sub(
        r"<main[^>]*id=[\"']cm-seo-main[\"'][^>]*>\s*",
        "",
        html,
        count=1,
        flags=re.I,
    )
    html = re.sub(r"\s*</main>\s*(?=\s*<section class=\"cm-carte-signup\"|\s*<section class=\"cm-carte-cta\"|\s*<footer)", "\n", html, count=1, flags=re.I)

    patterns = [
        r"<details[^>]*id=[\"']seo-dense[\"'][\s\S]*?</details>",
        r"<section[^>]*id=[\"']seo-dense[\"'][\s\S]*?</section>",
    ]
    for pat in patterns:
        if re.search(pat, html, re.I):
            return re.sub(pat, new_block.strip() + "\n", html, count=1, flags=re.I)
    raise SystemExit("seo-dense block not found")


def wrap_remaining(path: Path) -> bool:
    """For other carte pages: wrap existing seo-dense in <main> if missing."""
    html = path.read_text(encoding="utf-8")
    if 'id="cm-seo-main"' in html or "id='cm-seo-main'" in html:
        return False
    if 'id="seo-dense"' not in html:
        return False
    # skip experiences which already have a different main
    if re.search(r"<main\b", html, re.I) and "cm-plein-air-shell" in html:
        return False

    def repl(m: re.Match) -> str:
        return f'<main id="cm-seo-main">\n{m.group(0)}\n    </main>'

    new, n = re.subn(
        r"<details[^>]*id=[\"']seo-dense[\"'][\s\S]*?</details>",
        repl,
        html,
        count=1,
        flags=re.I,
    )
    if n == 0:
        new, n = re.subn(
            r"<section[^>]*id=[\"']seo-dense[\"'][\s\S]*?</section>",
            repl,
            html,
            count=1,
            flags=re.I,
        )
    if n:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> None:
    for rel, block in SEO.items():
        path = ROOT / rel
        html = path.read_text(encoding="utf-8")
        path.write_text(replace_seo_block(html, block), encoding="utf-8")
        print("rewrote", rel)

    for folder in (ROOT / "carte", ROOT / "en" / "map"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.html")):
            rel = str(path.relative_to(ROOT))
            if rel in SEO:
                continue
            if wrap_remaining(path):
                print("wrapped", rel)


if __name__ == "__main__":
    main()
