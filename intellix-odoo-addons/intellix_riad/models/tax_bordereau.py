# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

ONES = (
    "",
    "un",
    "deux",
    "trois",
    "quatre",
    "cinq",
    "six",
    "sept",
    "huit",
    "neuf",
    "dix",
    "onze",
    "douze",
    "treize",
    "quatorze",
    "quinze",
    "seize",
    "dix-sept",
    "dix-huit",
    "dix-neuf",
)
TENS = (
    "",
    "",
    "vingt",
    "trente",
    "quarante",
    "cinquante",
    "soixante",
    "soixante",
    "quatre-vingt",
    "quatre-vingt",
)


def _below_hundred(n):
    n = int(n)
    if n < 20:
        return ONES[n]
    tens, unit = divmod(n, 10)
    if tens == 7 or tens == 9:
        base = TENS[tens]
        rest = _below_hundred(10 + unit)
        liaison = " et " if unit == 1 and tens == 7 else "-"
        return "%s%s%s" % (base, liaison, rest)
    if unit == 0:
        return TENS[tens] + ("s" if tens == 8 else "")
    liaison = " et " if unit == 1 and tens != 8 else "-"
    return "%s%s%s" % (TENS[tens], liaison, ONES[unit])


def amount_to_fr_letters(value):
    value = int(round(float(value or 0)))
    if value == 0:
        return "zéro dirhams"
    if value == 1:
        return "un dirham"

    def chunk(n):
        if n < 100:
            return _below_hundred(n)
        hundreds, rest = divmod(n, 100)
        head = "cent" if hundreds == 1 else "%s cent" % ONES[hundreds]
        if rest == 0:
            return head + ("s" if hundreds > 1 else "")
        return "%s %s" % (head, _below_hundred(rest))

    millions, rest = divmod(value, 1000000)
    thousands, rest = divmod(rest, 1000)
    parts = []
    if millions:
        parts.append(
            "un million" if millions == 1 else "%s millions" % chunk(millions)
        )
    if thousands:
        parts.append("mille" if thousands == 1 else "%s mille" % chunk(thousands))
    if rest:
        parts.append(chunk(rest))
    return "%s dirhams" % " ".join(parts)


class IntellixRiadTaxBordereauTemplate(models.Model):
    _name = "intellix.riad.tax.bordereau.template"
    _description = "Modèle de bordereau de taxe de séjour (par commune)"
    _order = "name"

    name = fields.Char(string="Commune / modèle", required=True)
    active = fields.Boolean(default=True)
    kingdom_label = fields.Char(default="ROYAUME DU MAROC")
    authority_name = fields.Char(string="Autorité (ligne 1)")
    authority_line_2 = fields.Char(string="Autorité (ligne 2)")
    authority_line_3 = fields.Char(string="Autorité (ligne 3)")
    tax_title = fields.Char(default="TAXE DE SEJOUR")
    document_title = fields.Char(default="Bordereau de versement")
    service_name = fields.Char(string="Service destinataire")
    city_for_date = fields.Char(string="Ville pour la date")
    currency_word = fields.Char(default="dirhams")
    show_operator_nature = fields.Boolean(default=True)
    show_cin = fields.Boolean(default=True)
    show_fax = fields.Boolean(default=True)
    show_admin_box = fields.Boolean(
        default=True,
        string="Encadré service (n° déclaration / reçu)",
    )
    certification_text = fields.Text(
        default="Je soussigné certifie exactes les informations mentionnées sur le présent bordereau",
    )
    footer_note = fields.Char(
        default="À déposer à la recette communale avant la fin du mois suivant le trimestre.",
    )
    operator_name_label = fields.Char(
        default="Nom et prénom de l'exploitant ou raison sociale",
    )
    operator_address_label = fields.Char(
        default="Adresse personnelle ou siège social",
    )
    operator_cin_label = fields.Char(default="N° CIN ou n° d'immatriculation")
    phone_label = fields.Char(default="Tél")
    fax_label = fields.Char(default="Fax")
    nature_label = fields.Char(default="Nature de l'exploitant")
    nature_proprietaire_label = fields.Char(default="Propriétaire")
    nature_directeur_label = fields.Char(default="Directeur")
    nature_gerant_label = fields.Char(default="Gérant")
    col_clients = fields.Char(default="Nombre de clients")
    col_nights = fields.Char(default="Nombre des nuitées")
    col_rate = fields.Char(default="Taux de la taxe")
    col_amount = fields.Char(default="Montant de la taxe")
    settled_text = fields.Char(default="Arrêté le présent bordereau à la somme de")
    in_letters_label = fields.Char(default="En lettres")
    declarant_label = fields.Char(default="Le Déclarant")
    date_prefix = fields.Char(default="À")
    admin_box_title = fields.Char(default="Service communal de l'assiette")
    admin_declaration_no = fields.Char(default="N° de déclaration")
    admin_received = fields.Char(default="Reçue le")
    admin_ordonnateur = fields.Char(default="L'ordonnateur")
    report_xmlid = fields.Char(
        string="Rapport QWeb",
        default="intellix_riad.action_report_tax_bordereau",
        help="Imprimé à utiliser. Chaque commune peut pointer vers son propre rapport.",
    )
    notes = fields.Text(string="Notes internes (non imprimées)")


