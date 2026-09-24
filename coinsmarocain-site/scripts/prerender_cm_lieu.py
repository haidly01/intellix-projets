#!/usr/bin/env python3
"""Prerender HTML serveur des fiches /lieux/<slug> (photos visibles sans JS)."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cm_photo_categories import (
    YSABELLA_HERO_MAIN_ID,
    YSABELLA_HERO_ROOM_ID,
    YSABELLA_HERO_TERRACE_ID,
    categories_for_photo,
    group_photos_by_category,
)
from cm_fiche_devises import (
    REF_CURRENCY,
    format_price_label,
    fx_selector_html,
    normalize_currency,
)
from cm_lieu_schema import script_tag
from cm_room_public_copy import public_room_description
from cm_lieu_seo import (
    gallery_h2_subtitle,
    gallery_h2_title,
    gallery_section_heading,
    page_h1,
    page_lede,
    public_slug,
    rooms_h2_title,
    seo_bundle,
)
from cm_ysabella_seo_media import seo_alt, seo_photo_url, seo_thumb_crop

ROOM_DESC_LIMIT = 168

WA = "212660159177"
STEPS = [
    ("Budget", "Fourchette honnête pour le projet — on calibre le lieu et les prestataires."),
    ("Type de lieu", "Riad médina, villa palmeraie ou domaine — selon le groupe et le format."),
    ("Menus", "Table marocaine, chef à domicile ou cocktail — selon le moment."),
    ("Divertissement", "Musique, spectacle, DJ — uniquement si ça sert la soirée."),
    ("Décoration", "Fleurs, lumière, scénographie — le juste nécessaire."),
    ("Hébergement", "Chambres sur place ou à proximité pour les invités."),
]


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def osm_embed_src(lieu: dict) -> str:
    """Carte OSM avec pin si lat/lng connus — pas un bbox vide de Marrakech."""
    lat = lieu.get("latitude") or lieu.get("lat")
    lng = lieu.get("longitude") or lieu.get("lng")
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return (
            "https://www.openstreetmap.org/export/embed.html"
            "?bbox=-8.15%2C31.48%2C-7.85%2C31.72&amp;layer=mapnik"
        )
    pad = 0.028
    bbox = "%s%%2C%s%%2C%s%%2C%s" % (
        round(lng_f - pad, 5),
        round(lat_f - pad, 5),
        round(lng_f + pad, 5),
        round(lat_f + pad, 5),
    )
    return (
        "https://www.openstreetmap.org/export/embed.html?bbox=%s&amp;layer=mapnik"
        "&amp;marker=%s%%2C%s" % (bbox, round(lat_f, 6), round(lng_f, 6))
    )


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def truncate_words(text: str, limit: int = ROOM_DESC_LIMIT) -> str:
    """Coupe à un mot entier vers 150–180 caractères."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    snippet = text[: limit + 1]
    cut = snippet.rfind(" ")
    if cut < int(limit * 0.55):
        cut = limit
    return snippet[:cut].rstrip(" ,.;:…") + "…"


def room_desc_markup(desc_full: str, room_id) -> str:
    """Texte complet + line-clamp CSS ; case à cocher = Lire plus sans JS."""
    tid = esc(room_id or "x")
    full = desc_full or ""
    if len(full) <= 150:
        return f'<p class="cm-fiche-room-desc">{esc(full)}</p>'
    return (
        f'<input type="checkbox" class="cm-fiche-room-toggle" id="cm-room-more-{tid}" '
        f'aria-hidden="true">'
        f'<p class="cm-fiche-room-desc" id="cm-room-desc-{tid}" '
        f'data-short="{esc(truncate_words(full))}">{esc(full)}</p>'
        f'<label class="cm-fiche-room-more" for="cm-room-more-{tid}" '
        f'aria-controls="cm-room-desc-{tid}">'
        f'<span class="cm-fiche-room-more-open">Lire plus</span>'
        f'<span class="cm-fiche-room-more-close">Lire moins</span>'
        f"</label>"
    )


def wa_url(text: str) -> str:
    from urllib.parse import quote

    return f"https://wa.me/{WA}?text={quote(text)}"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "CoinsLieuPrerender/1.0"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _photo_by_id(photos: list, pid: int):
    for p in photos:
        try:
            if int(p.get("id")) == int(pid):
                return p
        except (TypeError, ValueError):
            continue
    return None


