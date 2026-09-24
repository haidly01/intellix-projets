# -*- coding: utf-8 -*-
"""Générateur : transforme un plan IA validé en artefacts Odoo Website.

Pour chaque page du plan : crée (ou met à jour) un ``ir.ui.view`` QWeb + un
``website.page`` assemblé à partir des snippets natifs, publie la page, applique
le SEO, et gère les entrées de menu (``website.menu``).

Idempotent : on conserve un mapping ``slug → page_id`` sur le brief ; une
re-génération met à jour les pages existantes au lieu de les dupliquer.

Robuste : une page en échec n'interrompt pas la génération des autres (elle est
remontée dans ``warnings``).
"""
import json
import logging

from . import snippets

_logger = logging.getLogger(__name__)


def _page_arch(sections_html):
    """Enveloppe les sections dans la structure de page Website standard."""
    return (
        '<t t-call="website.layout">'
        '<div id="wrap" class="oe_structure">'
        f"{sections_html}"
        "</div>"
        "</t>"
    )


def _apply_seo(page, page_meta, warnings):
    try:
        vals = {}
        if page_meta.get("seo_title"):
            vals["website_meta_title"] = page_meta["seo_title"]
        if page_meta.get("seo_description"):
            vals["website_meta_description"] = page_meta["seo_description"]
        if vals:
            page.write(vals)
    except Exception:  # noqa: BLE001
        warnings.append(f"SEO non appliqué pour « {page_meta.get('title')} ».")


def _publish(page, warnings):
    try:
        page.write({"is_published": True})
    except Exception:  # noqa: BLE001
        try:
            page.website_published = True
        except Exception:  # noqa: BLE001
            warnings.append(f"Publication impossible pour « {page.name} ».")


def _upsert_page(env, website, page_meta, slug_map, palette, warnings, publish=False):
    """Crée ou met à jour une page. Renvoie l'enregistrement website.page.

    ``publish`` False (génération / prévisualisation, GRATUIT) : la page est
    créée/MAJ mais reste NON publiée (invisible pour le public). ``publish``
    True (action payante) : la page devient publique.
    """
    title = page_meta["title"]
    slug = page_meta.get("slug") or env["ir.http"]._slugify(title)
    sections_html = snippets.build_sections(page_meta.get("sections"), palette)

    page = None
    existing_id = slug_map.get(slug)
    if existing_id:
        candidate = env["website.page"].browse(existing_id)
        if candidate.exists():
            page = candidate

    if page:
        page.view_id.with_context(lang=None).write({"arch": _page_arch(sections_html)})
    else:
        result = website.with_context(website_id=website.id).new_page(
            name=title,
            add_menu=False,
            sections_arch=sections_html,
            page_values={"is_published": bool(publish)},
            page_title=title,
        )
        page = env["website.page"].browse(result["page_id"])

    if publish:
        _publish(page, warnings)
    _apply_seo(page, page_meta, warnings)
    slug_map[slug] = page.id
    return page


def _sync_menu(env, website, entries, warnings):
    """Crée/MAJ les entrées de menu pour les pages marquées in_menu."""
    top_menu = website.menu_id
    if not top_menu:
        warnings.append("Menu racine du site introuvable : menus non synchronisés.")
        return
    for index, (page, page_meta) in enumerate(entries):
        if not page_meta.get("in_menu"):
            continue
        try:
            menu = env["website.menu"].search(
                [("page_id", "=", page.id), ("website_id", "=", website.id)], limit=1
            )
            vals = {
                "name": page_meta["title"],
                "url": page.url,
                "page_id": page.id,
                "parent_id": top_menu.id,
                "website_id": website.id,
                "sequence": 10 + index,
            }
            if menu:
                menu.write(vals)
            else:
                env["website.menu"].create(vals)
        except Exception:  # noqa: BLE001
            warnings.append(f"Menu non créé pour « {page_meta['title']} ».")


