#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class T(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "header", "footer"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "header", "footer") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def wc(path: Path) -> int:
    p = T()
    p.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return len(" ".join(p.parts).split())


D_ACT = """
      <h2>Bon à savoir avant de réserver</h2>
      <p>Les horaires dépendent de la saison et de la chaleur : en été, on privilégie le matin tôt ou le sunset ; en hiver, les journées pleines sont plus confortables. Indiquez l'âge des participants, d'éventuelles contraintes de mobilité et votre hébergement — le transfert se calcule autrement depuis la médina, la palmeraie ou un domaine hors ville.</p>
      <p>Coins Marocain ne revend pas de circuits « ramassage ». Chaque expérience est privée ou en très petit comité, avec un prestataire identifié. Pour comparer les options autour de Marrakech, utilisez le <a href="/guide-marrakech">guide des escapades</a> ; pour voir les lieux en images, la <a href="/carte">carte en vidéo</a>. Devis et ajustements : <a href="/contact">contact</a> ou WhatsApp Yasmine.</p>
      <h2>Maillage avec votre séjour</h2>
      <p>Une activité se glisse souvent entre deux nuits en villa ou riad privatisé. Elle peut aussi ouvrir ou clôturer un <a href="/evenements">événement</a> (EVJF, retraite, anniversaire). L'important est le rythme : une seule sortie forte par jour suffit souvent, plutôt que d'empiler trois formules et de perdre le fil du voyage.</p>
"""

D_EVT = """
      <h2>Devis et délais</h2>
      <p>Pour un chiffrage utile, prévoyez dates flexibles ou une fenêtre de trois jours, un effectif réaliste (adultes / enfants), et le niveau d'intimité souhaité. Nous répondons en général sous 48 h avec une ou deux pistes de lieux — pas une liste longue à trier. Les adresses restent confidentielles jusqu'à l'échange qualifié.</p>
      <p>La privatisation change la donne : vous n'êtes pas un salon parmi d'autres. Hébergement des invités, traiteur, timing cérémonie ou agenda de retraite, transferts aéroport : Yasmine centralise. Parcourez la <a href="/carte">carte en vidéo</a> pour ressentir les lieux, puis <a href="/contact">demandez un devis</a>. Compléments utiles : <a href="/villas-riads-marrakech">villas &amp; riads</a> et le <a href="/blog/">blogue</a>.</p>
"""

D_CARTE = """
    <section id="seo-dense" class="wrap" style="max-width:720px;margin:0 auto 36px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">Comment utiliser cette carte</h2>
      <p>Filtrez par thème ou par zone, ouvrez un pin, regardez la vidéo. Si le lieu convient, demandez les disponibilités et un devis de privatisation — sans passer par une plateforme anonyme. Les adresses exactes ne sont communiquées qu'aux voyageurs engagés dans un projet sérieux.</p>
      <p>La carte couvre un rayon d'environ trente minutes autour de Marrakech : centre, palmeraie, Agafay et quelques adresses satellites. Pour les escapades plus lointaines (Essaouira, Merzouga, Ouzoud), voir le <a href="/guide-marrakech">guide des escapades</a>. Pour un événement, croisez avec le hub <a href="/evenements">événements</a> ; pour une nuitée seule, <a href="/villas-riads-marrakech">villas &amp; riads</a>.</p>
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.3rem">Pourquoi la vidéo d'abord</h2>
      <p>Photos catalogues et plans 3D peinent à rendre la lumière marocaine, l'échelle d'un patio ou le bruit de voisinage. Une courte vidéo tournée sur place réduit les mauvaises surprises. Ensuite seulement, on parle budget, capacité et calendrier — avec un humain, pas un formulaire de 40 champs.</p>
    </section>
"""

