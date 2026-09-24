# -*- coding: utf-8 -*-
"""Flux unique chambres hébergement (tarif fixe) — JSON canonique, pas de second scrape XML."""
from __future__ import annotations

import json
import logging
import re
from xml.sax.saxutils import escape

from odoo import http
from odoo.http import request
from odoo.addons.coins_marocain.models.room_public_copy import public_room_description

_logger = logging.getLogger(__name__)

_HTML_TAG = re.compile(r"<[^>]+>")
_HEBERGEMENT_TYPES = frozenset({"riad", "villa", "apartment", "other"})
_EXCLUDED_PILLARS = frozenset({"evenements"})
_PUBLISH_URL = "https://www.facebook.com/marketplace/create/rental"
_SCHEMA_ID = "coins-marocain.chambres.v1"
_POSTE_MAROC_DIRECTORY = "https://www.codepostal.ma/search_mot.aspx?keyword=marrakech"
_WIKIPEDIA_BAB_DOUKKALA = "https://en.wikipedia.org/wiki/Bab_Doukkala"
# Porte de médina Bab Doukkala — Wikipedia 31.633944°N, 7.999000°W. Landmark de quartier, pas le riad.
_BAB_DOUKKALA_LANDMARK = {
    "latitude": 31.633944,
    "longitude": -7.999,
    "name": "Bab Doukkala (porte de médina)",
    "source": "wikipedia.bab_doukkala_gate",
    "source_url": _WIKIPEDIA_BAB_DOUKKALA,
    "cite": "31°38′2.2″N 7°59′56.4″W = 31.633944, -7.999000 (Wikipedia, Bab Doukkala city gate)",
    "note": "Landmark public du quartier — pas la porte du riad, GPS Odoo vide.",
}
_QUARTIER_RADIUS_KM = 5


def _strip_html(html):
    if not html:
        return ""
    text = _HTML_TAG.sub(" ", html)
    return re.sub(r"\s+", " ", text).strip()


def _public_description(html):
    text = _strip_html(html)
    if not text:
        return ""
    text = re.split(r"\bSource Airbnb\b", text, flags=re.I)[0]
    text = re.split(r"À compléter\s*:", text, flags=re.I)[0]
    return re.sub(r"\s+", " ", text).strip(" ·-\t")


def _site_base():
    return (
        request.env["ir.config_parameter"]
        .sudo()
        .get_param("coins_marocain.partenaire_base_url", "https://coinsmarocain.com")
        .rstrip("/")
    )


# Aliases SEO déjà servis sur coinsmarocain.com (nginx → API publique).
# Ne jamais exposer /web/image Odoo : robots Disallow /web + placeholder 256px.
_YSABELLA_SEO_PHOTOS = {
    27: "chambre-emilia-1",
    28: "chambre-emilia-2",
    29: "chambre-emilia-3",
    32: "chambre-emilia-tableau",
    33: "chambre-julia",
    35: "chambre-nael-1",
    36: "chambre-nael-2",
    37: "chambre-nael-3",
    38: "chambre-antonella",
    42: "chambre-nada-1",
    43: "chambre-nada-2",
    46: "suite-ysabella",
    50: "salon-the-marocain",
    51: "salon-poterie-coussins",
    52: "salle-a-manger",
    53: "patio-fontaine",
    54: "salon-banquettes",
    55: "salon-arche",
    56: "plaque-entree",
    57: "table-dressee-patio",
    58: "table-longue",
    59: "service-the",
    60: "the-zellige",
    61: "table-roses",
    62: "terrasse-table",
    63: "the-table",
    64: "patio-fontaine-dessus",
}


def _photo_url(photo):
    """JPEG public coinsmarocain.com — pas le placeholder /web/image IntelliX."""
    seo = _YSABELLA_SEO_PHOTOS.get(photo.id)
    if seo:
        return "%s/photos/riad-la-casa-ysabella-marrakech-%s.jpg" % (_site_base(), seo)
    return "%s/api/coins-marocain/photos/%s?w=1600" % (_site_base(), photo.id)


