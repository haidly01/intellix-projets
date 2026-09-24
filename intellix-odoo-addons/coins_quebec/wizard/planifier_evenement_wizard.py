# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Mapping préparé — inactif (pas de coins.deco.prestataire au Québec).
STYLE_THEME_MAP = {
    "moderne": "moderne_minimaliste",
    "traditionnel": "oriental_traditionnel",
    "nature_rural": "boheme_nature",
    "desert": "nomade_desert",
}


class CoinsQuebecPlanifierEvenementWizard(models.TransientModel):
    """Wizard allégé voyageurs CQ — notes + style. Pas de filtre catalogue."""

    _name = "coins.quebec.planifier.evenement.wizard"
    _description = "Planifier l'événement (voyageur Coins Québec)"

    voyageur_id = fields.Many2one(
        "coins.quebec.voyageur",
        string="Fiche voyageur",
        required=True,
        ondelete="cascade",
    )
    step = fields.Integer(default=1)
    traveler_name = fields.Char(related="voyageur_id.name", readonly=True)
    type_sejour = fields.Selection(
        related="voyageur_id.type_sejour",
        readonly=True,
    )
    region = fields.Selection(related="voyageur_id.region", readonly=True)
    city = fields.Char(related="voyageur_id.city", readonly=True)
    subtitle = fields.Char(compute="_compute_header")
    capacity_note = fields.Char(compute="_compute_header")

    style_lieu = fields.Selection(
        [
            ("moderne", "Moderne"),
            ("traditionnel", "Traditionnel"),
            ("nature_rural", "Nature-Rural"),
            ("desert", "Nordique"),
        ],
        string="Style de lieu",
    )
    property_list_html = fields.Html(
        compute="_compute_property_list_html",
        sanitize=False,
    )
    deco_hint = fields.Char(compute="_compute_deco_hint")
    note_lieu = fields.Text(string="Lieu pressenti / à confirmer")
    note_menu = fields.Text(string="Menu — note libre")
    note_divert = fields.Text(string="Divertissement — note libre")
    note_deco = fields.Text(string="Décoration — note libre")
    note_heberg = fields.Text(string="Hébergement — note libre (optionnel)")
    resume_html = fields.Html(compute="_compute_resume_html", sanitize=False)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        voy = self.env["coins.quebec.voyageur"].browse(vals.get("voyageur_id") or 0)
        if not voy:
            return vals
        vals.setdefault("step", 1)
        vals["style_lieu"] = voy.cq_evt_style or False
        vals["note_lieu"] = voy.cq_evt_note_lieu or False
        vals["note_menu"] = voy.cq_evt_note_menu or False
        vals["note_divert"] = voy.cq_evt_note_divert or False
        vals["note_deco"] = voy.cq_evt_note_deco or False
        vals["note_heberg"] = voy.cq_evt_note_heberg or False
        return vals

    @api.depends(
        "voyageur_id",
        "voyageur_id.name",
        "voyageur_id.type_sejour",
        "voyageur_id.region",
        "voyageur_id.city",
    )
    def _compute_header(self):
        type_labels = dict(
            self.env["coins.quebec.voyageur"]._fields["type_sejour"].selection
        )
        region_labels = dict(
            self.env["coins.quebec.voyageur"]._fields["region"].selection
        )
        for wiz in self:
            voy = wiz.voyageur_id
            if not voy:
                wiz.subtitle = ""
                wiz.capacity_note = ""
                continue
            wiz.subtitle = "%s · %s · %s%s" % (
                voy.name or "Voyageur",
                type_labels.get(voy.type_sejour) or "séjour",
                region_labels.get(voy.region) or "",
                (" · %s" % voy.city) if voy.city else "",
            )
            wiz.capacity_note = _(
                "Pas de taille de groupe ni de budget sur la fiche voyageur CQ. "
                "Aucun filtre capacité — catalogue non classé."
            )

    @api.depends("style_lieu")
    def _compute_deco_hint(self):
        for wiz in self:
            theme = STYLE_THEME_MAP.get(wiz.style_lieu or "")
            if theme:
                wiz.deco_hint = _(
                    "Pas de coins.deco.prestataire au Québec. "
                    "Thème prévu plus tard : %s (inactif). Notes libres seulement."
                ) % theme
            else:
                wiz.deco_hint = _(
                    "Pas de catalogue déco Coins Québec. Notes libres seulement. "
                    "Mapping style→thème inactif."
                )

    @api.depends("voyageur_id")
    def _compute_property_list_html(self):
        Prop = self.env["coins.quebec.property"].sudo().with_context(active_test=False)
        props = Prop.search([("is_demo", "=", False)], order="name")
        if not props:
            props = Prop.search([], order="name")
        type_labels = dict(Prop._fields["property_type"].selection)
        cards = []
        for prop in props:
            extra = []
            if not prop.active:
                extra.append("archivé")
            if prop.is_demo:
                extra.append("démo")
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
                '<div class="o_cq_evt_prop%s"><div class="n">%s</div>'
                '<div class="meta">%s</div></div>'
                % (
                    " test" if extra else "",
                    escape(prop.name or "—"),
                    escape(meta),
                )
            )
        body = (
            '<div class="o_cq_evt_empty"><b>Inventaire réel, non filtrable.</b> '
            "Aucun bien CQ n’a de style événement. Lecture seule — "
            "%s fiche(s) coins.quebec.property. "
            "Note libre ci-dessous pour le lieu pressenti.</div>"
            '<div class="o_cq_evt_props">%s</div>'
            % (len(props), "".join(cards) or "<p>Aucun bien.</p>")
        )
        html = Markup(body)
        for wiz in self:
            wiz.property_list_html = html

    @api.depends(
        "voyageur_id",
        "style_lieu",
        "note_lieu",
        "note_menu",
        "note_divert",
        "note_deco",
        "note_heberg",
    )
    def _compute_resume_html(self):
        type_labels = dict(
            self.env["coins.quebec.voyageur"]._fields["type_sejour"].selection
        )
        region_labels = dict(
            self.env["coins.quebec.voyageur"]._fields["region"].selection
        )
        style_labels = dict(self._fields["style_lieu"].selection)
        for wiz in self:
            voy = wiz.voyageur_id
            name = voy.name if voy else "—"
            style = style_labels.get(wiz.style_lieu) or "— non choisi"
            lieu = (wiz.note_lieu or "").strip() or "Pas de lieu filtré. Note libre vide."
            menu = (wiz.note_menu or "").strip() or "Note menu vide."
            divert = (wiz.note_divert or "").strip() or "Note divertissement vide."
            deco = (wiz.note_deco or "").strip() or "Pas de prestataire déco au Québec."
            heberg = (wiz.note_heberg or "").strip() or (
                "Optionnel — champ Réservation liée inchangé."
            )
            wiz.resume_html = Markup(
                """
<div class="o_cq_evt_cover">
  <div class="o_cq_evt_brand">Coins Québec
    <span class="tag">Brouillon événement · version allégée</span></div>
  <div class="eyebrow">Préparée pour %s</div>
  <h2>Proposition encore incomplète.</h2>
  <p class="script">Le catalogue Québec ne permet pas d’assembler un document fini.</p>
  <div class="o_cq_evt_meta">
    <div><span>Séjour</span><b>%s</b></div>
    <div><span>Région</span><b>%s</b></div>
    <div><span>Ville</span><b>%s</b></div>
    <div><span>Style retenu</span><b>%s</b></div>
  </div>
</div>
<div class="o_cq_evt_block"><h3>1 · Le style</h3><p>%s</p></div>
<div class="o_cq_evt_block"><h3>2 · Le lieu</h3><p>%s</p></div>
<div class="o_cq_evt_block"><h3>3 · Le menu</h3>
  <div class="row"><span>%s</span><em>À chiffrer</em></div></div>
<div class="o_cq_evt_block"><h3>4 · Divertissement</h3>
  <div class="row"><span>%s</span><em>À chiffrer</em></div></div>
<div class="o_cq_evt_block"><h3>5 · Décoration</h3>
  <div class="row"><span>%s</span><em>À chiffrer</em></div></div>
<div class="o_cq_evt_block"><h3>6 · Hébergement</h3><p>%s</p></div>
<div class="o_cq_evt_totaux">
  <h3>Totaux (CAD)</h3>
  <div class="row"><span>Lieu / privatisation</span><span>Placeholder</span></div>
  <div class="row"><span>Menu + divertissement + déco</span><span>À chiffrer</span></div>
  <div class="row"><span>Hébergement</span><span>Selon réservation liée</span></div>
  <div class="row"><span>statut_conversion
    <i>à écrire plus tard — champ absent</i></span><span>—</span></div>
  <div class="row"><span>montant_extras
    <i>à écrire plus tard — champ absent</i></span><span>—</span></div>
  <div class="row total"><span>Estimation totale</span>
    <span>Impossible — catalogue vide</span></div>
</div>
                """
                % (
                    escape(name),
                    escape(type_labels.get(voy.type_sejour) if voy else "—"),
                    escape(region_labels.get(voy.region) if voy else "—"),
                    escape((voy.city or "—") if voy else "—"),
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
        voy = self.voyageur_id
        style_labels = dict(self._fields["style_lieu"].selection)
        type_labels = dict(voy._fields["type_sejour"].selection)
        region_labels = dict(voy._fields["region"].selection)
        return "\n".join(
            [
                "Brouillon événement CQ (interne) — version allégée",
                "Voyageur : %s" % (voy.name or "—"),
                "Séjour : %s" % (type_labels.get(voy.type_sejour) or "—"),
                "Région : %s" % (region_labels.get(voy.region) or "—"),
                "Ville : %s" % (voy.city or "—"),
                "Style : %s" % (style_labels.get(self.style_lieu) or "—"),
                "Lieu pressenti : %s" % ((self.note_lieu or "").strip() or "—"),
                "Menu : %s" % ((self.note_menu or "").strip() or "à chiffrer"),
                "Divertissement : %s"
                % ((self.note_divert or "").strip() or "à chiffrer"),
                "Décoration : %s" % ((self.note_deco or "").strip() or "à chiffrer"),
                "Hébergement : %s"
                % ((self.note_heberg or "").strip() or "voir réservation liée"),
                "statut_conversion : — (champ absent)",
                "montant_extras : — (champ absent)",
                "Estimation CAD : à chiffrer — catalogue vide",
            ]
        )

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planifier l'événement"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(
                self.env.context, default_voyageur_id=self.voyageur_id.id
            ),
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
        self.voyageur_id.write(
            {
                "cq_evt_style": self.style_lieu or False,
                "cq_evt_note_lieu": self.note_lieu or False,
                "cq_evt_note_menu": self.note_menu or False,
                "cq_evt_note_divert": self.note_divert or False,
                "cq_evt_note_deco": self.note_deco or False,
                "cq_evt_note_heberg": self.note_heberg or False,
                "cq_evt_resume": self._assemble_resume_text(),
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
