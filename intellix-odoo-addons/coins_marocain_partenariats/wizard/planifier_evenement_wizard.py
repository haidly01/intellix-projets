# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Mapping préparé — inactif tant qu'il n'y a aucun coins.deco.prestataire.
STYLE_THEME_MAP = {
    "moderne": "moderne_minimaliste",
    "traditionnel": "oriental_traditionnel",
    "nature_rural": "boheme_nature",
    "desert": "nomade_desert",
}

TAILLE_CEILING = {
    "1_10": 10,
    "10_20": 20,
    "20_30": 30,
    "30_plus": 30,
}

BUDGET_LABELS = {
    "lt_500": "Moins de 500 DH",
    "500_1500": "Dès 500 DH",
    "1500_3000": "1 500 – 3 000 DH",
    "gt_3000": "Plus de 3 000 DH",
}

STYLE_CARDS = (
    ("moderne", "Moderne", "Villa contemporaine, lignes épurées"),
    ("traditionnel", "Traditionnel", "Riad, terrasses, patio"),
    ("nature_rural", "Nature-Rural", "Ourika, Atlas, jardin"),
    ("desert", "Désert", "Agafay, camp, dunes"),
)


class CoinsPlanifierEvenementWizard(models.TransientModel):
    """Wizard allégé — notes + préférence de style. Pas de filtre catalogue."""

    _name = "coins.planifier.evenement.wizard"
    _description = "Planifier l'événement (fiche voyageur)"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Fiche voyageur",
        required=True,
        ondelete="cascade",
    )
    step = fields.Integer(default=1)

    traveler_name = fields.Char(related="lead_id.contact_name", readonly=True)
    event_type = fields.Selection(related="lead_id.coins_type_evenement", readonly=True)
    taille_groupe = fields.Selection(
        related="lead_id.coins_voy_taille_groupe",
        readonly=True,
    )
    nombre_personnes = fields.Integer(
        related="lead_id.coins_nombre_personnes",
        readonly=True,
    )
    date_souhaitee = fields.Date(
        related="lead_id.coins_date_souhaitee",
        readonly=True,
    )
    budget = fields.Char(related="lead_id.coins_voyageur_budget", readonly=True)
    subtitle = fields.Char(compute="_compute_header")
    capacity_note = fields.Char(compute="_compute_header")

    style_lieu = fields.Selection(
        [
            ("moderne", "Moderne"),
            ("traditionnel", "Traditionnel"),
            ("nature_rural", "Nature-Rural"),
            ("desert", "Désert"),
        ],
        string="Style de lieu",
    )
    property_list_html = fields.Html(
        string="Lieux catalogue",
        compute="_compute_property_list_html",
        sanitize=False,
    )
    deco_ready = fields.Boolean(compute="_compute_deco_ready")
    deco_hint = fields.Char(compute="_compute_deco_ready")

    note_lieu = fields.Text(string="Lieu pressenti / à confirmer")
    note_menu = fields.Text(string="Menu — note libre")
    note_divert = fields.Text(string="Divertissement — note libre")
    note_deco = fields.Text(string="Décoration — note libre")
    note_heberg = fields.Text(string="Hébergement — note libre (optionnel)")

    resume_html = fields.Html(
        string="Résumé",
        compute="_compute_resume_html",
        sanitize=False,
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        lead = self.env["crm.lead"].browse(vals.get("lead_id") or 0)
        if not lead:
            return vals
        vals.setdefault("step", 1)
        vals["style_lieu"] = lead.coins_evt_style or False
        vals["note_lieu"] = lead.coins_evt_note_lieu or False
        vals["note_menu"] = lead.coins_evt_note_menu or False
        vals["note_divert"] = lead.coins_evt_note_divert or False
        vals["note_deco"] = lead.coins_evt_note_deco or False
        vals["note_heberg"] = lead.coins_evt_note_heberg or False
        return vals

    @api.model
    def _capacity_for_lead(self, lead):
        """Plafond du seau ; entier seulement si seau vide et effectif > 2."""
        seau = lead.coins_voy_taille_groupe
        n = int(lead.coins_nombre_personnes or 0)
        if seau:
            return TAILLE_CEILING.get(seau, 10)
        if n > 2:
            return n
        return 0

    def _budget_label(self, lead):
        raw = (lead.coins_voyageur_budget or "").strip()
        if not raw:
            return "—"
        return BUDGET_LABELS.get(raw, raw)

    @api.depends(
        "lead_id",
        "lead_id.contact_name",
        "lead_id.coins_type_evenement",
        "lead_id.coins_date_souhaitee",
        "lead_id.coins_voyageur_budget",
        "lead_id.coins_voy_taille_groupe",
        "lead_id.coins_nombre_personnes",
    )
    def _compute_header(self):
        type_sel = self.env["crm.lead"]._fields["coins_type_evenement"].selection
        type_labels = dict(type_sel)
        taille_sel = self.env["crm.lead"]._fields["coins_voy_taille_groupe"].selection
        taille_labels = dict(taille_sel)
        for wiz in self:
            lead = wiz.lead_id
            if not lead:
                wiz.subtitle = ""
                wiz.capacity_note = ""
                continue
            name = lead.contact_name or lead.name or "Voyageur"
            ev = type_labels.get(lead.coins_type_evenement) or "Événement"
            date_s = (
                lead.coins_date_souhaitee.strftime("%d/%m/%Y")
                if lead.coins_date_souhaitee
                else "date à confirmer"
            )
            seau = taille_labels.get(lead.coins_voy_taille_groupe) or "groupe ?"
            wiz.subtitle = "%s · %s · %s · %s · groupe %s" % (
                name,
                ev,
                date_s,
                wiz._budget_label(lead),
                seau,
            )
            cap = self._capacity_for_lead(lead)
            n = int(lead.coins_nombre_personnes or 0)
            if lead.coins_voy_taille_groupe:
                wiz.capacity_note = _(
                    "Filtre capacité (quand le catalogue sera classé) : "
                    "seau %s → plafond %s. Effectif saisi %s ignoré."
                ) % (seau, cap, n or "—")
            elif n > 2:
                wiz.capacity_note = _(
                    "Pas de seau — effectif %s retenu (événement plausible)."
                ) % n
            else:
                wiz.capacity_note = _(
                    "Pas de seau ni d’effectif événement. Aucun filtre capacité."
                )

    def _deco_count(self):
        if "coins.deco.prestataire" not in self.env:
            return 0
        return self.env["coins.deco.prestataire"].sudo().search_count([])

    @api.depends("style_lieu")
    def _compute_deco_ready(self):
        n = self._deco_count()
        for wiz in self:
            wiz.deco_ready = bool(n)
            theme = STYLE_THEME_MAP.get(wiz.style_lieu or "")
            if n:
                wiz.deco_hint = _(
                    "Catalogue déco disponible — mapping style→thème encore inactif "
                    "dans cette version allégée."
                )
            elif theme:
                wiz.deco_hint = _(
                    "0 prestataire coins.deco.prestataire. "
                    "Thème prévu plus tard : %s (inactif)."
                ) % theme
            else:
                wiz.deco_hint = _(
                    "0 prestataire coins.deco.prestataire. "
                    "Notes libres uniquement. Mapping style→thème inactif."
                )

    @api.depends("lead_id")
    def _compute_property_list_html(self):
        Prop = self.env["coins.property"].sudo().with_context(active_test=False)
        props = Prop.search([], order="name")
        type_labels = dict(Prop._fields["property_type"].selection)
        cards = []
        for prop in props:
            extra = []
            if not prop.active:
                extra.append("archivé")
            meta = " · ".join(
                x
                for x in (
                    type_labels.get(prop.property_type) or prop.property_type,
                    prop.city or "",
                    ", ".join(extra) if extra else "",
                )
                if x
            )
            cards.append(
                '<div class="o_coins_evt_prop%s"><div class="n">%s</div>'
                '<div class="meta">%s</div></div>'
                % (
                    " test" if extra or "test" in (prop.name or "").lower() else "",
                    escape(prop.name or "—"),
                    escape(meta),
                )
            )
        body = (
            '<div class="o_coins_evt_empty"><b>Inventaire réel, non filtrable.</b> '
            "Aucun bien n’a de style / budget / capacité événement en prod. "
            "Lecture seule — %s fiches coins.property. "
            "Note libre ci-dessous pour le lieu pressenti.</div>"
            '<div class="o_coins_evt_props">%s</div>'
            % (len(props), "".join(cards) or "<p>Aucun bien.</p>")
        )
        html = Markup(body)
        for wiz in self:
            wiz.property_list_html = html

    @api.depends(
        "lead_id",
        "style_lieu",
        "note_lieu",
        "note_menu",
        "note_divert",
        "note_deco",
        "note_heberg",
        "deco_ready",
    )
    def _compute_resume_html(self):
        type_sel = self.env["crm.lead"]._fields["coins_type_evenement"].selection
        type_labels = dict(type_sel)
        taille_sel = self.env["crm.lead"]._fields["coins_voy_taille_groupe"].selection
        taille_labels = dict(taille_sel)
        style_labels = dict(self._fields["style_lieu"].selection)
        for wiz in self:
            lead = wiz.lead_id
            name = (lead.contact_name or lead.name or "Voyageur") if lead else "—"
            ev = type_labels.get(lead.coins_type_evenement) if lead else ""
            seau = taille_labels.get(lead.coins_voy_taille_groupe) if lead else ""
            n = int(lead.coins_nombre_personnes or 0) if lead else 0
            style = style_labels.get(wiz.style_lieu) or "— non choisi"
            lieu = (wiz.note_lieu or "").strip() or "Pas de lieu filtré. Note libre vide."
            menu = (wiz.note_menu or "").strip() or "Note menu vide — pas d’options live."
            divert = (wiz.note_divert or "").strip() or "Note divertissement vide."
            deco = (wiz.note_deco or "").strip() or (
                "0 prestataire coins.deco.prestataire."
                if not wiz.deco_ready
                else "Note décoration vide."
            )
            heberg = (wiz.note_heberg or "").strip() or (
                "Optionnel — bouton + Nouvelle réservation inchangé."
            )
            wiz.resume_html = Markup(
                """
<div class="o_coins_evt_cover">
  <div class="o_coins_evt_brand">Coins Marocain
    <span class="tag">Brouillon événement · version allégée</span></div>
  <div class="eyebrow">Préparée pour %s</div>
  <h2>Proposition encore incomplète.</h2>
  <p class="script">Le catalogue prod ne permet pas d’assembler un document fini.</p>
  <div class="o_coins_evt_meta">
    <div><span>Occasion</span><b>%s</b></div>
    <div><span>Invités (seau)</span><b>%s</b></div>
    <div><span>Effectif saisi</span><b>%s</b><i>ne pas filtrer là-dessus</i></div>
    <div><span>Fourchette</span><b>%s</b></div>
    <div><span>Style retenu</span><b>%s</b></div>
  </div>
</div>
<div class="o_coins_evt_block"><h3>1 · Le style</h3><p>%s</p></div>
<div class="o_coins_evt_block"><h3>2 · Le lieu</h3><p>%s</p></div>
<div class="o_coins_evt_block"><h3>3 · Le menu</h3>
  <div class="row"><span>%s</span><em>À chiffrer</em></div></div>
<div class="o_coins_evt_block"><h3>4 · Divertissement</h3>
  <div class="row"><span>%s</span><em>À chiffrer</em></div></div>
<div class="o_coins_evt_block"><h3>5 · Décoration</h3>
  <div class="row"><span>%s</span><em>À chiffrer</em></div></div>
<div class="o_coins_evt_block"><h3>6 · Hébergement</h3><p>%s</p></div>
<div class="o_coins_evt_totaux">
  <h3>Totaux</h3>
  <div class="row"><span>Lieu / privatisation</span><span>Placeholder</span></div>
  <div class="row"><span>Menu + divertissement + déco</span><span>À chiffrer</span></div>
  <div class="row"><span>Hébergement</span><span>Selon réservation existante</span></div>
  <div class="row"><span>statut_conversion
    <i>à écrire plus tard — champ absent</i></span><span>—</span></div>
  <div class="row"><span>montant_extras (Volet B)
    <i>à écrire plus tard — champ absent</i></span><span>—</span></div>
  <div class="row total"><span>Estimation totale</span>
    <span>Impossible — catalogue vide</span></div>
</div>
                """
                % (
                    escape(name),
                    escape(ev or "—"),
                    escape(seau or "—"),
                    escape(str(n) if n else "—"),
                    escape(wiz._budget_label(lead) if lead else "—"),
                    escape(style),
                    escape(
                        style
                        if wiz.style_lieu
                        else "Aucun style cliqué — 0 lieu classé derrière chaque carte."
                    ),
                    escape(lieu),
                    escape(menu),
                    escape(divert),
                    escape(deco),
                    escape(heberg),
                )
            )

    def _assemble_resume_text(self):
        self.ensure_one()
        lead = self.lead_id
        style_labels = dict(self._fields["style_lieu"].selection)
        type_sel = lead._fields["coins_type_evenement"].selection
        lines = [
            "Brouillon événement (interne) — version allégée",
            "Voyageur : %s" % (lead.contact_name or lead.name or "—"),
            "Occasion : %s"
            % (dict(type_sel).get(lead.coins_type_evenement) or "—"),
            "Seau groupe : %s"
            % (lead.coins_voy_taille_groupe or "—"),
            "Effectif saisi : %s (ne pas filtrer)"
            % (lead.coins_nombre_personnes or "—"),
            "Budget : %s" % self._budget_label(lead),
            "Style : %s" % (style_labels.get(self.style_lieu) or "—"),
            "Lieu pressenti : %s" % ((self.note_lieu or "").strip() or "—"),
            "Menu : %s" % ((self.note_menu or "").strip() or "à chiffrer"),
            "Divertissement : %s" % ((self.note_divert or "").strip() or "à chiffrer"),
            "Décoration : %s" % ((self.note_deco or "").strip() or "à chiffrer"),
            "Hébergement : %s"
            % ((self.note_heberg or "").strip() or "voir + Nouvelle réservation"),
            "statut_conversion : — (champ absent)",
            "montant_extras : — (champ absent)",
            "Estimation : à chiffrer — catalogue vide",
        ]
        return "\n".join(lines)

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planifier l'événement"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context, default_lead_id=self.lead_id.id),
        }

    def action_pick_style(self):
        self.ensure_one()
        code = self.env.context.get("style_code")
        if code not in dict(self._fields["style_lieu"].selection):
            raise UserError(_("Style inconnu."))
        self.style_lieu = code
        return self._reopen()

    def action_goto(self):
        self.ensure_one()
        step = int(self.env.context.get("goto") or self.step or 1)
        self.step = min(5, max(1, step))
        return self._reopen()

    def action_next(self):
        self.ensure_one()
        self.step = min(5, (self.step or 1) + 1)
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.step = max(1, (self.step or 1) - 1)
        return self._reopen()

    def action_save_draft(self):
        self.ensure_one()
        lead = self.lead_id
        if lead.coins_fiche_type != "voyageur" and not lead.coins_is_voyageur_lead:
            raise UserError(_("Cette fiche n’est pas une fiche voyageur."))
        lead.write(
            {
                "coins_evt_style": self.style_lieu or False,
                "coins_evt_note_lieu": self.note_lieu or False,
                "coins_evt_note_menu": self.note_menu or False,
                "coins_evt_note_divert": self.note_divert or False,
                "coins_evt_note_deco": self.note_deco or False,
                "coins_evt_note_heberg": self.note_heberg or False,
                "coins_evt_resume": self._assemble_resume_text(),
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Brouillon enregistré"),
                "message": _(
                    "Résumé sur la fiche. Rien n’a été envoyé au voyageur. "
                    "Aucune réservation créée."
                ),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
