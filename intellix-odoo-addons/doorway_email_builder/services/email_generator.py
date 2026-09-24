# -*- coding: utf-8 -*-
"""Générateur : transforme une réponse Claude validée en artefacts email Odoo.

Pour chaque email du payload, crée (ou met à jour, de façon idempotente) :
  - un ``mail.template`` (envoi transactionnel / depuis une fiche),
  - un ``mailing.mailing`` (campagne d'emailing de masse éditable),
  - un ``doorway.message.template`` canal Email (catalogue de templates),
  - un ``doorway.message.campaign`` (canal Email) prêt pour le flux de campagne
    multi-contacts — uniquement si ``create_campaigns`` est vrai.

Idempotent : on conserve un mapping ``email_key → {ids}`` sur le brief ; une
re-génération met à jour les enregistrements existants au lieu de les dupliquer.

Robuste : un email en échec n'interrompt pas la génération des autres (il est
remonté dans ``warnings``).
"""
import logging

_logger = logging.getLogger(__name__)


def _email_key(email, index):
    """Clé stable d'un email pour l'idempotence (basée sur l'étape de séquence)."""
    step = email.get("sequence_step")
    try:
        step = int(step)
    except (TypeError, ValueError):
        step = index + 1
    return "email_%d" % step


def _wrap_html(html_body, preheader):
    """Enveloppe le corps dans un conteneur responsive 600px + pré-en-tête caché."""
    preheader_span = ""
    if preheader:
        preheader_span = (
            '<span style="display:none !important;visibility:hidden;opacity:0;'
            'color:transparent;height:0;width:0;overflow:hidden;mso-hide:all;">'
            "%s</span>" % preheader
        )
    return (
        '<div style="background:#f4f5f7;margin:0;padding:24px 0;">'
        "%s"
        '<table role="presentation" align="center" width="100%%" cellpadding="0" '
        'cellspacing="0" style="border-collapse:collapse;background:#f4f5f7;">'
        '<tr><td align="center" style="padding:0 12px;">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;width:600px;max-width:600px;'
        "background:#ffffff;border-radius:10px;overflow:hidden;"
        'font-family:Arial,Helvetica,sans-serif;color:#1f2937;">'
        '<tr><td style="padding:28px 32px;font-size:15px;line-height:1.55;">'
        "%s"
        "</td></tr></table>"
        "</td></tr></table>"
        "</div>"
    ) % (preheader_span, html_body or "")


def _res_partner_model_id(env):
    model = env["ir.model"].sudo().search([("model", "=", "res.partner")], limit=1)
    return model.id if model else False


def _has_message_template(env):
    return bool(
        env["ir.model"].sudo().search(
            [("model", "=", "doorway.message.template")], limit=1
        )
    )


def _has_message_campaign(env):
    return bool(
        env["ir.model"].sudo().search(
            [("model", "=", "doorway.message.campaign")], limit=1
        )
    )


def _upsert_mail_template(env, email, wrapped_html, subject, ids, warnings):
    Template = env["mail.template"].sudo()
    model_id = _res_partner_model_id(env)
    vals = {
        "name": "[Email Builder] %s" % email["name"],
        "subject": subject,
        "body_html": wrapped_html,
        "model_id": model_id,
        "use_default_to": True,
        "auto_delete": True,
    }
    rec = None
    if ids.get("mail_template_id"):
        candidate = Template.browse(ids["mail_template_id"])
        if candidate.exists():
            rec = candidate
    try:
        if rec:
            rec.write(vals)
        else:
            rec = Template.create(vals)
        ids["mail_template_id"] = rec.id
    except Exception as exc:  # noqa: BLE001
        _logger.exception("Email builder : mail.template")
        warnings.append("mail.template « %s » non généré : %s" % (email["name"], exc))


def _upsert_mailing(env, email, wrapped_html, subject, ids, warnings):
    Mailing = env["mailing.mailing"].sudo()
    model_id = _res_partner_model_id(env)
    if not model_id:
        warnings.append("Modèle res.partner introuvable : mailing non généré.")
        return
    vals = {
        "subject": subject,
        "preview": email.get("preheader") or "",
        "body_arch": wrapped_html,
        "body_html": wrapped_html,
        "mailing_model_id": model_id,
        "mailing_type": "mail",
        "state": "draft",
    }
    rec = None
    if ids.get("mailing_id"):
        candidate = Mailing.browse(ids["mailing_id"])
        if candidate.exists():
            rec = candidate
    try:
        if rec:
            rec.write(vals)
        else:
            rec = Mailing.create(vals)
        ids["mailing_id"] = rec.id
    except Exception as exc:  # noqa: BLE001
        _logger.exception("Email builder : mailing.mailing")
        warnings.append("mailing.mailing « %s » non généré : %s" % (email["name"], exc))