def _room_photo_urls(prop, room):
    Photo = request.env["coins.property.photo"].sudo()
    photos = Photo.search(
        [("property_id", "=", prop.id), ("room_id", "=", room.id)],
        order="sequence, id",
        limit=5,
    )
    if not photos:
        photos = Photo.search(
            [("property_id", "=", prop.id), ("room_id", "=", False)],
            order="sequence, id",
            limit=3,
        )
    return [_photo_url(p) for p in photos if p.image]


def _property_fiche_url(prop):
    slug = (prop.name or "").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    if "casa-ysabella" in slug or "ysabella" in slug:
        return "%s/lieux/riad-medina-marrakech-la-casa-ysabella#room-%s" % (
            _site_base(),
            "{room_id}",
        )
    if prop.portal_token:
        return "%s/partenaire/%s" % (_site_base(), prop.portal_token)
    return "%s/carte/stay.html" % _site_base()


def _eligible_hebergement_properties():
    Property = request.env["coins.property"].sudo()
    domain = [
        ("active", "=", True),
        ("property_type", "in", list(_HEBERGEMENT_TYPES)),
    ]
    props = Property.search(domain)
    out = request.env["coins.property"]
    for prop in props:
        if prop.map_pillar in _EXCLUDED_PILLARS:
            continue
        if prop.property_type == "pool_hammam":
            continue
        out |= prop
    return out


def _room_has_fixed_price(room):
    if "price_per_night" not in room._fields:
        return False
    return bool(room.price_per_night and room.price_per_night > 0)