D_MAP_EN = """
    <section id="seo-dense" class="wrap" style="max-width:720px;margin:0 auto 36px;padding:0 22px;line-height:1.65;color:#262220">
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.4rem">How to use this map</h2>
      <p>Filter by theme or zone, open a pin, watch the video. If the place fits, ask for dates and a privatisation quote — without an anonymous marketplace. Exact addresses are shared only once a project is serious.</p>
      <p>Coverage is roughly a thirty-minute radius around Marrakech. For longer day trips, see the <a href="/en/guide-marrakech">day-trip guide</a>. For celebrations, open <a href="/en/events">events</a>; for stays, <a href="/en/villas-riads">villas &amp; riads</a>.</p>
      <h2 style="font-family:Cormorant Garamond,Cardo,Georgia,serif;font-size:1.3rem">Why video first</h2>
      <p>Catalogue photos rarely show Moroccan light, patio scale or neighbour noise. A short on-site film reduces surprises. Only then do we talk budget, capacity and calendar — with a human, not a 40-field form.</p>
    </section>
"""

D_EVT_EN = """
      <h2>Quotes and lead times</h2>
      <p>For a useful quote, share a date window, a realistic headcount and the privacy level you want. We usually reply within 48 hours with one or two venue options — not a long list. Addresses stay confidential until the exchange is qualified.</p>
      <p>Privatisation means you are not one ballroom among many. Guest stays, catering, ceremony or retreat agenda, airport transfers: one thread with Yasmine. Browse the <a href="/en/map">video map</a>, then <a href="/en/contact">request a quote</a>.</p>
"""

D_VILLAS_EN = """
      <h2>What privatised means here</h2>
      <p>You take the whole place for your group — not a wing of a hotel. That changes noise, breakfast, and how guests move between rooms and outdoor spaces. Videos on the map help you shortlist; we then check real capacity and calendar.</p>
      <p>Many stays pair with a half-day experience (Agafay, Ourika, medina at night) or a wellness slot. Start on the <a href="/en/map/stay">stay map</a> or write via <a href="/en/contact">contact</a>.</p>
"""


def put_before(path: Path, block: str, markers: list[str], already: str) -> bool:
    t = path.read_text(encoding="utf-8")
    if already in t:
        return False
    for m in markers:
        if m in t:
            path.write_text(t.replace(m, block + m, 1), encoding="utf-8")
            return True
    return False


