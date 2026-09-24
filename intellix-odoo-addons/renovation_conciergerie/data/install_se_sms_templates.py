# Run via odoo-bin shell.
# SMS Soumission Entrepreneurs — templates + actions latérales (pas d'envoi).

BOOKING = "https://soumissionentrepreneurs.com/deposer-projet"
icp = env["ir.config_parameter"].sudo()
if not icp.get_param("renovation_conciergerie.se_booking_url"):
    icp.set_param("renovation_conciergerie.se_booking_url", BOOKING)
REVIEW = icp.get_param("renovation_conciergerie.se_review_url") or "https://soumissionentrepreneurs.com/avis"
if not icp.get_param("renovation_conciergerie.se_review_url"):
    icp.set_param("renovation_conciergerie.se_review_url", REVIEW)

PRENOM_LEAD = "{{ (object.contact_name or object.partner_id.name or 'bonjour').split()[0] }}"
PROJET_LEAD = "{{ object.service_category_ids[:1].name if object.service_category_ids else 'rénovation' }}"
ORIGINE = "{{ object.source_id.name if object.source_id else 'soumissionentrepreneurs.com' }}"
PRENOM_EVT = "{{ (object.opportunity_id.contact_name or (object.partner_ids[:1].name if object.partner_ids else '') or 'bonjour').split()[0] }}"
ESTIMATEUR = "{{ object.user_id.name or 'un estimateur' }}"
PROJET_EVT = "{{ object.opportunity_id.service_category_ids[:1].name if object.opportunity_id and object.opportunity_id.service_category_ids else 'rénovation' }}"
HEURE = "{{ format_datetime(object.start, tz=object.user_id.tz or 'America/Montreal', dt_format='HH:mm', lang_code='fr_CA') }}"

TEMPLATES = [
    {
        "xmlid": "mail_sms_se_t0_confirmation",
        "name": "SE SMS — T0 Confirmation",
        "model": "crm.lead",
        "body": (
            f"Bonjour {PRENOM_LEAD}, merci pour votre demande pour {PROJET_LEAD} "
            f"sur {ORIGINE}. Un conseiller (Félix) vous appelle sous peu au 581-798-5801. "
            "— Soumission Entrepreneurs"
        ),
    },
    {
        "xmlid": "mail_sms_se_a2_rappel_24h",
        "name": "SE SMS — A2 Rappel 24h",
        "model": "calendar.event",
        "body": (
            f"Rappel : votre rendez-vous avec {ESTIMATEUR} pour {PROJET_EVT} "
            f"est demain à {HEURE}. Besoin de reporter ? Répondez à ce texto. "
            "— Soumission Entrepreneurs"
        ),
    },
    {
        "xmlid": "mail_sms_se_a3_rappel_2h",
        "name": "SE SMS — A3 Rappel 2h",
        "model": "calendar.event",
        "body": (
            f"À tantôt {PRENOM_EVT} ! {ESTIMATEUR} arrive vers {HEURE} "
            f"pour votre soumission {PROJET_EVT}. — Soumission Entrepreneurs"
        ),
    },
    {
        "xmlid": "mail_sms_se_c1_avis",
        "name": "SE SMS — C1 Demande d'avis",
        "model": "crm.lead",
        "body": (
            f"Bonjour {PRENOM_LEAD}, comment s'est passé votre projet de {PROJET_LEAD} "
            f"avec nous ? Dites-le-nous ici : {REVIEW} — Soumission Entrepreneurs"
        ),
    },
    {
        "xmlid": "mail_sms_se_b2_relance_j2",
        "name": "SE SMS — B2 Relance J+2",
        "model": "crm.lead",
        "body": (
            f"{PRENOM_LEAD}, on n'a pas réussi à se parler pour votre projet de {PROJET_LEAD}. "
            f"Choisissez un moment ici : {BOOKING} — Soumission Entrepreneurs"
        ),
    },
    {
        "xmlid": "mail_sms_se_b4_relance_j8",
        "name": "SE SMS — B4 Dernière relance J+8",
        "model": "crm.lead",
        "body": (
            f"Dernier message {PRENOM_LEAD} — si votre projet de {PROJET_LEAD} "
            f"est toujours d'actualité, on est là : {BOOKING}. Sinon, bonne continuation ! "
            "— Soumission Entrepreneurs"
        ),
    },
]

Sms = env["sms.template"].sudo()
IrModel = env["ir.model"].sudo()
IrData = env["ir.model.data"].sudo()
Mailing = env["mailing.mailing"].sudo()

created = []
for spec in TEMPLATES:
    xmlid = f"renovation_conciergerie.{spec['xmlid']}"
    model = IrModel.search([("model", "=", spec["model"])], limit=1)
    vals = {
        "name": spec["name"],
        "model_id": model.id,
        "body": spec["body"],
    }
    tmpl = env.ref(xmlid, raise_if_not_found=False)
    if not tmpl:
        tmpl = Sms.search([("name", "=", spec["name"])], limit=1)
    if tmpl:
        tmpl.write(vals)
        action = "updated"
    else:
        tmpl = Sms.create(vals)
        action = "created"
    if not env.ref(xmlid, raise_if_not_found=False):
        IrData.create({
            "name": spec["xmlid"],
            "module": "renovation_conciergerie",
            "model": "sms.template",
            "res_id": tmpl.id,
            "noupdate": True,
        })
    if not tmpl.sidebar_action_id:
        tmpl.action_create_sidebar_action()

    mailing_name = spec["name"]
    mailing = Mailing.search([
        ("mailing_type", "=", "sms"),
        ("subject", "=", mailing_name),
    ], limit=1)
    mailing_vals = {
        "subject": mailing_name,
        "mailing_type": "sms",
        "state": "draft",
        "sms_template_id": tmpl.id,
        "body_plaintext": spec["body"],
        "mailing_model_id": model.id,
        "sms_allow_unsubscribe": True,
        "sms_force_send": False,
    }
    if mailing:
        mailing.write(mailing_vals)
        mailing_action = "mailing-updated"
    else:
        mailing = Mailing.create(mailing_vals)
        mailing_action = "mailing-created"

    created.append((action, tmpl.id, spec["name"], spec["model"], mailing_action, mailing.id))

env.cr.commit()
for row in created:
    print(*row)
print("review_url", REVIEW)
print("booking_url", BOOKING)