class IntellixRiadTaxBordereau(models.Model):
    _name = "intellix.riad.tax.bordereau"
    _description = "Bordereau trimestriel de taxe de séjour"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc, quarter desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    template_id = fields.Many2one(
        "intellix.riad.tax.bordereau.template",
        string="Modèle communal",
        required=True,
        ondelete="restrict",
    )
    year = fields.Integer(required=True, index=True)
    quarter = fields.Selection(
        [("1", "T1"), ("2", "T2"), ("3", "T3"), ("4", "T4")],
        required=True,
        index=True,
    )
    date_from = fields.Date(readonly=True)
    date_to = fields.Date(readonly=True)
    operator_name = fields.Char(string="Nom de l'exploitant")
    operator_address = fields.Char(string="Adresse / siège")
    operator_cin = fields.Char(string="N° CIN / immatriculation")
    operator_phone = fields.Char(string="Téléphone")
    operator_fax = fields.Char(string="Fax")
    operator_nature = fields.Selection(
        [
            ("proprietaire", "Propriétaire"),
            ("directeur", "Directeur"),
            ("gerant", "Gérant"),
        ],
        string="Nature de l'exploitant",
    )
    guests_count = fields.Integer(string="Nombre de clients", readonly=True)
    nights_count = fields.Integer(string="Nombre de nuitées", readonly=True)
    tax_rate = fields.Float(string="Taux de la taxe", digits=(16, 2), readonly=True)
    amount_due = fields.Monetary(
        string="Montant total dû",
        currency_field="currency_id",
        readonly=True,
    )
    amount_letter = fields.Char(string="Montant en lettres", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    state = fields.Selection(
        [("draft", "Brouillon"), ("ready", "Prêt à déposer"), ("sent", "Envoyé")],
        default="draft",
        tracking=True,
    )
    sent_at = fields.Datetime(readonly=True)
    due_date = fields.Date(string="Échéance de dépôt", compute="_compute_print_fields")
    quarter_ordinal = fields.Char(compute="_compute_print_fields")
    amount_figure = fields.Char(compute="_compute_print_fields")
    print_date = fields.Date(compute="_compute_print_fields")

    _sql_constraints = [
        (
            "estab_quarter_uniq",
            "unique(establishment_id, year, quarter)",
            "Un seul bordereau par établissement et par trimestre.",
        ),
    ]

    @api.depends("establishment_id", "year", "quarter")
    def _compute_name(self):
        for rec in self:
            rec.name = _("Bordereau T%s %s — %s") % (
                rec.quarter or "?",
                rec.year or "",
                rec.establishment_id.name or "",
            )

    @api.depends("year", "quarter", "amount_due", "establishment_id")
    def _compute_print_fields(self):
        ordinals = {"1": "1er", "2": "2ème", "3": "3ème", "4": "4ème"}
        today = fields.Date.context_today(self)
        for rec in self:
            rec.print_date = today
            rec.quarter_ordinal = ordinals.get(rec.quarter or "", rec.quarter or "")
            rec.amount_figure = ("%.2f" % (rec.amount_due or 0)).replace(".", ",")
            if rec.year and rec.quarter and rec.establishment_id:
                rec.due_date = rec.establishment_id._quarter_due_date(
                    rec.year, rec.quarter
                )
            else:
                rec.due_date = False

    def action_refresh_totals(self):
        for rec in self:
            rec._refresh_from_stays()
        return True

    def _refresh_from_stays(self):
        self.ensure_one()
        estab = self.establishment_id
        data = estab.compile_tourist_tax_rows(self.year, int(self.quarter))
        guests = sum(row["guests"] for row in data["rows"])
        person_nights = sum(row["guests"] * row["nights"] for row in data["rows"])
        rate = data["rate"] or estab.tourist_tax_rate or 0.0
        amount = round(person_nights * rate, 2)
        mad = estab.tourist_tax_currency_id or self.env["res.currency"].search(
            [("name", "=", "MAD")], limit=1
        )
        self.write(
            {
                "date_from": data["start"],
                "date_to": data["end"],
                "operator_name": estab.tax_operator_name or estab.name,
                "operator_address": estab.tax_operator_address
                or getattr(estab.property_id, "street", None)
                or "",
                "operator_cin": estab.tax_operator_cin or "",
                "operator_phone": estab.tax_operator_phone or "",
                "operator_fax": estab.tax_operator_fax or "",
                "operator_nature": estab.tax_operator_nature or "gerant",
                "guests_count": guests,
                "nights_count": person_nights,
                "tax_rate": rate,
                "amount_due": amount,
                "amount_letter": amount_to_fr_letters(amount),
                "currency_id": mad.id if mad else False,
                "template_id": (
                    estab.tax_bordereau_template_id.id
                    if estab.tax_bordereau_template_id
                    else self.template_id.id
                ),
                "state": "ready",
            }
        )

    def action_print(self):
        self.action_refresh_totals()
        xmlid = (
            self.template_id.report_xmlid
            or "intellix_riad.action_report_tax_bordereau"
        )
        report = self.env.ref(xmlid, raise_if_not_found=False)
        if not report:
            raise UserError(
                _("Rapport introuvable (%s). Vérifiez le modèle de bordereau.") % xmlid
            )
        return report.report_action(self)

    def action_print_annex(self):
        """Justificatif interne — distinct du bordereau communal et des fiches de police."""
        return self.env.ref("intellix_riad.action_report_tax_annex").report_action(self)

    def action_mark_sent(self):
        self.write({"state": "sent", "sent_at": fields.Datetime.now()})
        return True

    def annex_rows(self):
        self.ensure_one()
        data = self.establishment_id.compile_tourist_tax_rows(self.year, int(self.quarter))
        return data["rows"]