def _room_photo(photos: list, room: dict, slug: str):
    rid = room.get("id")
    name = (room.get("nom") or room.get("name") or "").upper()
    token = name.split()[0] if name else ""
    for p in photos:
        if rid and p.get("room_id") and int(p.get("room_id") or 0) == int(rid):
            return p
    for p in photos:
        if token and token in (p.get("legende") or "").upper():
            return p
    for p in photos:
        if "chambres" in categories_for_photo(p, slug) and token and token in (p.get("legende") or "").upper():
            return p
    return None


def pick_hero_mosaic(photos: list, slug: str):
    """Photo principale, chambre, terrasse — Ysabella ciblée, sinon premier jeu disponible."""
    main = photos[0] if photos else {}
    room_ph = {}
    terrace = {}
    if slug == "la-casa-ysabella":
        main = _photo_by_id(photos, YSABELLA_HERO_MAIN_ID) or main
        room_ph = _photo_by_id(photos, YSABELLA_HERO_ROOM_ID) or {}
        terrace = _photo_by_id(photos, YSABELLA_HERO_TERRACE_ID) or {}
    if not room_ph:
        for p in photos:
            if p is main:
                continue
            if "chambres" in categories_for_photo(p, slug) or p.get("room_id"):
                room_ph = p
                break
    if not terrace:
        for p in photos:
            if p in (main, room_ph):
                continue
            codes = categories_for_photo(p, slug)
            if "aires_communes" in codes or "exterieur_piscine" in codes:
                terrace = p
                break
    if not terrace:
        for p in photos:
            if p not in (main, room_ph):
                terrace = p
                break
    return main, room_ph, terrace


