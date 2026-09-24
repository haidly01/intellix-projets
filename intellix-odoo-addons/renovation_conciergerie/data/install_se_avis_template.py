# Run via odoo-bin shell.
from pathlib import Path

NAME = "SE — Demande d'avis post-projet"
XMLID = "renovation_conciergerie.mail_template_se_avis"
HTML_PATH = Path("/odoo/custom/addons/renovation_conciergerie/data/email_se_avis.html")
BODY = HTML_PATH.read_text(encoding="utf-8")

icp = env["ir.config_parameter"].sudo()
icp.set_param("renovation_conciergerie.se_review_url", "https://soumissionentrepreneurs.com/avis/")

Template = env["mail.template"].sudo()
model = env["ir.model"].sudo().search([("model", "=", "crm.lead")], limit=1)
mail_server = env["ir.mail_server"].sudo().search(
    [("smtp_user", "=", "info@soumissionentrepreneurs.com")], limit=1
)
vals = {
    "name": NAME,
    "model_id": model.id,
    "subject": "Comment s'est passé votre projet, {{ (object.contact_name or object.partner_id.name or 'bonjour').split()[0] }} ?",
    "body_html": BODY,
    "email_from": "Soumission Entrepreneurs <info@soumissionentrepreneurs.com>",
    "email_to": "{{ object.email_from }}",
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
        "name": "mail_template_se_avis",
        "module": "renovation_conciergerie",
        "model": "mail.template",
        "res_id": template.id,
        "noupdate": True,
    })
    print("xmlid set")
print("template", template.id, template.name, template.model)
env.cr.commit()