def _upsert_message_template(env, email, wrapped_html, subject, ids, warnings):
    if not _has_message_template(env):
        return
    Template = env["doorway.message.template"].sudo()
    vals = {
        "name": "[Email IA] %s" % email["name"],
        "canal": "email",
        "sujet": subject,
        "corps": wrapped_html,
        "corps_text": email.get("text_body") or "",
        "actif": True,
    }
    rec = None
    if ids.get("msg_template_id"):
        candidate = Template.browse(ids["msg_template_id"])
        if candidate.exists():
            rec = candidate
    try:
        if rec:
            rec.write(vals)
        else:
            rec = Template.create(vals)
        ids["msg_template_id"] = rec.id
    except Exception as exc:  # noqa: BLE001
        _logger.exception("Email builder : doorway.message.template")
        warnings.append(
            "doorway.message.template « %s » non généré : %s" % (email["name"], exc)
        )


def _upsert_campaign(env, email, wrapped_html, subject, campaign_name, ids, warnings):
    if not _has_message_campaign(env):
        return
    Campaign = env["doorway.message.campaign"].sudo()
    vals = {
        "name": campaign_name,
        "sujet": subject,
        "corps_email": wrapped_html,
        "corps_master": wrapped_html,
        "canal_email": True,
    }
    rec = None
    if ids.get("campaign_id"):
        candidate = Campaign.browse(ids["campaign_id"])
        if candidate.exists():
            rec = candidate
    try:
        if rec:
            # Ne réécrase pas une campagne déjà envoyée / planifiée.
            if rec.statut in ("brouillon",):
                rec.write(vals)
        else:
            rec = Campaign.create(dict(vals, statut="brouillon"))
        ids["campaign_id"] = rec.id
    except Exception as exc:  # noqa: BLE001
        _logger.exception("Email builder : doorway.message.campaign")
        warnings.append(
            "doorway.message.campaign « %s » non générée : %s" % (campaign_name, exc)
        )


def generate_emails(env, payload, artifact_map=None, create_campaigns=True):
    """Construit les artefacts email à partir du payload validé.

    :param payload: payload validé (cf. claude_email_builder.validate_payload).
    :param artifact_map: mapping email_key→ids d'une génération précédente.
    :param create_campaigns: créer/maj aussi des doorway.message.campaign.
    :returns: dict {ok, message, emails:[...], artifact_map:{...}, warnings:[...]}
    """
    warnings = []
    artifact_map = dict(artifact_map or {})
    emails = payload.get("emails") or []
    if not emails:
        return {
            "ok": False,
            "message": "Aucun email à générer.",
            "emails": [],
            "artifact_map": artifact_map,
            "warnings": warnings,
        }

    campaign_base = payload.get("campaign_name") or "Campagne email"
    sequence = len(emails) > 1
    out = []
    for index, email in enumerate(emails):
        key = _email_key(email, index)
        ids = dict(artifact_map.get(key) or {})
        subject = (email.get("subjects") or ["(objet)"])[0]
        wrapped_html = _wrap_html(email.get("html_body"), email.get("preheader"))

        _upsert_mail_template(env, email, wrapped_html, subject, ids, warnings)
        _upsert_mailing(env, email, wrapped_html, subject, ids, warnings)
        _upsert_message_template(env, email, wrapped_html, subject, ids, warnings)
        if create_campaigns:
            campaign_name = (
                "%s — %d/%d" % (campaign_base, index + 1, len(emails))
                if sequence
                else campaign_base
            )
            _upsert_campaign(
                env, email, wrapped_html, subject, campaign_name, ids, warnings
            )

        artifact_map[key] = ids
        out.append(
            {
                "key": key,
                "name": email["name"],
                "subjects": email.get("subjects") or [],
                "preheader": email.get("preheader") or "",
                "sequence_step": email.get("sequence_step"),
                "send_delay_days": email.get("send_delay_days"),
                "cta": email.get("cta") or [],
                "mail_template_id": ids.get("mail_template_id"),
                "mailing_id": ids.get("mailing_id"),
                "msg_template_id": ids.get("msg_template_id"),
                "campaign_id": ids.get("campaign_id"),
            }
        )

    if not any(
        e.get("mail_template_id") or e.get("mailing_id") for e in out
    ):
        return {
            "ok": False,
            "message": "Aucun artefact email n'a pu être généré.",
            "emails": out,
            "artifact_map": artifact_map,
            "warnings": warnings,
        }

    return {
        "ok": True,
        "message": "%d email(s) généré(s) en artefacts Odoo." % len(out),
        "emails": out,
        "artifact_map": artifact_map,
        "warnings": warnings,
    }


def payload_preview(payload):
    """Renvoie un résumé texte du payload→emails (diagnostic/dry-run)."""
    lines = []
    for index, email in enumerate(payload.get("emails", [])):
        subjects = " | ".join(email.get("subjects") or [])
        lines.append(
            "- %s [étape %s, +%sj] : %s"
            % (
                email.get("name"),
                email.get("sequence_step", index + 1),
                email.get("send_delay_days", 0),
                subjects,
            )
        )
    return "\n".join(lines)
