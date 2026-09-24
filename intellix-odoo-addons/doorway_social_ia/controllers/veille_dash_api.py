# -*- coding: utf-8 -*-
"""API Veille pour le tableau Réseaux sociaux — signaux Odoo réels, pas la démo SQLite."""

import json
import logging
import re
import unicodedata
from urllib.error import URLError
from urllib.request import Request, urlopen

from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons.doorway_veille_sociale.services.followup_log import (
    commission_report,
    followups_for_signal,
    log_followup,
    set_converti,
)
from odoo.addons.doorway_veille_sociale.services.lead_copy import (
    VERTICALS,
    generate_lead_copy,
    vertical_for_branche,
)
from odoo.addons.doorway_veille_sociale.services.media_exclude import is_media_source
from odoo.addons.doorway_veille_sociale.services.reddit_service import RedditService
from odoo.addons.doorway_veille_sociale.services.url_helpers import is_google_news_article
from odoo.addons.doorway_veille_sociale.services.url_resolver import VeilleUrlResolver

_logger = logging.getLogger(__name__)

NODE_UPSTREAM = "http://127.0.0.1:43147"

BRANCH_LABEL = {
    "soumission_entrepreneurs": "soumissionentrepreneurs.com",
    "soumission_toitures": "soumissiontoitures.com",
    "ici_thermopompe": "icithermopompe.com",
    "isolation_qc": "isolationqc.com",
    "portes_fenetres": "portesetfenetresqc.com",
    "maison_recherchee": "maisonrecherchee.com",
    "coins_quebec": "Coins Québec",
    "coins_marocain": "Coins Marocain",
    "coins_commerce": "Coins Commerce",
    "reno_immo_qc": "Réno / immo Québec",
    "associations": "Associations",
    "non_pertinent": "Non pertinent",
}

ROLE_BY_LOGIN = {
    "zakaria@agencedoorway.com": {
        "slug": "zakaria",
        "name": "Zakaria",
        "admin": True,
        "verticals": ["coins_marocain"],
        "branches": ["coins_marocain"],
    },
    "martin@agencedoorway.com": {
        "slug": "martin",
        "name": "Martin",
        "admin": True,
        "verticals": ["coins_quebec"],
        "branches": ["coins_quebec", "coins_commerce"],
    },
    "karine@agencedoorway.com": {
        "slug": "karine",
        "name": "Karine",
        "admin": True,
        "verticals": ["coins_marocain", "coins_quebec", "reno_immo_qc"],
        "branches": [],
    },
    "leiladaouadi@gmail.com": {
        "slug": "leila",
        "name": "Leila",
        "admin": False,
        "verticals": ["reno_immo_qc"],
        "branches": [
            "soumission_entrepreneurs",
            "soumission_toitures",
            "ici_thermopompe",
            "isolation_qc",
            "portes_fenetres",
            "maison_recherchee",
            "reno_immo_qc",
        ],
    },
}


