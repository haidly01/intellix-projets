# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


class CrmLead(models.Model):
    _inherit = "crm.lead"

    coins_is_event_lead = fields.Boolean(
        string="Lead pipeline Événements",
        compute="_compute_coins_is_event_lead",
        store=True,
    )

    # --- Informations de base ---
    coins_type_evenement = fields.Selection(
        [
            ("mariage", "Mariage"),
            ("anniversaire", "Anniversaire"),
            ("seminaire", "Séminaire"),
            ("groupe_amis", "Groupe d’amis"),
            ("reunion_famille", "Réunion de famille"),
            ("autre", "Autre"),
        ],
        string="Type d’événement",
    )
    coins_date_souhaitee = fields.Date(string="Date souhaitée")
    coins_date_flexible = fields.Boolean(string="Date flexible")
    coins_nombre_personnes = fields.Integer(string="Nombre de personnes")
    coins_provenance_invites = fields.Selection(
        [
            ("local", "Local"),
            ("autre_ville_maroc", "Autre ville (Maroc)"),
            ("international", "International"),
        ],
        string="Provenance des invités",
    )
    coins_provenance_invites_detail = fields.Char(
        string="Précision provenance",
        help="Ville / pays d’origine des invités.",
    )
    coins_budget_par_personne = fields.Float(
        string="Budget par personne",
        digits=(16, 2),
    )
    coins_budget_total = fields.Float(
        string="Budget total",
        digits=(16, 2),
    )

    # --- Lieu et hébergement ---
    coins_avec_hebergement = fields.Boolean(string="Avec hébergement")
    coins_nombre_nuits = fields.Integer(string="Nombre de nuits")
    coins_type_lieu = fields.Selection(
        [
            ("villa_privee", "Villa privée"),
            ("riad", "Riad"),
            ("les_deux", "Les deux"),
        ],
        string="Type de lieu",
    )
    coins_piscine_requise = fields.Boolean(string="Piscine requise")
    coins_chambres_separees = fields.Boolean(string="Chambres séparées")
    coins_acces_pmr = fields.Boolean(string="Accès PMR")

    # --- Restauration ---
    coins_type_repas = fields.Selection(
        [
            ("marocain", "Marocain"),
            ("international", "International"),
            ("mix", "Mix"),
        ],
        string="Type de repas",
    )
    coins_nombre_repas = fields.Integer(string="Nombre de repas")
    coins_restrictions_alimentaires = fields.Text(string="Restrictions alimentaires")
    coins_alcool_servi = fields.Selection(
        [
            ("oui", "Oui"),
            ("non", "Non"),
            ("sans_objet", "Sans objet"),
        ],
        string="Alcool servi",
    )
    coins_gateau_requis = fields.Boolean(string="Gâteau requis")

    # --- Ambiance et décoration ---
    coins_theme_couleurs = fields.Char(string="Thème / couleurs")
    coins_decoration_florale = fields.Boolean(string="Décoration florale")
    coins_musique = fields.Selection(
        [
            ("dj", "DJ"),
            ("groupe_live", "Groupe live"),
            ("ambiance_calme", "Ambiance calme"),
            ("aucune", "Aucune"),
        ],
        string="Musique",
    )
    coins_photo_video = fields.Selection(
        [
            ("photographe", "Photographe"),
            ("videaste", "Vidéaste"),
            ("les_deux", "Les deux"),
            ("aucun", "Aucun"),
        ],
        string="Photo / vidéo",
    )
    coins_eclairage_special = fields.Boolean(string="Éclairage spécial")

    # --- Activités ---
    coins_activite_ids = fields.Many2many(
        "coins.event.activite",
        "crm_lead_coins_event_activite_rel",
        "lead_id",
        "activite_id",
        string="Activités",
    )
    coins_activites_enfants = fields.Boolean(string="Activités enfants")
    coins_transport_requis = fields.Selection(
        [
            ("aeroport", "Aéroport"),
            ("entre_lieux", "Entre lieux"),
            ("aucun", "Aucun"),
        ],
        string="Transport requis",
    )

    # --- Spécifique mariage ---
    coins_ceremonie_lieu = fields.Char(string="Lieu de cérémonie")
    coins_nombre_jours_celebration = fields.Integer(string="Nombre de jours de célébration")
    coins_wedding_planner_deja = fields.Boolean(
        string="Wedding planner déjà en place",
    )

    # --- Spécifique anniversaire ---
    coins_surprise = fields.Boolean(string="Surprise")
    coins_etape_marquante = fields.Char(string="Étape marquante")

    # --- Spécifique séminaire ---
    coins_objectif_seminaire = fields.Text(string="Objectif du séminaire")
    coins_materiel_technique = fields.Text(string="Matériel technique")
    coins_salle_reunion_formelle = fields.Boolean(string="Salle de réunion formelle")
    coins_facturation_entreprise = fields.Boolean(string="Facturation entreprise")

    # --- Amis / famille ---
    coins_occasion_precise = fields.Char(string="Occasion précise")
    coins_niveau_organisation = fields.Selection(
        [
            ("tout_organise", "Tout organisé"),
            ("temps_libre", "Temps libre"),
        ],
        string="Niveau d’organisation",
    )

    # --- Clôture ---
    coins_date_limite_proposition = fields.Date(string="Date limite de proposition")
    coins_moyen_recontact = fields.Selection(
        [
            ("whatsapp", "WhatsApp"),
            ("appel", "Appel"),
            ("email", "Email"),
        ],
        string="Moyen de recontact",
    )
    coins_autres_prestataires_en_discussion = fields.Boolean(
        string="Autres prestataires en discussion",
    )

    # --- Prestataires CRM ---
    coins_prestataire_ids = fields.Many2many(
        "coins.prestataire",
        "crm_lead_coins_prestataire_rel",
        "lead_id",
        "prestataire_id",
        string="Prestataires retenus",
    )
    coins_prestataire_suggestion_ids = fields.Many2many(
        "coins.prestataire",
        "crm_lead_coins_prestataire_suggestion_rel",
        "lead_id",
        "prestataire_id",
        string="Prestataires suggérés",
    )

    @api.depends("team_id")
    def _compute_coins_is_event_lead(self):
        team = self.env.ref(
            "coins_marocain.crm_team_evenements", raise_if_not_found=False
        )
        team_id = team.id if team else False
        for lead in self:
            lead.coins_is_event_lead = bool(team_id and lead.team_id.id == team_id)

    def _coins_event_prestataire_domain_parts(self):
        """Build OR domain parts from filled brief fields (simple category/tag match)."""
        self.ensure_one()
        Tag = self.env["coins.prestataire.tag"]
        parts = []

        def tag_ids(*codes):
            return Tag.search([("code", "in", list(codes))]).ids

        if self.coins_musique == "dj":
            parts.append([("category", "=", "dj")])
        elif self.coins_musique == "groupe_live":
            tids = tag_ids("groupe_live", "live")
            if tids:
                parts.append(
                    ["&", ("category", "=", "dj"), ("specialite_tag_ids", "in", tids)]
                )
            else:
                parts.append([("category", "=", "dj")])

        if self.coins_photo_video == "photographe":
            parts.append([("category", "=", "photographe")])
        elif self.coins_photo_video == "videaste":
            parts.append([("category", "=", "videaste")])
        elif self.coins_photo_video == "les_deux":
            parts.append([("category", "in", ["photographe", "videaste"])])

        if self.coins_decoration_florale:
            parts.append([("category", "=", "fleuriste")])

        if self.coins_type_repas:
            repas_domain = [("category", "=", "traiteur")]
            if self.coins_type_repas in ("marocain", "international"):
                tids = tag_ids(self.coins_type_repas)
                if tids:
                    repas_domain = [
                        "&",
                        ("category", "=", "traiteur"),
                        ("specialite_tag_ids", "in", tids),
                    ]
            elif self.coins_type_repas == "mix":
                tids = tag_ids("marocain", "international", "mix")
                if tids:
                    repas_domain = [
                        "&",
                        ("category", "=", "traiteur"),
                        ("specialite_tag_ids", "in", tids),
                    ]
            parts.append(repas_domain)

        if self.coins_transport_requis and self.coins_transport_requis != "aucun":
            parts.append([("category", "=", "transport")])

        activite_codes = set(self.coins_activite_ids.mapped("code"))
        if activite_codes & {"excursion", "quad"}:
            parts.append([("category", "=", "excursion")])
        if activite_codes & {"spa_massage", "hammam"}:
            parts.append([("category", "=", "spa")])
        if "cours_cuisine" in activite_codes:
            tids = tag_ids("cours_cuisine")
            if tids:
                parts.append([("specialite_tag_ids", "in", tids)])
            else:
                parts.append([("category", "=", "excursion")])

        if self.coins_type_lieu or self.coins_piscine_requise:
            lieu_domain = [("category", "=", "lieu")]
            tag_codes = []
            if self.coins_type_lieu == "villa_privee":
                tag_codes.append("villa_privee")
            elif self.coins_type_lieu == "riad":
                tag_codes.append("riad")
            elif self.coins_type_lieu == "les_deux":
                tag_codes.extend(["villa_privee", "riad"])
            if self.coins_piscine_requise:
                tag_codes.append("piscine")
            tids = tag_ids(*tag_codes) if tag_codes else []
            if tids:
                lieu_domain = [
                    "&",
                    ("category", "=", "lieu"),
                    ("specialite_tag_ids", "in", tids),
                ]
            parts.append(lieu_domain)

        if self.coins_type_evenement in ("mariage", "seminaire"):
            tids = tag_ids(self.coins_type_evenement)
            if tids:
                parts.append([("specialite_tag_ids", "in", tids)])

        return parts

    def action_suggest_prestataires(self):
        self.ensure_one()
        if not self.coins_is_event_lead:
            raise UserError(
                _(
                    "Les suggestions de prestataires sont réservées aux leads "
                    "de l’équipe Événements."
                )
            )
        Prestataire = self.env["coins.prestataire"]
        base = [("active", "=", True), ("disponibilite", "!=", "indisponible")]
        parts = self._coins_event_prestataire_domain_parts()
        if not parts:
            self.coins_prestataire_suggestion_ids = [(5, 0, 0)]
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Suggestions prestataires"),
                    "message": _(
                        "Aucun critère de filtrage renseigné sur le brief. "
                        "Remplissez musique, lieu, restauration, etc."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        domain = expression.AND([base, expression.OR(parts)])
        suggested = Prestataire.search(domain)
        self.coins_prestataire_suggestion_ids = [(6, 0, suggested.ids)]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Suggestions prestataires"),
                "message": _("%s prestataire(s) suggéré(s). Voir l’onglet Prestataires.")
                % len(suggested),
                "type": "success",
                "sticky": False,
            },
        }

    def action_assign_suggested_prestataires(self):
        """Ajoute toutes les suggestions aux prestataires retenus."""
        self.ensure_one()
        self.coins_prestataire_ids = [
            (4, pid) for pid in self.coins_prestataire_suggestion_ids.ids
        ]
        return True