def generate_site(env, plan, slug_map=None, set_homepage=True, publish=False):
    """Construit le site à partir du plan validé.

    :param plan: plan validé (cf. claude_site_builder.validate_plan).
    :param slug_map: mapping slug→page_id d'une génération précédente (idempotence).
    :param publish: si False (par défaut), les pages sont construites mais restent
        NON publiées (génération + prévisualisation GRATUITES) ; menu et page
        d'accueil ne sont PAS modifiés. La mise en ligne se fait via
        :func:`publish_site` (action payante).
    :returns: dict {pages:[{title,url,page_id,is_home}], warnings:[...],
               slug_map:{...}, homepage_url, ok:bool, message:str}
    """
    warnings = []
    slug_map = dict(slug_map or {})
    website = env["website"].get_current_website()
    if not website:
        return {
            "ok": False,
            "message": "Aucun site web (website) configuré sur cette base.",
            "pages": [],
            "warnings": warnings,
            "slug_map": slug_map,
        }

    palette = plan.get("palette") or {}
    pages = plan.get("pages") or []
    created = []
    for page_meta in pages:
        try:
            page = _upsert_page(
                env, website, page_meta, slug_map, palette, warnings, publish=publish
            )
            created.append((page, page_meta))
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Site builder : échec génération page")
            warnings.append(
                f"Page « {page_meta.get('title', '?')} » non générée : {exc}"
            )

    if not created:
        return {
            "ok": False,
            "message": "Aucune page n'a pu être générée.",
            "pages": [],
            "warnings": warnings,
            "slug_map": slug_map,
        }

    homepage_url = None
    home_entry = next((c for c in created if c[1].get("is_home")), created[0])
    homepage_url = home_entry[0].url

    # Menu + page d'accueil : uniquement à la mise en ligne (publish).
    if publish:
        _sync_menu(env, website, created, warnings)
        if set_homepage:
            try:
                website.homepage_url = homepage_url
            except Exception:  # noqa: BLE001
                warnings.append("Impossible de définir la page d'accueil du site.")

    pages_out = [
        {
            "title": meta["title"],
            "url": page.url,
            "page_id": page.id,
            "is_home": bool(meta.get("is_home")),
        }
        for page, meta in created
    ]
    return {
        "ok": True,
        "message": "%d page(s) générée(s)." % len(created),
        "pages": pages_out,
        "warnings": warnings,
        "slug_map": slug_map,
        "homepage_url": homepage_url,
    }


def publish_site(env, plan, slug_map=None, set_homepage=True):
    """Met EN LIGNE les pages déjà générées (action payante).

    Publie (is_published=True) les pages du ``slug_map``, synchronise le menu et
    définit la page d'accueil. Idempotent : re-publier ne crée pas de doublon.

    :returns: dict {ok, message, homepage_url, count, warnings}
    """
    warnings = []
    slug_map = dict(slug_map or {})
    website = env["website"].get_current_website()
    if not website:
        return {"ok": False, "message": "Aucun site web configuré.", "warnings": warnings}

    Page = env["website.page"]
    meta_by_slug = {}
    for page_meta in (plan or {}).get("pages") or []:
        slug = page_meta.get("slug") or env["ir.http"]._slugify(page_meta.get("title") or "")
        meta_by_slug[slug] = page_meta

    entries = []
    published = []
    for slug, page_id in slug_map.items():
        page = Page.browse(page_id)
        if not page.exists():
            continue
        _publish(page, warnings)
        published.append(page)
        entries.append((page, meta_by_slug.get(slug, {})))

    if not published:
        return {
            "ok": False,
            "message": "Aucune page à publier — générez le site d'abord.",
            "warnings": warnings,
        }

    _sync_menu(env, website, entries, warnings)

    home_entry = next((e for e in entries if e[1].get("is_home")), entries[0])
    homepage_url = home_entry[0].url
    if set_homepage:
        try:
            website.homepage_url = homepage_url
        except Exception:  # noqa: BLE001
            warnings.append("Impossible de définir la page d'accueil du site.")

    return {
        "ok": True,
        "message": "%d page(s) publiée(s) en ligne." % len(published),
        "homepage_url": homepage_url,
        "count": len(published),
        "warnings": warnings,
    }


def plan_preview(plan):
    """Renvoie un résumé texte du mapping plan→pages (diagnostic/dry-run)."""
    lines = []
    for page in plan.get("pages", []):
        types = ", ".join(s.get("type", "?") for s in page.get("sections", []))
        flags = []
        if page.get("is_home"):
            flags.append("home")
        if page.get("in_menu"):
            flags.append("menu")
        lines.append(
            f"- {page.get('title')} [/{page.get('slug')}]"
            f"{(' (' + ', '.join(flags) + ')') if flags else ''} : {types}"
        )
    return "\n".join(lines)


def dumps(value):
    return json.dumps(value, ensure_ascii=False)