def _fold(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def _blob(sig):
    return _fold(
        " \n ".join(
            filter(
                None,
                [
                    getattr(sig, "titre", "") or "",
                    getattr(sig, "texte", "") or "",
                    getattr(sig, "resume", "") or "",
                    getattr(sig, "auteur", "") or "",
                ],
            )
        )
    )


def _rx(text, pattern):
    return bool(re.search(pattern, text, re.IGNORECASE))


def _municipal(text):
    return _rx(
        text,
        r"\b(hotel de ville|appel d['’]?offres|ville de |municipalit|ecoles? "
        r"|stade olympique|arenas? |college |complexe aquatique|saaq|tgv)\b",
    )


def _tagged_branche(sig):
    raw = _fold(getattr(sig, "plateforme", "") or "")
    raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if raw in BRANCH_LABEL and raw not in (
        "google_alerts",
        "reddit",
        "linkedin",
        "facebook",
        "facebook_manuel",
        "instagram",
    ):
        return raw
    return ""


def infer_branche(sig):
    """Route le signal vers le site du portfolio — jamais Coins Québec par défaut."""
    t = _blob(sig)
    type_projet = _fold(getattr(sig, "type_projet", "") or "")
    tagged = _tagged_branche(sig)
    if not t and not type_projet and not tagged:
        return "non_pertinent"

    if (
        _rx(t, r"\b(disney|disneyland|walt disney)\b")
        or (_rx(t, r"\bdefense\b") and _rx(t, r"\b(9\s*g\$|9g\$|milliard|depenser)\b"))
        or _rx(t, r"\b(saaqclic|\bsaaq\b)\b")
        or _rx(t, r"\bun argument contre le tgv\b")
        or _rx(t, r"\bconseil pour gars chaud\b")
    ):
        return "non_pertinent"

    if _rx(t, r"\b(toiture|toits?|couvreur|couvreurs|bardeaux?|gouttieres?)\b"):
        return "soumission_toitures"

    if (
        _rx(t, r"\b(thermopompe|thermo-pompe|hvac|climatisation|camt|mazout)\b")
        or type_projet == "ecoenergy"
    ):
        return "ici_thermopompe"

    if _rx(t, r"\bisolat(ion|ions|er|eurs?)?\b"):
        return "isolation_qc"

    if _rx(t, r"\bportes?( et)? fenetres?\b") or _rx(t, r"\bfenetres? et portes?\b"):
        return "portes_fenetres"

    if _rx(
        t, r"\b(maison recherchee|courtier immobilier|\bmls\b|propriete a vendre)\b"
    ) and not _rx(t, r"\bmaison mere\b"):
        return "maison_recherchee"

    if _rx(t, r"\b(riad|marrakech|casablanca|ouarzazate|essaouira|\bfes\b|\bmaroc\b)\b"):
        return "coins_marocain"

    if (
        _rx(
            t,
            r"\b(tourisme regional|activites touristiques|activites rive-?(nord|sud)|"
            r"hebergement (insolite|touristique)|evenement corporatif|voyageurs? coins|"
            r"resto |restaurant |spa (qc|quebec|region|lanaudiere)|commer[cç]ant( local)?)\b",
        )
        and not _municipal(t)
        and not _rx(t, r"\b(soumission|renov|toiture|thermopompe|couvreur)\b")
    ):
        return "coins_quebec"

    if _rx(t, r"\bpiscines?\b") and _rx(
        t,
        r"\b(semi-?creusees?|creusees?|hors terre|installer|installation)\b",
    ):
        return "soumission_entrepreneurs"

    if _rx(
        t,
        r"\b(soumissionentrepreneurs|sites? de soumissions?|soumission renovation)\b",
    ) or (
        _rx(t, r"\b(renovation|renovations|renovateur|entrepreneurs? en renov)\b")
        and not _municipal(t)
    ):
        return "soumission_entrepreneurs"

    if _rx(t, r"\bcherche\b.{0,40}\b(entrepreneur|renovateur|soumission)\b") and not _municipal(
        t
    ):
        return "soumission_entrepreneurs"

    if tagged and tagged != "non_pertinent":
        return tagged

    if _rx(t, r"\b(osbl|organisme communautaire|fondation|chambre de commerce)\b") and _rx(
        t, r"\bassoc"
    ):
        return "associations"

    if _rx(t, r"\b(boutique|enseigne|retail)\b") and not _rx(t, r"\brenov"):
        return "coins_commerce"

    return "non_pertinent"


def _node_json(path, timeout=8):
    req = Request(NODE_UPSTREAM + path, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as err:
        _logger.info("node %s: %s", path, err)
        return None


def _score(sig):
    if sig.score_intention:
        return sig.score_intention
    return sig.score_final or 0


def _dashboard_open_url(sig, resolve_now=False):
    """Partie 1 : news.google.com/articles → resolver AVANT url_editeur."""
    if sig.url_resolue:
        return sig.url_resolue
    raw = (sig.url or "").strip()
    if is_google_news_article(raw) and resolve_now:
        try:
            resolved = VeilleUrlResolver(sig.env).resolve(sig)
        except Exception as err:  # noqa: BLE001
            _logger.info("open_url resolve failed signal=%s: %s", sig.id, err)
            resolved = ""
        if resolved:
            if resolved != raw:
                try:
                    sig.sudo().write({"url_resolue": resolved})
                except Exception:  # noqa: BLE001
                    pass
            return resolved
        return (sig.url_editeur or raw or "")
    if is_google_news_article(raw):
        return raw
    return sig.url_resolue or sig.url_editeur or raw or ""


def current_role():
    user = request.env.user
    login = (user.login or "").strip().lower()
    role = ROLE_BY_LOGIN.get(login)
    if role:
        return dict(role, login=login, mapped=True)
    return {
        "slug": "",
        "name": user.name or "",
        "admin": bool(user.has_group("base.group_system")),
        "verticals": [],
        "branches": [],
        "login": login,
        "mapped": False,
    }


def _reponse_recue(sig):
    """True if the counterpart wrote after our last outbound (or after we marked replied)."""
    msgs = sig.conversation_message_ids.sorted(key=lambda m: (m.posted_at or m.create_date, m.id))
    if not msgs:
        return False
    last_in = None
    last_out = None
    for msg in msgs:
        if msg.direction == "inbound":
            last_in = msg
        else:
            last_out = msg
    if not last_in:
        return False
    in_at = last_in.posted_at or last_in.create_date
    if last_out:
        out_at = last_out.posted_at or last_out.create_date
        if in_at and out_at:
            return in_at > out_at
    return (sig.statut in ("repondu", "accepte", "cree_odoo")) and msgs[-1].direction == "inbound"


def _reponse_recue_map(signals):
    result = {sig.id: False for sig in signals}
    if not signals:
        return result
    Msg = request.env["doorway.veille.conversation.message"]
    msgs = Msg.search([("signal_id", "in", signals.ids)], order="posted_at, id")
    last = {}
    last_in = {}
    last_out = {}
    for msg in msgs:
        last[msg.signal_id.id] = msg
        if msg.direction == "inbound":
            last_in[msg.signal_id.id] = msg
        else:
            last_out[msg.signal_id.id] = msg
    for sig in signals:
        inbound = last_in.get(sig.id)
        if not inbound:
            continue
        outbound = last_out.get(sig.id)
        in_at = inbound.posted_at or inbound.create_date
        if outbound:
            out_at = outbound.posted_at or outbound.create_date
            result[sig.id] = bool(in_at and out_at and in_at > out_at)
        else:
            tail = last.get(sig.id)
            result[sig.id] = sig.statut in ("repondu", "accepte", "cree_odoo") and tail and tail.direction == "inbound"
    return result


def serialize_signal(sig, detail=False, light=False, reponse_recue=None):
    media = is_media_source(sig)
    branche = infer_branche(sig)
    statut = sig.statut or "en_attente"
    if media or (branche == "non_pertinent" and statut == "en_attente"):
        statut = "ignore"
    open_url = _dashboard_open_url(sig, resolve_now=detail)
    if getattr(sig, "url_enrichie", None):
        open_url = sig.url_enrichie or open_url
    payload = {
        "id": sig.id,
        "source": sig.source or "autre",
        "plateforme": sig.plateforme or sig.source or "",
        "auteur": sig.auteur or "",
        "titre": sig.titre or "",
        "texte": sig.texte or "",
        "url": open_url,
        "url_source": sig.url or "",
        "url_enrichie": getattr(sig, "url_enrichie", None) or "",
        "url_editeur": sig.url_editeur or "",
        "categorie_lead": getattr(sig, "categorie_lead", None) or "",
        "reponse_publique": getattr(sig, "reponse_publique", None) or "",
        "message_prive": getattr(sig, "message_prive", None) or "",
        "canal_soumission": getattr(sig, "canal_soumission", None) or "",
        "soumis_par": getattr(sig, "canal_soumission", None) or (
            sig.auteur if (sig.source or "") == "facebook_manuel" else ""
        ),
        "vertical": vertical_for_branche(branche, sig.plateforme if (sig.source or "") == "facebook_manuel" else None),
        "followups": followups_for_signal(sig.id) if detail else {},
        "resume": sig.resume or "",
        "type_projet": sig.type_projet or "",
        "marche": sig.marche or "",
        "action_suggeree": sig.action_suggeree or "",
        "statut": statut,
        "score_final": sig.score_final or 0,
        "score_intention": sig.score_intention or 0,
        "score": _score(sig),
        "temperature": sig.temperature or "",
        "branche": branche,
        "branche_label": BRANCH_LABEL.get(branche, branche),
        "media_excluded": media,
        "date_detection": sig.date_detection.isoformat() if sig.date_detection else False,
    }
    pub = (payload["reponse_publique"] or "").strip()
    priv = (payload["message_prive"] or "").strip()
    payload["generation_ok"] = bool(pub and priv)
    if payload["generation_ok"]:
        payload["generation_error"] = None
    elif pub.startswith("[Génération échouée]") or priv.startswith("[Génération échouée]"):
        payload["generation_error"] = pub or priv
    else:
        payload["generation_error"] = (
            "Réponses vides — la génération n’a pas écrit de texte "
            "(catégorie : %s). Clique « Régénérer la réponse »."
            % (payload["categorie_lead"] or "à confirmer")
        )
    if reponse_recue is None and not light:
        reponse_recue = _reponse_recue(sig)
    payload["reponse_recue"] = bool(reponse_recue)
    if not light:
        payload["can_reply_api"] = bool(sig.can_reply_api)
        payload["reply_api_source"] = sig.reply_api_source or "none"
        payload["reply_channel_hint"] = sig.reply_channel_hint or ""
    else:
        payload["can_reply_api"] = sig.source in ("reddit", "facebook", "instagram")
        payload["reply_api_source"] = sig.source if sig.source in ("reddit", "facebook", "instagram") else "none"
        payload["reply_channel_hint"] = ""
    if detail:
        payload["conversation"] = [
            {
                "id": m.id,
                "direction": m.direction,
                "author_name": m.author_name or "",
                "body": m.body or "",
                "posted_at": m.posted_at.isoformat() if m.posted_at else False,
                "platform": m.platform or "",
            }
            for m in sig.conversation_message_ids.sorted("posted_at")
        ]
    return payload


def _json(payload, status=200):
    return request.make_json_response(payload, status=status)


def _body():
    raw = request.httprequest.get_data() or b"{}"
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _signal(sid):
    try:
        rec = request.env["doorway.veille.signal"].browse(int(sid))
    except (TypeError, ValueError):
        return None
    if not rec.exists():
        return None
    return rec


def backfill_empty_copy(limit=40):
    """Relance la génération sur les signaux ouverts encore vides."""
    from odoo.addons.doorway_veille_sociale.services.scoring_service import (
        VeilleScoringService,
    )
    from odoo.addons.doorway_veille_sociale.services.lead_copy import (
        apply_lead_copy_to_records,
    )

    Signal = request.env["doorway.veille.signal"].sudo()
    recs = Signal.search(
        [
            ("statut", "in", ("en_attente", "accepte", "repondu")),
            "|",
            ("reponse_publique", "=", False),
            ("reponse_publique", "=", ""),
        ],
        limit=limit,
        order="id desc",
    )
    if not recs:
        return _json({"ok": True, "updated": 0, "ids": []})
    scoring = VeilleScoringService(request.env)
    apply_lead_copy_to_records(scoring, recs, infer_branche)
    done = [r.id for r in recs if (r.reponse_publique or "").strip()]
    return _json({"ok": True, "updated": len(done), "ids": done, "tried": recs.ids})


def handle(path, method):
    """Intercepte /api/signals et /api/veille/* depuis le proxy iframe."""
    method = (method or "GET").upper()
    parts = [p for p in path.split("/") if p]

    if path.rstrip("/") == "/api/veille/status" and method == "GET":
        return status()

    if path.rstrip("/") == "/api/veille/whoami" and method == "GET":
        return whoami()

    if path.rstrip("/") == "/api/veille/commission" and method == "GET":
        return _json(commission_report())

    if path.rstrip("/") == "/api/veille/reply-alerts" and method == "GET":
        return reply_alerts()

    if path.rstrip("/") == "/api/veille/backfill-copy" and method == "POST":
        return backfill_empty_copy()

    if path.rstrip("/") == "/api/signals/facebook-manuel" and method == "POST":
        return submit_facebook_manuel()

    if path.rstrip("/") == "/api/signals" and method == "GET":
        return list_signals()

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "signals":
        sid = parts[2]
        if method == "GET":
            return get_signal(sid)
        return _json({"error": "méthode non supportée"}, status=405)

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "signals":
        sid, action = parts[2], parts[3]
        if action == "statut" and method == "POST":
            return set_statut(sid)
        if action == "reply" and method == "POST":
            return reply(sid)
        if action == "sync" and method == "POST":
            return sync_conversation(sid)
        if action == "followup" and method == "POST":
            return followup(sid)
        if action == "regenerate" and method == "POST":
            return regenerate(sid)
        if action == "categorie" and method == "POST":
            return set_categorie(sid)
        return _json({"error": "action inconnue"}, status=404)

    return None


def status():
    cfg = request.env["doorway.veille.config"].sudo().get_config()
    reddit_creds = RedditService(request.env).credentials_ok(cfg)
    Signal = request.env["doorway.veille.signal"]
    counts = {
        src: Signal.search_count([("source", "=", src)])
        for src in ("reddit", "google_alerts", "facebook", "facebook_manuel", "instagram", "autre")
    }
    sess = _node_json("/api/linkedin/session") or {}
    has_sess = any(
        (a.get("has_session") and a.get("has_li_at"))
        for a in (sess.get("accounts") or [])
    )
    sources = [
        {
            "id": "google_alerts",
            "label": "Google Alerts",
            "ok": bool(cfg.google_alerts_actif and cfg.google_alerts_email),
            "count": counts["google_alerts"],
            "hint": "Flux presse actif" if cfg.google_alerts_actif else "E-mail Google Alerts manquant",
        },
        {
            "id": "reddit",
            "label": "Reddit",
            "ok": bool(reddit_creds),
            "count": counts["reddit"],
            "hint": (
                "OAuth connecté — tu peux répondre en direct"
                if reddit_creds
                else "Les posts arrivent. Pour répondre en direct : Veille sociale → Connexions → Obtenir refresh token Reddit."
            ),
        },
        {
            "id": "meta",
            "label": "Facebook / Instagram",
            "ok": bool((cfg.meta_access_token or "").strip()),
            "count": counts["facebook"] + counts["instagram"],
            "hint": "Token Meta présent" if (cfg.meta_access_token or "").strip() else "Token Meta manquant",
        },
        {
            "id": "linkedin",
            "label": "LinkedIn",
            "ok": has_sess,
            "count": None,
            "hint": (
                "Session connectée — clique LinkedIn pour voir les conversations"
                if has_sess
                else "Exporte la session via l’extension IntelliX Session"
            ),
        },
    ]
    return _json(
        {
            "live": True,
            "demo": False,
            "sources": sources,
            "total": sum(counts.values()),
        }
    )


def list_signals():
    args = request.httprequest.args
    statut = (args.get("statut") or "").strip()
    source = (args.get("source") or "").strip()
    branche = (args.get("branche") or "").strip()
    branches = [b.strip() for b in (args.get("branches") or "").split(",") if b.strip()]
    try:
        limit = min(max(int(args.get("limit") or 80), 1), 200)
    except ValueError:
        limit = 80
    Signal = request.env["doorway.veille.signal"]
    domain = []
    if statut == "accepte":
        domain.append(("statut", "in", ["accepte", "cree_odoo", "repondu"]))
    elif statut and statut != "ignore":
        domain.append(("statut", "=", statut))
    if source and source != "linkedin":
        if source == "facebook":
            domain.append(("source", "in", ["facebook", "facebook_manuel"]))
        else:
            domain.append(("source", "=", source))
    all_recs = Signal.browse()
    if source != "linkedin":
        all_recs = Signal.search(domain, order="score_final desc, date_detection desc, id desc")
        drop = all_recs.filtered(
            lambda s: s.statut == "en_attente"
            and (infer_branche(s) == "non_pertinent" or is_media_source(s))
        )
        if drop:
            drop.with_context(mail_notrack=True, tracking_disable=True).write(
                {"statut": "ignore"}
            )
    rows = []
    recu_map = _reponse_recue_map(all_recs) if all_recs else {}
    if source != "linkedin":
        for sig in all_recs:
            item = serialize_signal(sig, light=True, reponse_recue=recu_map.get(sig.id))
            if item.get("media_excluded") and statut != "ignore":
                continue
            if branches and item["branche"] not in branches:
                continue
            if branche and not branches and item["branche"] != branche:
                continue
            if statut == "ignore" and item["statut"] != "ignore":
                continue
            if statut and statut != "ignore" and item["statut"] != statut and not (
                statut == "accepte" and item["statut"] in ("accepte", "cree_odoo", "repondu")
            ):
                continue
            rows.append(item)
    if source in ("", "linkedin"):
        li = _node_json("/api/linkedin/interactions", timeout=45) or {}
        for item in li.get("interactions") or []:
            if branches and item.get("branche") not in branches:
                continue
            if branche and not branches and item.get("branche") != branche:
                continue
            if statut == "accepte" and item.get("statut") not in (
                "accepte",
                "cree_odoo",
                "repondu",
            ):
                continue
            elif statut and statut != "accepte" and item.get("statut") != statut:
                continue
            rows.append(item)
    waiting = [r for r in rows if r["statut"] == "en_attente"]
    treated = [r for r in rows if r["statut"] in ("repondu", "accepte", "cree_odoo")]
    scores = [r["score"] for r in rows if r["score"]]
    page = rows[:limit]
    return _json(
        {
            "live": True,
            "signals": page,
            "kpis": {
                "a_trier": len(waiting),
                "traites_semaine": len(treated),
                "score_moyen": ("%.1f" % (sum(scores) / len(scores))) if scores else "0",
                "sources": len({r["source"] for r in rows}),
            },
            "truncated": len(rows) > limit,
            "total": len(rows),
        }
    )


def reply_alerts():
    Signal = request.env["doorway.veille.signal"]
    recs = Signal.search(
        [("statut", "in", ["repondu", "accepte", "cree_odoo", "en_attente"])],
        order="date_detection desc, id desc",
        limit=200,
    )
    recu_map = _reponse_recue_map(recs)
    alerts = []
    for sig in recs:
        if not recu_map.get(sig.id):
            continue
        item = serialize_signal(sig, light=True, reponse_recue=True)
        alerts.append(
            {
                "id": item["id"],
                "kind": "veille",
                "label": "Réponse reçue",
                "title": item.get("titre") or item.get("resume") or "Signal veille",
                "subtitle": " · ".join(
                    filter(None, [item.get("branche_label"), item.get("source")])
                ),
                "when": item.get("date_detection") or "",
                "preview": (item.get("texte") or item.get("resume") or "")[:180],
            }
        )
    return _json({"live": True, "alerts": alerts})


def get_signal(sid):
    if str(sid).startswith("li-"):
        li = _node_json("/api/linkedin/interactions", timeout=45) or {}
        for item in li.get("interactions") or []:
            if str(item.get("id")) == str(sid):
                return _json({"live": True, "signal": item})
        return _json({"error": "Signal introuvable."}, status=404)
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    try:
        sig.action_sync_conversation()
    except Exception as err:
        _logger.info("veille sync conversation signal=%s: %s", sid, err)
    return _json({"live": True, "signal": serialize_signal(sig, detail=True)})


def set_statut(sid):
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    statut = (_body().get("statut") or "").strip()
    try:
        if statut == "ignore":
            sig.action_ignorer()
        elif statut == "accepte":
            sig.action_accepter()
        elif statut == "repondu":
            sig.action_marquer_repondu()
        else:
            return _json({"error": "statut invalide"}, status=400)
    except UserError as err:
        return _json({"error": str(err)}, status=400)
    return _json({"ok": True, "signal": serialize_signal(sig)})


def reply(sid):
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    texte = (_body().get("texte") or "").strip()
    if not texte:
        return _json({"error": "Écris une réponse."}, status=400)
    try:
        if sig.can_reply_api:
            sig.action_send_reply(texte)
            published = True
        else:
            sig.message_post(
                body="<p><b>Réponse (manuel)</b></p><p>%s</p>" % texte.replace("<", "&lt;"),
                subtype_xmlid="mail.mt_note",
            )
            sig.action_marquer_repondu()
            published = False
    except UserError as err:
        return _json({"error": str(err)}, status=400)
    except Exception as err:
        _logger.warning("veille reply signal=%s: %s", sid, err)
        return _json({"error": "Impossible d’envoyer la réponse."}, status=500)
    return _json(
        {
            "ok": True,
            "published": published,
            "signal": serialize_signal(sig, detail=True),
        }
    )


def sync_conversation(sid):
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    try:
        sig.action_sync_conversation()
    except UserError as err:
        return _json({"error": str(err)}, status=400)
    return _json({"ok": True, "signal": serialize_signal(sig, detail=True)})


def whoami():
    role = current_role()
    return _json(
        {
            "ok": True,
            "identity": role if role.get("mapped") else None,
            "prerequisite": (
                None
                if role.get("mapped")
                else "Utilisateur Odoo non mappé (Leila / Martin / Zakaria / Karine)."
            ),
            "role": role,
            "voir_toutes": True,
        }
    )


def _can_followup(sig, role):
    if role.get("admin") or role.get("slug") in ("karine", "martin", "zakaria"):
        return True
    soumis = (getattr(sig, "canal_soumission", None) or "").strip().lower()
    return bool(role.get("slug") and soumis == role.get("slug"))


def _can_convert(sig, role):
    slug = role.get("slug")
    if slug in ("karine", "martin"):
        return True
    if slug == "zakaria":
        return infer_branche(sig) == "coins_marocain" or (
            (sig.plateforme or "") == "coins_marocain"
        )
    return False


def submit_facebook_manuel():
    body = _body()
    url = (body.get("url") or "").strip()
    soumetteur = (body.get("soumetteur") or body.get("canal_soumission") or "").strip().lower()
    vertical = (body.get("vertical") or "").strip()
    note = (body.get("note") or body.get("texte") or "").strip()
    categorie = (body.get("categorie_lead") or body.get("categorie") or "").strip()
    if not url or "facebook.com" not in url:
        return _json({"error": "Le lien Facebook du post est obligatoire."}, status=400)
    if soumetteur not in ("leila", "martin", "zakaria"):
        return _json({"error": "Soumetteur : Leila, Martin ou Zakaria."}, status=400)
    if vertical not in VERTICALS:
        return _json({"error": "Vertical inconnu."}, status=400)
    if categorie and categorie not in VERTICALS[vertical]["categories"]:
        return _json({"error": "Catégorie hors taxonomie de ce vertical."}, status=400)
    titre = note or ("Post Facebook soumis manuellement — %s" % vertical)
    Signal = request.env["doorway.veille.signal"].sudo()
    payload = {
        "source": "facebook_manuel",
        "plateforme": vertical,
        "auteur": soumetteur,
        "canal_soumission": soumetteur,
        "titre": titre[:200],
        "texte": note or titre,
        "url": url,
        "statut": "en_attente",
        "marche": "autre" if vertical == "coins_marocain" else "quebec",
        "categorie_lead": categorie or False,
        "signal_id_externe": "fbman-%s-%s" % (soumetteur, fields_now_id()),
    }
    sig = Signal.upsert_from_payload(payload)
    from odoo.addons.doorway_veille_sociale.services.scoring_service import (
        VeilleScoringService,
    )

    scoring = VeilleScoringService(request.env)
    generation_error = None
    try:
        if not sig.score_intention:
            scoring.apply_scores_to_records(sig)
    except Exception as err:  # noqa: BLE001
        _logger.warning("facebook-manuel score failed signal=%s: %s", sig.id, err)
    try:
        if not sig.reponse_publique or not sig.message_prive:
            data = generate_lead_copy(scoring, sig, infer_branche(sig), categorie_lock=categorie or None)
            sig.sudo().write(
                {
                    "categorie_lead": data["categorie_lead"],
                    "reponse_publique": data["reponse_publique"],
                    "message_prive": data["message_prive"],
                }
            )
            sig._push_to_supabase()
    except Exception as err:  # noqa: BLE001
        _logger.warning("facebook-manuel generation failed signal=%s: %s", sig.id, err)
        generation_error = str(err)
        if not (sig.reponse_publique or "").strip():
            sig.sudo().write(
                {
                    "reponse_publique": "[Génération échouée] %s — relance depuis le tiroir." % err,
                    "message_prive": "[Génération échouée] Relance « Régénérer la réponse ».",
                }
            )
    payload = serialize_signal(sig, detail=True)
    if generation_error and not payload.get("generation_ok"):
        payload["generation_error"] = generation_error
    return _json({"ok": True, "signal": payload})


def fields_now_id():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def followup(sid):
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    role = current_role()
    kind = (_body().get("kind") or "").strip()
    if kind == "ignore":
        if not _can_followup(sig, role):
            return _json({"error": "Pas le droit d'ignorer ce signal."}, status=403)
        sig.action_ignorer()
        return _json({"ok": True, "signal": serialize_signal(sig, detail=True), "logged": False})
    if kind == "converti":
        if not _can_convert(sig, role):
            return _json({"error": "Seul Karine/Martin (Zakaria sur sa branche) marque converti."}, status=403)
        result = set_converti(sig.id, role.get("slug"))
        return _json({"ok": True, "signal": serialize_signal(sig, detail=True), "convert": result})
    if kind not in ("public", "prive"):
        return _json({"error": "kind invalide"}, status=400)
    if not _can_followup(sig, role):
        return _json({"error": "Boutons de suivi réservés au soumetteur et aux admin."}, status=403)
    texte = sig.reponse_publique if kind == "public" else sig.message_prive
    slug = role.get("slug") or (sig.canal_soumission or "karine")
    logged = log_followup(
        slug=slug,
        kind=kind,
        signal_id=sig.id,
        texte=texte or "",
        url=sig.url_enrichie or sig.url or "",
        platform="facebook" if "facebook" in (sig.source or "") else (sig.source or "facebook"),
    )
    return _json({"ok": True, "signal": serialize_signal(sig, detail=True), "log": logged})


def regenerate(sid):
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    from odoo.addons.doorway_veille_sociale.services.scoring_service import (
        VeilleScoringService,
    )

    scoring = VeilleScoringService(request.env)
    try:
        data = generate_lead_copy(
            scoring, sig, infer_branche(sig), categorie_lock=sig.categorie_lead or None
        )
    except Exception as err:  # noqa: BLE001
        _logger.warning("regenerate failed signal=%s: %s", sig.id, err)
        return _json(
            {
                "error": "Génération échouée : %s" % err,
                "signal": serialize_signal(sig, detail=True),
            },
            status=500,
        )
    sig.sudo().write(
        {
            "reponse_publique": data["reponse_publique"],
            "message_prive": data["message_prive"],
        }
    )
    sig._push_to_supabase()
    return _json({"ok": True, "signal": serialize_signal(sig, detail=True)})


def set_categorie(sid):
    sig = _signal(sid)
    if not sig:
        return _json({"error": "Signal introuvable."}, status=404)
    cat = (_body().get("categorie_lead") or "").strip()
    vertical = vertical_for_branche(
        infer_branche(sig),
        sig.plateforme if (sig.source or "") == "facebook_manuel" else None,
    )
    allowed = VERTICALS[vertical]["categories"]
    if cat not in allowed:
        return _json({"error": "Catégorie hors liste.", "allowed": allowed}, status=400)
    sig.sudo().write({"categorie_lead": cat})
    from odoo.addons.doorway_veille_sociale.services.scoring_service import (
        VeilleScoringService,
    )

    data = generate_lead_copy(
        VeilleScoringService(request.env), sig, infer_branche(sig), categorie_lock=cat
    )
    sig.sudo().write(
        {
            "reponse_publique": data["reponse_publique"],
            "message_prive": data["message_prive"],
        }
    )
    sig._push_to_supabase()
    return _json({"ok": True, "signal": serialize_signal(sig, detail=True)})