def _real_coord(value):
    if value in (None, False, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == 0:
        return None
    return number


def _partner_zip(prop):
    partner = getattr(prop, "owner_id", False)
    if not partner:
        return ""
    return (partner.sudo().zip or "").strip()


def _address_for_property(prop, postal_codes):
    street = (getattr(prop, "street", None) or "").strip()
    city = (prop.city or "").strip()
    district = (prop.district or "").strip()
    if not (street or city or district):
        return None
    return {
        "addr1": street,
        "city": city,
        "region": district,
        "postal_code": postal_codes[0] if postal_codes else "",
        "country": "MA",
    }


def _attach_address(geo, prop):
    address = _address_for_property(prop, geo.get("postal_codes") or [])
    if address:
        geo["address"] = address
    return geo


def _geo_for_property(prop):
    """Localité optionnelle. Jamais de GPS de porte inventé. 0,0 ignoré."""
    lat = _real_coord(getattr(prop, "latitude", None))
    lng = _real_coord(getattr(prop, "longitude", None))
    zipcode = _partner_zip(prop)
    city = prop.city or ""
    district = prop.district or ""
    if lat is not None and lng is not None:
        geo = {
            "circle": {
                "latitude": lat,
                "longitude": lng,
                "radius": _QUARTIER_RADIUS_KM,
                "radius_unit": "km",
            },
            "country": "MA",
            "precision": "property_gps",
            "source": "odoo.coins.property",
        }
        if zipcode:
            geo["postal_codes"] = [zipcode]
        return _attach_address(geo, prop)
    if zipcode:
        geo = {
            "postal_codes": [zipcode],
            "country": "MA",
            "precision": "odoo_partner_zip",
            "source": "odoo.res.partner.zip",
        }
        return _attach_address(geo, prop)
    city_l = city.lower()
    district_l = district.lower().replace(" ", "")
    if "marrakech" in city_l and "doukala" in district_l:
        return _attach_address(
            {
                "postal_codes": ["40030"],
                "country": "MA",
                "precision": "quartier_landmark",
                "source": "poste_maroc.codepostal.ma",
                "source_url": _POSTE_MAROC_DIRECTORY,
                "cite": "MARRAKECH | BAB DOUKKALA | 40030 ; MARRAKECH | DERB NAKHLA | 40030",
                "note": "Adresse Odoo + rayon quartier 5 km + landmark Wikipedia Bab Doukkala. Pas la porte du riad.",
                "circle": {
                    "latitude": _BAB_DOUKKALA_LANDMARK["latitude"],
                    "longitude": _BAB_DOUKKALA_LANDMARK["longitude"],
                    "radius": _QUARTIER_RADIUS_KM,
                    "radius_unit": "km",
                    "landmark": _BAB_DOUKKALA_LANDMARK["name"],
                    "landmark_source": _BAB_DOUKKALA_LANDMARK["source"],
                    "landmark_url": _BAB_DOUKKALA_LANDMARK["source_url"],
                    "landmark_cite": _BAB_DOUKKALA_LANDMARK["cite"],
                    "landmark_note": _BAB_DOUKKALA_LANDMARK["note"],
                },
                "landmark": _BAB_DOUKKALA_LANDMARK,
            },
            prop,
        )
    if "marrakech" in city_l:
        return _attach_address(
            {
                "postal_codes": ["40000"],
                "country": "MA",
                "precision": "city_postal",
                "source": "poste_maroc.codepostal.ma",
                "source_url": _POSTE_MAROC_DIRECTORY,
                "cite": "40000 = code ville Marrakech (série officielle 40000)",
                "note": "Niveau ville / médina — pas la porte d’un riad.",
            },
            prop,
        )
    address = _address_for_property(prop, [])
    if address:
        return {
            "country": "MA",
            "precision": "odoo_address",
            "source": "odoo.coins.property",
            "address": address,
        }
    return None


def _canonical_item(prop, room):
    price = float(room.price_per_night)
    currency = prop.currency_id.name if prop.currency_id else "EUR"
    prop_desc = _public_description(prop.description or "")
    room_desc = public_room_description(_strip_html(room.description or ""))
    description_parts = [
        part
        for part in [
            room_desc,
            prop_desc,
            "Tarif fixe par nuit (%s %s)." % (price, currency),
            "Réservation via Coins Marocain — coinsmarocain.com",
        ]
        if part
    ]
    description = " ".join(description_parts)[:5000]
    fiche_template = _property_fiche_url(prop)
    fiche_url = fiche_template.replace("{room_id}", str(room.id))
    item = {
        "id": "cm-room-%s" % room.id,
        "title": "%s — %s" % (prop.name, room.name),
        "description": description,
        "price": price,
        "currency": currency,
        "availability": "in_stock",
        "link": fiche_url,
        "photos": _room_photo_urls(prop, room),
        "videos": [],
        "source": {
            "odoo_room_id": room.id,
            "odoo_property_id": prop.id,
            "property_name": prop.name,
            "room_name": room.name,
            "city": prop.city or "",
            "district": prop.district or "",
            "street": (getattr(prop, "street", None) or "").strip(),
            "sleeps": room.sleeps or 0,
            "property_type": prop.property_type,
        },
    }
    try:
        geo = _geo_for_property(prop)
    except Exception:
        _logger.exception("geo canonique indisponible pour property %s", prop.id)
        geo = None
    if geo:
        item["geo"] = geo
    return item


def _canonical_items():
    """Une seule lecture Odoo des chambres à tarif fixe."""
    rows = []
    Room = request.env["coins.property.room"].sudo()
    for prop in _eligible_hebergement_properties():
        rooms = Room.search([("property_id", "=", prop.id), ("active", "=", True)], order="sequence, id")
        for room in rooms:
            if not _room_has_fixed_price(room):
                continue
            rows.append(_canonical_item(prop, room))
    return rows


def _excludes():
    return {
        "privatisation": True,
        "evenements": True,
        "events_groups": True,
        "rooms_without_fixed_price": True,
    }


def _category_options():
    return {
        "policy": "lister, ne pas choisir — taxonomie ambiguë lodging vs vacation rental vs hotel",
        "google_product_category": [
            {
                "id": "1475",
                "path": "Business & Industrial > Hotel & Hospitality",
                "note": "Seul nœud GPC hospitality. Utilisé plus tôt sur le XML — pas un choix validé.",
            }
        ],
        "google_lodging_surfaces": [
            {
                "surface": "Google Hotel Center",
                "kinds": ["hotel", "hostel", "inn", "bed and breakfast", "guest house"],
                "spec": "https://support.google.com/hotelprices/answer/9970971",
            },
            {
                "surface": "Google Vacation Rentals",
                "kinds": ["apartment", "house", "villa", "vacation rental (other)"],
                "spec": "https://developers.google.com/hotels/vacation-rentals/dev-guide/onboarding",
            },
        ],
        "facebook_catalog": [
            {
                "catalog_vertical": "commerce",
                "spec": "https://www.facebook.com/business/help/120325381656392",
                "note": "FPC lodging / vacation rental à lister depuis la taxonomie Meta, sans ID inventé.",
            },
            {
                "catalog_vertical": "hotels",
                "spec": "https://developers.facebook.com/docs/marketing-api/hotel-ads/catalog/",
            },
        ],
    }


def _canonical_payload(items):
    return {
        "schema": _SCHEMA_ID,
        "ok": True,
        "source": "odoo.coins.property.room.price_per_night",
        "count": len(items),
        "excludes": _excludes(),
        "category_options": _category_options(),
        "items": items,
    }


def _item_to_marketplace_room(item):
    src = item.get("source") or {}
    return {
        "odoo_room_id": src.get("odoo_room_id"),
        "odoo_property_id": src.get("odoo_property_id"),
        "property_name": src.get("property_name"),
        "room_name": src.get("room_name"),
        "title": item["title"],
        "description": item["description"],
        "price": item["price"],
        "currency": item["currency"],
        "city": src.get("city") or "",
        "district": src.get("district") or "",
        "category": "Location de vacances",
        "photo_urls": item.get("photos") or [],
        "fiche_url": item["link"],
        "publish_url": _PUBLISH_URL,
        "sleeps": src.get("sleeps") or 0,
        "property_type": src.get("property_type"),
    }


def _gmc_xml_from_items(items):
    site = _site_base()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
        "  <channel>",
        "    <title>Coins Marocain — Chambres hébergement</title>",
        "    <link>%s</link>" % escape(site),
        "    <description>Chambres et suites hébergement avec tarif fixe par nuit (devise saisie partenaire, EUR pour Casa Ysabella). Catégorie GMC/Hotel/VR non choisie — voir /feeds/chambres.json category_options.</description>",
    ]
    for item in items:
        photos = item.get("photos") or []
        image = photos[0] if photos else ""
        price = "%.2f %s" % (item["price"], item["currency"])
        lines.extend(
            [
                "    <item>",
                "      <g:id>%s</g:id>" % escape(item["id"]),
                "      <g:title>%s</g:title>" % escape(item["title"][:150]),
                "      <g:description>%s</g:description>" % escape(item["description"][:5000]),
                "      <g:link>%s</g:link>" % escape(item["link"]),
                "      <g:image_link>%s</g:image_link>" % escape(image),
            ]
        )
        for extra in photos[1:10]:
            lines.append("      <g:additional_image_link>%s</g:additional_image_link>" % escape(extra))
        lines.extend(
            [
                "      <g:availability>in stock</g:availability>",
                "      <g:price>%s</g:price>" % escape(price),
                "      <g:brand>Coins Marocain</g:brand>",
                "      <g:condition>new</g:condition>",
                "      <g:identifier_exists>false</g:identifier_exists>",
                "    </item>",
            ]
        )
    lines.extend(["  </channel>", "</rss>"])
    return "\n".join(lines)


