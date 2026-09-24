# Run via odoo-bin shell. Creates/updates mail.template SE RDV confirmé.
from pathlib import Path

NAME = "SE — Confirmation rendez-vous estimateur"
XMLID = "renovation_conciergerie.mail_template_se_rdv_confirme"
HTML_PATH = Path("/odoo/custom/addons/renovation_conciergerie/data/email_se_rdv_confirme.html")
BODY = HTML_PATH.read_text(encoding="utf-8")

Template = env["mail.template"].sudo()
model = env["ir.model"].sudo().search([("model", "=", "calendar.event")], limit=1)
mail_server = env["ir.mail_server"].sudo().search(
    [("smtp_user", "=", "info@soumissionentrepreneurs.com")], limit=1
)
vals = {
    "name": NAME,
    "model_id": model.id,
    "subject": "Votre rendez-vous est confirmé — Soumission Entrepreneurs",
    "body_html": BODY,
    "email_from": "Soumission Entrepreneurs <info@soumissionentrepreneurs.com>",
    "email_to": "{{ object.opportunity_id.email_from or object.partner_ids[:1].email }}",
    "use_default_to": False,
    "auto_delete": False,
    "email_layout_xmlid": False,
}
if mail_server:
    vals["mail_server_id"] = mail_server.id

template = env.ref(XMLID, raise_if_not_found=False)
if not template:
    template = Template.search([("name", "=", NAME)], limit=1)
if template:
    template.write(vals)
    print("updated", template.id)
else:
    template = Template.create(vals)
    print("created", template.id)

if not env.ref(XMLID, raise_if_not_found=False):
    env["ir.model.data"].sudo().create({
        "name": "mail_template_se_rdv_confirme",
        "module": "renovation_conciergerie",
        "model": "mail.template",
        "res_id": template.id,
        "noupdate": True,
    })
    print("xmlid set")
print("template", template.id, template.name, template.model)
env.cr.commit()