def render_body(lieu: dict, *, proof: bool = False) -> str:
    name = lieu.get("name") or "Lieu"
    slug = lieu.get("slug") or ""
    photos = [p for p in (lieu.get("photos") or []) if p.get("url")]
    videos = [v for v in (lieu.get("videos") or []) if v.get("url")]
    rooms = lieu.get("rooms") or []
    for r in rooms:
        r["description"] = public_room_description(
            strip_html(r.get("description") or "")
        )
    amenities = lieu.get("amenities") or []
    reviews = [r for r in (lieu.get("reviews") or []) if (r.get("texte") or r.get("text"))]
    nearby = lieu.get("nearby") or []
    cats = lieu.get("categories") or []
    can_priv = bool(lieu.get("can_privatise"))
    price = float(lieu.get("price_from") or 0)
    currency_ref = normalize_currency(lieu.get("currency") or lieu.get("currency_ref") or REF_CURRENCY)
    hero, hero_room, hero_terrace = pick_hero_mosaic(photos, slug)
    place = " — ".join(
        x for x in [lieu.get("district"), lieu.get("city") or "Marrakech"] if x
    )
    narrative_txt = strip_html(lieu.get("narrative_html") or "")
    desc_src = lieu.get("description_html") or lieu.get("narrative_html") or ""
    desc_txt = strip_html(desc_src)
    # Évite le paragraphe dupliqué (narrative = description sur Ysabella).
    same_copy = bool(narrative_txt and desc_txt and narrative_txt[:160] == desc_txt[:160])
    lede = page_lede(lieu) or ("" if same_copy else narrative_txt[:220])
    h1 = page_h1(lieu)
    raw_desc = desc_src if desc_txt else (lieu.get("narrative_html") or "")
    if "<p" in (raw_desc or "").lower():
        desc = raw_desc
    else:
        paras = [p.strip() for p in re.split(r"\n\s*\n", strip_html(raw_desc)) if p.strip()]
        desc = "".join(f"<p>{esc(p)}</p>" for p in paras) or "<p>Description à venir.</p>"
    wa_res = wa_url(f"Bonjour Yasmine, je souhaite réserver {name}.")
    wa_dispo = wa_url(f"Bonjour Yasmine, je souhaite les disponibilités de {name}.")
    wa_priv = wa_url(
        f"Bonjour Yasmine, je souhaite privatiser {name} et organiser un événement. "
        "On peut enchaîner Budget → Type de lieu → Menus → Divertissement → Décoration → Hébergement."
    )

    badges = "".join(
        f'<span class="cm-fiche-badge">{esc(c.get("label") or c.get("code"))}</span>'
        for c in cats
    )
    img_tags = []
    for i, ph in enumerate(photos):
        src = seo_photo_url(ph, 720)
        full = seo_photo_url(ph, 1600)
        alt = seo_alt(ph, name)
        img_tags.append(
            f'<img src="{esc(src)}" data-full="{esc(full)}" alt="{esc(alt)}" title="{esc(alt)}" '
            f'width="104" height="104" loading="{"eager" if i == 0 else "lazy"}" decoding="async">'
        )
    def _img_src(ph, key="url"):
        w = 1600 if key in ("url_full", "full") else 720
        return seo_photo_url(ph, w) or ph.get("url_full") or ph.get(key) or ph.get("url") or ""

    more_n = max(0, len(photos) - len([x for x in (hero, hero_room, hero_terrace) if x.get("url")]))

    video_tile = ""
    if videos:
        v0 = videos[0]
        video_tile = (
            f'<button type="button" class="cm-fiche-hero-tile is-video" data-video="{esc(v0.get("url"))}" '
            f'aria-label="Lire la vidéo d’introduction">'
            f'<img src="{esc(_img_src(hero) or "/assets/img/hero.jpg")}" alt="">'
            f'<span class="cm-fiche-play" aria-hidden="true"></span>'
            f'<span class="cm-fiche-video-label">Vidéo d’intro · 0:30</span></button>'
        )
    else:
        video_tile = (
            '<div class="cm-fiche-hero-tile is-video-placeholder" role="img" '
            'aria-label="Vidéo d’introduction à venir">'
            '<span class="cm-fiche-play" aria-hidden="true"></span>'
            '<span class="cm-fiche-video-label">Vidéo d’intro — à venir</span>'
            '<p class="cm-fiche-video-hint">Pas encore de vidéo pour ce lieu. '
            "L’emplacement reste réservé, ce n’est pas une lecture.</p></div>"
        )

    room_tile = ""
    if hero_room.get("url"):
        room_tile = (
            f'<button type="button" class="cm-fiche-hero-tile" data-full="{esc(_img_src(hero_room))}">'
            f'<img src="{esc(seo_photo_url(hero_room, 720) or hero_room.get("url") or hero_room.get("url_thumb"))}" '
            f'alt="{esc(seo_alt(hero_room, "Chambre"))}"{crop_attr(hero_room)}>'
            "</button>"
        )
    terrace_tile = ""
    if hero_terrace.get("url"):
        terrace_tile = (
            f'<a class="cm-fiche-hero-tile is-more" href="#galerie">'
            f'<img src="{esc(seo_photo_url(hero_terrace, 720) or hero_terrace.get("url") or hero_terrace.get("url_thumb"))}" '
            f'alt="{esc(seo_alt(hero_terrace, "Terrasse"))}"{crop_attr(hero_terrace)}>'
            f'<span class="cm-fiche-more-badge">+{more_n} photos</span></a>'
        )

    stacked = f'<div class="cm-fiche-hero-stack">{room_tile}{terrace_tile}</div>'

    rooms_html = ""
    if rooms:
        cards = []
        for r in rooms:
            prix = float(r.get("price_per_night") or 0)
            room_cur = normalize_currency(r.get("currency") or currency_ref)
            price_l = format_price_label(prix, room_cur, kind="room") if prix else "Sur devis"
            price_attrs = (
                f' data-price-ref="{prix:.0f}" data-currency-ref="{esc(room_cur)}" data-price-kind="room"'
                if prix
                else ""
            )
            room_title = re.sub(r"\s+", " ", str(r.get("nom") or "")).strip()
            if room_title.isupper():
                room_title = room_title.title().replace("Chambre", "chambre").replace("Suite", "suite")
            rph = _room_photo(photos, r, slug)
            photo_html = ""
            if rph:
                photo_html = (
                    f'<div class="cm-fiche-room-photo">'
                    f'<img src="{esc(seo_photo_url(rph, 720))}" '
                    f'data-full="{esc(seo_photo_url(rph, 1600))}" alt="{esc(seo_alt(rph, room_title))}" '
                    f'width="480" height="480"{crop_attr(rph)}></div>'
                )
            else:
                photo_html = (
                    '<div class="cm-fiche-room-photo is-missing">'
                    "<p>Pas de photo clairement identifiable pour cette chambre.</p></div>"
                )
            desc_full = strip_html(r.get("description") or "")
            rid = r.get("id")
            article_attrs = ' class="cm-fiche-room"'
            if rid is not None and str(rid).isdigit():
                article_attrs = (
                    f' class="cm-fiche-room" id="room-{int(rid)}" '
                    f'data-cm-content-id="cm-room-{int(rid)}"'
                )
            cards.append(
                f"<article{article_attrs}>"
                f"{photo_html}"
                f"<h3>{esc(room_title)}</h3>"
                f'<p class="cm-fiche-room-price"{price_attrs}>{esc(price_l)}</p>'
                f'<p class="cm-fiche-room-meta">{int(r.get("sleeps") or 0)} pers.</p>'
                f"{room_desc_markup(desc_full, r.get('id'))}</article>"
            )
        rooms_html = (
            f'<section class="cm-fiche-section" id="chambres"><h2>{esc(rooms_h2_title(lieu))}</h2>'
            f'<div class="cm-fiche-rooms">{"".join(cards)}</div></section>'
        )
    elif amenities:
        rooms_html = (
            '<section class="cm-fiche-section" id="offres"><h2>Services &amp; offres</h2>'
            f'<p>{esc(", ".join(amenities))}</p></section>'
        )

    def amenity_icon(label: str) -> str:
        t = (label or "").lower()
        if "patio" in t or "jardin" in t:
            return "patio"
        if "terrasse" in t or "rooftop" in t or "toit" in t:
            return "terrasse"
        if "salon" in t or "manger" in t:
            return "salon"
        if "piscine" in t:
            return "piscine"
        if "hammam" in t or "spa" in t:
            return "spa"
        if "wifi" in t:
            return "wifi"
        return "lieu"

    offre = "".join(
        f'<li data-icon="{amenity_icon(a)}"><span class="cm-fiche-ico" aria-hidden="true"></span>{esc(a)}</li>'
        for a in amenities[:8]
    )
    offre_html = (
        f'<section class="cm-fiche-section" id="offre"><h2>Ce que le lieu offre</h2>'
        f'<ul class="cm-fiche-offre">{offre}</ul></section>'
        if amenities
        else ""
    )

    avis_html = ""
    if reviews:
        bits = "".join(
            f'<blockquote><p>{esc(r.get("texte") or r.get("text"))}</p>'
            f'<cite>{esc(r.get("auteur") or "Avis Google")}</cite></blockquote>'
            for r in reviews[:3]
        )
        avis_html = f'<section class="cm-fiche-section" id="avis"><h2>Ils y sont déjà venus</h2>{bits}</section>'

    lat = lieu.get("latitude") or lieu.get("lat")
    lng = lieu.get("longitude") or lieu.get("lng")
    maps_href = lieu.get("maps_url") or ""
    if not maps_href and lat and lng:
        maps_href = "https://maps.google.com/?q=%s,%s" % (lat, lng)
    map_title = "Emplacement de %s" % name if lat and lng else "Marrakech et environs (30 min)"
    map_html = (
        f'<section class="cm-fiche-section" id="carte"><h2>Sur la carte</h2>'
        f'<p>{esc(place)}.</p>'
        '<div class="cm-fiche-map">'
        f'<iframe title="{esc(map_title)}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
        f'src="{osm_embed_src(lieu)}"></iframe>'
        "</div>"
    )
    if maps_href:
        map_html += f'<p><a href="{esc(maps_href)}" target="_blank" rel="noopener">Ouvrir dans Maps</a></p>'
    else:
        map_html += "<p>L’adresse exacte se confirme avec Yasmine (hors carte publique).</p>"
    map_html += "</section>"

    near_html = ""
    if nearby:
        cards = []
        for n in nearby[:3]:
            photo = n.get("photo_url") or ""
            img = (
                f'<img src="{esc(photo)}" alt="{esc(n.get("name"))}" width="640" height="120" loading="eager" decoding="async">'
                if photo
                else ""
            )
            cards.append(
                f'<a class="cm-fiche-near" href="{esc(n.get("detail_url") or "/lieux/"+n.get("slug",""))}">'
                f'{img}<span>{esc(n.get("name"))}</span>'
                f'<small>{esc(n.get("district") or n.get("city") or "")}</small></a>'
            )
        near_html = (
            '<section class="cm-fiche-section" id="nearby"><h2>Autres lieux dans le même esprit</h2>'
            f'<div class="cm-fiche-nearby">{"".join(cards)}</div></section>'
        )

    priv_btn = ""
    priv_panel = ""
    if can_priv:
        steps = "".join(
            f'<li><strong>{i}. {esc(t)}</strong> — {esc(d)}</li>'
            for i, (t, d) in enumerate(STEPS, start=1)
        )
        priv_btn = (
            f'<button type="button" class="cm-fiche-btn ghost" id="cmFichePrivatiser" '
            f'data-wa="{esc(wa_priv)}">Privatiser le lieu &amp; organiser un événement</button>'
        )
        priv_panel = (
            '<aside class="cm-fiche-priv" id="cmFichePrivPanel" hidden>'
            "<h2>Privatiser le lieu</h2><ol>"
            f"{steps}</ol>"
            f'<a class="cm-fiche-btn primary" href="{esc(wa_priv)}" target="_blank" rel="noopener">'
            "Démarrer avec un conseiller</a></aside>"
        )

    price_label = format_price_label(price, currency_ref, kind="from") if price else "Tarif sur demande"
    price_from_attrs = (
        f' data-price-ref="{price:.0f}" data-currency-ref="{esc(currency_ref)}" data-price-kind="from"'
        if price
        else ""
    )
    fx_html = fx_selector_html(currency_ref)
    proof_note = (
        '<p class="cm-fiche-proof">Page de preuve (noindex) — catégorie Privatisation simulée, '
        "aucun lieu réel modifié.</p>"
        if proof
        else (
            '<p class="cm-fiche-newmark">Nouvelle fiche — code <strong>CM-YS-PRIVEE</strong> — hero 3 colonnes, 6 chambres. Si vous voyez Thème / Zone / Capacité, ce n’est pas cette page.</p>'
            if slug == "la-casa-ysabella"
            else '<p class="cm-fiche-newmark">Nouvelle fiche — galerie, chambres et réservation WhatsApp</p>'
        )
    )

    sections = group_photos_by_category(photos, slug)
    section_blocks = []
    for code, label, group in sections:
        bits = []
        for i, ph in enumerate(group):
            src = ph.get("url") or ph.get("url_thumb")
            full = ph.get("url_full") or src
            alt = seo_alt(ph, name)
            eager = "eager" if ("asrari" in (slug or "") or i < 8) else "lazy"
            bits.append(
                f'<span class="cm-fiche-seo-photo"><img src="{esc(seo_photo_url(ph, 720))}" data-full="{esc(seo_photo_url(ph, 1600))}" '
                f'alt="{esc(alt)}" title="{esc(alt)}" '
                f'width="104" height="104" loading="{eager}" decoding="async"{crop_attr(ph)}></span>'
            )
        heading = gallery_section_heading(code, lieu, label)
        section_blocks.append(
            f'<div class="cm-fiche-gal-section" id="galerie-{esc(code)}" data-theme="{esc(code)}">'
            f"<h3>{esc(heading)}</h3>"
            f'<div class="cm-fiche-seo-photos">{"".join(bits)}</div></div>'
        )
    gal_title = gallery_h2_title(lieu)
    gal_sub = gallery_h2_subtitle(lieu, len(photos))
    gallery_hidden = (
        '<section class="cm-fiche-section cm-fiche-gallery" id="galerie">'
        f"<h2>{esc(gal_title)}</h2>"
        f'<p class="cm-fiche-gallery-sub">{esc(gal_sub)}</p>'
        + ("".join(section_blocks) if section_blocks else f'<div class="cm-fiche-seo-photos">{"".join(img_tags)}</div>')
        + "</section>"
    )

    return f"""
<main class="cm-lieu cm-fiche" id="cmLieuRoot" data-prerendered="1" data-slug="{esc(slug)}" data-can-privatise="{1 if can_priv else 0}" data-currency-ref="{esc(currency_ref)}">
  {proof_note}
  <section class="cm-fiche-hero cm-fiche-hero--mosaic" aria-label="Galerie">
    <div class="cm-fiche-hero-main">
      <img src="{esc(seo_photo_url(hero, 1600) or hero.get("url_full") or hero.get("url") or "/assets/img/hero.jpg")}" alt="{esc(seo_alt(hero, name + " — patio et fontaine"))}" fetchpriority="high"{crop_attr(hero)}>
    </div>
    {video_tile}
    {stacked}
  </section>
  <div class="cm-fiche-layout">
    <div class="cm-fiche-main">
      <p class="cm-fiche-eyebrow">Coins Marocain · Marrakech</p>
      <h1>{esc(h1)}</h1>
      {f'<p class="cm-fiche-lede">{esc(lede)}</p>' if lede else ""}
      <div class="cm-fiche-badges">{badges}</div>
      <p class="cm-fiche-place">{esc(place)}</p>
      <div class="cm-fiche-desc">{desc}</div>
      {rooms_html}
      {offre_html}
      {avis_html}
      {map_html}
      {near_html}
      {priv_panel}
    </div>
    <aside class="cm-fiche-book" id="cmFicheBook">
      <p class="cm-fiche-price"{price_from_attrs}>{esc(price_label)}</p>
      {fx_html}
      <form class="cm-fiche-book-form" id="cmFicheBookForm" data-place="{esc(name)}" data-capacity="{int(lieu.get("capacity") or 22)}">
        <div class="cm-fiche-book-dates">
          <label>Arrivée
            <input type="date" id="cmBookIn" name="arrivee" autocomplete="off">
          </label>
          <label>Départ
            <input type="date" id="cmBookOut" name="depart" autocomplete="off">
          </label>
        </div>
        <label>Voyageurs
          <input type="number" id="cmBookGuests" name="voyageurs" min="1" max="{int(lieu.get("capacity") or 22)}" value="2">
        </label>
        <p class="cm-fiche-book-note" id="cmBookNote">Yasmine confirme les dates — pas de paiement en ligne.</p>
      </form>
      <a class="cm-fiche-btn primary" id="cmBookWaRes" href="{esc(wa_res)}" target="_blank" rel="noopener">Réserver via WhatsApp</a>
      <a class="cm-fiche-btn ghost" id="cmBookWaDispo" href="{esc(wa_dispo)}" target="_blank" rel="noopener">Demander disponibilité</a>
      {priv_btn}
      <p class="cm-fiche-hint">Les dates et le nombre de voyageurs partent dans le message WhatsApp.</p>
    </aside>
  </div>
  <div class="cm-fiche-book-mobile" id="cmFicheBookMobile">
    <span{price_from_attrs}>{esc(price_label)}</span>
    <a class="cm-fiche-btn primary" id="cmBookWaMobile" href="{esc(wa_res)}" target="_blank" rel="noopener">Réserver via WhatsApp</a>
  </div>
  {gallery_hidden}
</main>
"""