class CoinsMarocainMarketplaceFeed(http.Controller):
    @http.route(
        "/api/coins-marocain/feeds/chambres.json",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    def canonical_chambres_json(self, **kwargs):
        items = _canonical_items()
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "public, max-age=300"),
        ]
        return request.make_response(
            json.dumps(_canonical_payload(items), ensure_ascii=False),
            headers=headers,
        )

    @http.route(
        "/api/coins-marocain/marketplace/rooms",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        cors="*",
    )
    def marketplace_rooms_json(self, **kwargs):
        items = _canonical_items()
        payload = {
            "ok": True,
            "count": len(items),
            "rooms": [_item_to_marketplace_room(item) for item in items],
            "excludes": _excludes(),
            "derived_from": "/api/coins-marocain/feeds/chambres.json",
        }
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "public, max-age=300"),
        ]
        return request.make_response(json.dumps(payload, ensure_ascii=False), headers=headers)

    @http.route(
        "/api/coins-marocain/feeds/chambres-hebergement.xml",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def merchant_feed_xml(self, **kwargs):
        items = _canonical_items()
        headers = [
            ("Content-Type", "application/xml; charset=utf-8"),
            ("Cache-Control", "public, max-age=900"),
        ]
        return request.make_response(_gmc_xml_from_items(items), headers=headers)