def main() -> None:
    n = 0
    for p in (ROOT / "activites").glob("*.html"):
        if put_before(
            p,
            D_ACT,
            ['<div class="article-cta">', "<footer"],
            "Bon à savoir avant de réserver",
        ):
            n += 1
            print("+", p.name, wc(p))

    hub = ROOT / "activites.html"
    ht = hub.read_text(encoding="utf-8")
    if "Bon à savoir avant de réserver" not in ht:
        block = (
            '<section class="wrap" style="max-width:720px;margin:0 auto 24px;padding:0 22px;line-height:1.65">'
            + D_ACT
            + "</section>\n  "
        )
        hub.write_text(
            ht.replace('<section class="filters"', block + '<section class="filters"', 1),
            encoding="utf-8",
        )
        n += 1
        print("+ activites.html", wc(hub))

    for p in (ROOT / "evenements").glob("*.html"):
        if put_before(
            p,
            D_EVT,
            ['      </div>\n      <aside class="pillar-aside">', '<div class="pillar-span">', "<footer"],
            "Devis et délais",
        ):
            n += 1
            print("+", p.name, wc(p))

    for p in (ROOT / "carte").glob("*.html"):
        if p.name == "plein-air.html":
            continue
        if put_before(
            p,
            D_CARTE,
            ['  <section class="cm-carte-signup"', "  <footer", "<footer", "</main>"],
            'id="seo-dense"',
        ):
            n += 1
            print("+", p.name, wc(p))

    maps = list((ROOT / "en" / "map").glob("*.html")) + [ROOT / "en" / "map.html"]
    for p in maps:
        if not p.exists() or p.name == "outdoors.html":
            continue
        if put_before(
            p,
            D_MAP_EN,
            ['  <section class="cm-carte-signup"', "  <footer", "<footer", "</main>"],
            'id="seo-dense"',
        ):
            n += 1
            print("+", p, wc(p))

    for p in (ROOT / "en" / "events").glob("*.html"):
        if p.name == "index.html":
            continue
        if put_before(
            p,
            D_EVT_EN,
            ['      </div>\n      <aside class="pillar-aside">', '<div class="pillar-span">', "<footer"],
            "Quotes and lead times",
        ):
            n += 1
            print("+", p.name, wc(p))

    vp = ROOT / "en" / "villas-riads.html"
    if put_before(vp, D_VILLAS_EN, ["<footer"], "What privatised means here"):
        n += 1
        print("+ en villas", wc(vp))

    ct = ROOT / "contact.html"
    ctt = ct.read_text(encoding="utf-8")
    if 'id="seo-dense"' not in ctt:
        block = """
      <aside id="seo-dense" style="max-width:640px;margin:0 auto 32px;padding:0 4px;line-height:1.65;color:#262220">
        <h2 style="font-family:Cardo,Georgia,serif;font-size:1.35rem">Temps de réponse et suite</h2>
        <p>Les demandes complètes (dates, effectif, intention) sont traitées en priorité. WhatsApp reste le canal le plus rapide pour un aller-retour court ; le formulaire crée une trace suivie par l'équipe. Nous ne vendons pas de listing public : chaque proposition est calibrée.</p>
        <p>Avant d'écrire, vous pouvez déjà éliminer des options via la <a href="/carte">carte en vidéo</a>, le <a href="/guide-marrakech">guide escapades</a> ou les pages <a href="/evenements">événements</a>. Cela accélère le premier échange.</p>
      </aside>
"""
        ct.write_text(ctt.replace('<main class="ct-main">', '<main class="ct-main">\n' + block, 1), encoding="utf-8")
        n += 1
        print("+ contact", wc(ct))

    vfr = ROOT / "villas-riads-marrakech.html"
    if vfr.exists():
        vt = vfr.read_text(encoding="utf-8")
        if 'id="seo-dense"' not in vt:
            block = """
  <section id="seo-dense" class="wrap" style="max-width:720px;margin:24px auto;padding:0 22px;line-height:1.65;color:#262220">
    <h2 style="font-family:Cardo,Georgia,serif;font-size:1.45rem">Privatiser une villa ou un riad à Marrakech</h2>
    <p>La page regroupe les formats que nous proposons le plus souvent : riad intimiste en médina, villa palmeraie avec piscine, domaine pour un groupe élargi. L'enjeu n'est pas le nombre d'annonces, mais la capacité réelle à privatiser sans partager les espaces communs avec d'autres voyageurs.</p>
    <p>Regardez d'abord les vidéos sur la <a href="/carte/hebergement">carte hébergement</a>, puis demandez un devis avec dates et effectif. Les expériences (désert, Ourika, hammam) se calent ensuite sur le même fil. L'ancienne URL /forfaits redirige ici pour préserver le SEO.</p>
  </section>
"""
            vfr.write_text(vt.replace("<footer", block + "\n<footer", 1), encoding="utf-8")
            n += 1
            print("+ villas FR", wc(vfr))

    print("changed", n)
    thin = []
    for pat in [
        "activites.html",
        "activites/*.html",
        "evenements/*.html",
        "carte/*.html",
        "contact.html",
        "villas-riads-marrakech.html",
        "en/villas-riads.html",
        "en/events/*.html",
        "en/map/*.html",
        "en/map.html",
    ]:
        for p in ROOT.glob(pat):
            if p.name in ("plein-air.html", "outdoors.html"):
                continue
            w = wc(p)
            if w < 400:
                thin.append((w, str(p.relative_to(ROOT))))
    print("THIN", len(thin))
    for w, r in sorted(thin):
        print(f"{w:4d} {r}")


if __name__ == "__main__":
    main()