def page_shell(lieu: dict, body: str, *, noindex: bool = False) -> str:
    name = lieu.get("name") or "Lieu"
    seo = seo_bundle(lieu, proof=noindex)
    photo = ((lieu.get("photos") or [{}])[0].get("url_full") or (lieu.get("photos") or [{}])[0].get("url") or "/assets/img/og-default.jpg")
    if lieu.get("slug") == "la-casa-ysabella":
        patio = next((p for p in (lieu.get("photos") or []) if str(p.get("id")) == "53"), None)
        if patio:
            photo = seo_photo_url(patio, 1600) or patio.get("url_full") or patio.get("url") or photo
    if photo.startswith("/"):
        photo = "https://coinsmarocain.com" + photo
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <link rel="icon" href="/favicon.ico?v=cm150" sizes="any">
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/img/favicon-32.png?v=cm150">
  <link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png?v=cm150">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(seo["title"])}</title>
  <meta name="description" content="{esc(seo["description"])}">
  <meta name="robots" content="{esc(seo["robots"])}">
  <link rel="canonical" href="{esc(seo["canonical"])}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Coins Marocain">
  <meta property="og:title" content="{esc(seo["title"])}">
  <meta property="og:description" content="{esc(seo["description"])}">
  <meta property="og:image" content="{esc(photo)}">
  <meta property="og:url" content="{esc(seo["canonical"])}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Playfair+Display:wght@500;600&family=Jost:wght@300;400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/activites.css?v=cm150">
  <link rel="stylesheet" href="/assets/cm-chrome.css?v=cm148">
  <link rel="stylesheet" href="/assets/cookies.css?v=cm148">
  <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
  <link rel="stylesheet" href="/assets/lieu.css?v=cm172">
  {script_tag(lieu)}
</head>
<body class="cm-lieu-page" data-header="solid" data-wa-msg="Bonjour Yasmine, je découvre {esc(name)}.">
  <!-- CM-YS-PRIVEE -->
  <header class="site-header solid" id="siteHeader">
    <div class="wrap header-inner">
      <a class="brand" href="/">
        <img src="/assets/img/logo-emblem-white.png?v=cm99" alt="Coins Marocain" class="brand-logo logo-light">
        <img src="/assets/img/logo-emblem.png?v=cm99" alt="Coins Marocain" class="brand-logo logo-dark">
      </a>
      <div class="header-actions">
        <button class="burger" id="burger" aria-label="Ouvrir le menu"><span></span><span></span><span></span></button>
      </div>
    </div>
  </header>
  <nav class="menu-overlay" id="menuOverlay" aria-hidden="true">
    <button class="menu-close" id="menuClose" aria-label="Fermer le menu">&times;</button>
    <p class="m-eyebrow">Coins Marocain</p>
  </nav>
  {body}
  <footer class="site-footer">
    <div class="wrap footer-cols">
      <div>
        <div class="foot-brand"><img src="/assets/img/logo-emblem-white.png?v=cm99" alt="Coins Marocain" width="173" height="44" style="height:44px;width:auto"></div>
        <p class="foot-tag">Voyages &amp; expériences curatés au Maroc.</p>
      </div>
      <div>
        <h4>Explorer</h4>
        <a href="/carte">Carte</a>
        <a href="/villas-riads-marrakech">Villas &amp; Riads</a>
        <a href="/journee-piscine">Journée piscine</a>
        <a href="/activites">Expériences</a>
      </div>
      <div>
        <h4>Contact</h4>
        <a href="/contact">Nous contacter</a>
        <a href="mailto:info@coinsmarocain.com">info@coinsmarocain.com</a>
      </div>
    </div>
    <div class="wrap foot-bottom">
      <p>© 2026 Coins Marocain — propriété de Digital Doorway SARL</p>
    </div>
  </footer>
  <script src="/assets/nav.js?v=cm148" defer></script>
  <script src="/assets/cookies.js?v=cm177" defer></script>
  <script src="/assets/lieu.js?v=cm177" defer></script>
</body>
</html>
"""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--slug", default="la-casa-ysabella")
    p.add_argument("--api", default="https://coinsmarocain.com/coins/api/carte/lieu/")
    p.add_argument("--out", default="")
    p.add_argument("--proof-privatise", action="store_true")
    args = p.parse_args()
    if args.proof_privatise:
        data = fetch_json(args.api + args.slug)
        lieu = dict(data.get("lieu") or {})
        lieu["can_privatise"] = True
        lieu["categories"] = list(lieu.get("categories") or []) + [
            {"code": "privatisation", "label": "Privatisation"}
        ]
        lieu["category_codes"] = list(lieu.get("category_codes") or []) + ["privatisation"]
        # Simule une fuite API (rue + GPS) : le JSON-LD doit les retirer.
        lieu["street"] = "12 rue secrète — ne pas publier"
        lieu["lat"] = 31.6333
        lieu["lng"] = -7.9999
        lieu["slug"] = "preuve-privatisation"
        lieu["name"] = (lieu.get("name") or "Lieu") + " — preuve Privatisation"
        body = render_body(lieu, proof=True)
        html_out = page_shell(lieu, body, noindex=True)
        out = Path(args.out or "/var/www/standby/coinsmarocain.com/lieux/preuve-privatisation.html")
    else:
        data = fetch_json(args.api.rstrip("/") + "/" + args.slug)
        if not data.get("ok") or not data.get("lieu"):
            print("API lieu introuvable", file=sys.stderr)
            return 2
        lieu = data["lieu"]
        body = render_body(lieu)
        html_out = page_shell(lieu, body, noindex=False)
        out = Path(args.out or f"/var/www/standby/coinsmarocain.com/lieux/{public_slug(lieu)}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    n_img = html_out.count("/api/coins-marocain/photos/")
    print(json.dumps({"out": str(out), "bytes": len(html_out), "photo_urls": n_img, "can_privatise": bool((data.get("lieu") or {}).get("can_privatise")) if not args.proof_privatise else True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
