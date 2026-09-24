from odoo import api, fields, models


class CrmLeadAssurance(models.Model):
    _inherit = "crm.lead"

    is_assurance_pipeline = fields.Boolean(
        string="Pipeline Assurance",
        compute="_compute_is_assurance_pipeline",
        store=True,
    )

    # ------------------------------------------------------------------
    # Niveau 1 — Qualification immédiate (formulaire front-end)
    # ------------------------------------------------------------------
    ins_type = fields.Selection(
        [
            ("auto", "Auto"),
            ("habitation", "Habitation"),
            ("sante", "Santé"),
            ("emprunteur", "Emprunteur"),
            ("plusieurs", "Plusieurs"),
        ],
        string="Type d'assurance",
        tracking=True,
    )
    ins_situation = fields.Selection(
        [
            ("assure", "Déjà assuré"),
            ("non_assure", "Pas encore assuré"),
            ("mecontent", "Assuré mais mécontent"),
        ],
        string="Situation actuelle",
        tracking=True,
    )
    ins_montant_mensuel = fields.Selection(
        [
            ("m30", "Moins de 30€"),
            ("30_60", "30-60€"),
            ("60_100", "60-100€"),
            ("p100", "Plus de 100€"),
            ("inconnu", "Je ne sais pas"),
        ],
        string="Montant mensuel actuel",
        tracking=True,
    )
    ins_anciennete = fields.Selection(
        [
            ("m1", "Moins d'1 an"),
            ("1_3", "1-3 ans"),
            ("p3", "Plus de 3 ans"),
        ],
        string="Ancienneté assurance",
        help="Loi Hamon : si +1 an, résiliation possible immédiatement.",
        tracking=True,
    )
    ins_age = fields.Selection(
        [
            ("18_25", "18-25"),
            ("26_35", "26-35"),
            ("36_50", "36-50"),
            ("51_65", "51-65"),
            ("65p", "65+"),
        ],
        string="Tranche d'âge",
        tracking=True,
    )
    ins_creneau_rappel = fields.Selection(
        [
            ("matin", "Matin"),
            ("apresmidi", "Après-midi"),
            ("soir", "Soir"),
            ("asap", "Dès que possible"),
        ],
        string="Créneau de rappel",
        tracking=True,
    )

    # ------------------------------------------------------------------
    # Niveau 2 — Qualification téléphonique (script concierge)
    # ------------------------------------------------------------------
    # Auto
    ins_auto_type_vehicule = fields.Selection(
        [
            ("citadine", "Citadine"),
            ("suv", "SUV"),
            ("electrique", "Électrique"),
            ("autre", "Autre"),
        ],
        string="Type de véhicule",
    )
    ins_auto_annee = fields.Integer(string="Année du véhicule")
    ins_auto_bonus_malus = fields.Float(string="Bonus/malus (coefficient)")
    ins_auto_km_annuel = fields.Integer(string="Kilométrage annuel")
    ins_auto_conducteur = fields.Selection(
        [("principal", "Principal seul"), ("secondaire", "Secondaire")],
        string="Conducteur",
    )
    ins_auto_sinistres_3ans = fields.Integer(string="Sinistres (3 dernières années)")
    # Habitation
    ins_hab_statut = fields.Selection(
        [("locataire", "Locataire"), ("proprietaire", "Propriétaire")],
        string="Statut logement",
    )
    ins_hab_surface = fields.Float(string="Surface (m²)")
    ins_hab_ville_quartier = fields.Char(string="Ville / type de quartier")
    ins_hab_valeur_mobilier = fields.Float(string="Valeur estimée du mobilier")
    ins_hab_sinistres = fields.Char(string="Sinistres déclarés récents")
    # Santé
    ins_sante_composition = fields.Selection(
        [("seul", "Seul"), ("couple", "Couple"), ("famille", "Famille")],
        string="Composition",
    )
    ins_sante_nb_enfants = fields.Integer(string="Nombre d'enfants")
    ins_sante_regime = fields.Selection(
        [("salarie", "Salarié"), ("tns", "TNS"), ("retraite", "Retraité")],
        string="Régime",
    )
    ins_sante_besoins = fields.Char(string="Besoins prioritaires (dentaire, optique, hospitalisation)")
    ins_sante_medecin_traitant = fields.Boolean(string="Médecin traitant déclaré")
    # Tous types
    ins_budget_max = fields.Float(string="Budget max mensuel accepté (€)")
    ins_priorite = fields.Selection(
        [
            ("prix", "Prix bas"),
            ("garanties", "Garanties complètes"),
            ("les_deux", "Les deux"),
        ],
        string="Priorité",
    )
    ins_delai_souscription = fields.Selection(
        [
            ("urgent", "Urgent"),
            ("mois", "Dans le mois"),
            ("compare", "Je compare"),
        ],
        string="Délai de souscription",
        tracking=True,
    )
    ins_comparateur = fields.Char(string="A déjà utilisé un comparateur (oui/lequel/non)")

    # ------------------------------------------------------------------
    # Niveau 3 — Gestion CRM (internes)
    # ------------------------------------------------------------------
    ins_score = fields.Integer(
        string="Score de qualification (0-100)",
        compute="_compute_ins_score",
        store=True,
        tracking=True,
    )
    ins_source_acquisition = fields.Selection(
        [
            ("tiktok", "TikTok"),
            ("meta", "Meta Ads"),
            ("google", "Google Ads"),
            ("seo", "SEO"),
            ("partenaire", "Partenaire"),
            ("bouche", "Bouche à oreille"),
        ],
        string="Source d'acquisition",
        tracking=True,
    )
    ins_motif_perte = fields.Selection(
        [
            ("trop_cher", "Trop cher"),
            ("pas_mieux", "Pas trouvé mieux"),
            ("souscrit_ailleurs", "A souscrit ailleurs"),
            ("pas_joignable", "Pas joignable"),
            ("pas_projet", "Pas de projet réel"),
        ],
        string="Motif de perte",
        tracking=True,
    )
    ins_date_reception = fields.Datetime(
        string="Date/heure de réception du lead",
        default=fields.Datetime.now,
        readonly=True,
    )
    ins_nb_tentatives_rappel = fields.Integer(string="Nombre de tentatives de rappel", default=0)
    ins_rappel_repondu = fields.Boolean(string="A répondu au rappel", tracking=True)
    # Commission estimée
    ins_tarif_propose = fields.Float(string="Tarif mensuel proposé (€)")
    ins_taux_commission = fields.Float(string="Taux commission assureur (%)")
    ins_commission_estimee = fields.Float(
        string="Commission estimée (annuelle, €)",
        compute="_compute_ins_commission",
        store=True,
    )

    # ------------------------------------------------------------------
    # KPI adaptatif (pastille colorée) — affiché sur tout le CRM
    # ------------------------------------------------------------------
    kpi_text = fields.Char(
        string="Indicateur",
        compute="_compute_crm_kpi",
        help="Indicateur clé adapté au pipeline (score, éligibilité, budget...).",
    )
    kpi_level = fields.Selection(
        [
            ("high", "Élevé"),
            ("medium", "Moyen"),
            ("low", "Faible"),
            ("none", "—"),
        ],
        string="Niveau KPI",
        compute="_compute_crm_kpi",
    )

    @api.depends(
        "is_assurance_pipeline",
        "ins_score",
        "is_driven_pipeline",
        "driven_eligible",
        "is_marketing_pipeline",
        "marketing_monthly_budget",
        "is_renovation_pipeline",
        "service_category_ids",
        "probability",
    )
    def _compute_crm_kpi(self):
        for lead in self:
            text, level = "", "none"
            if lead.is_assurance_pipeline:
                score = lead.ins_score or 0
                text = "Score %s/100" % score
                level = "high" if score >= 70 else "medium" if score >= 40 else "low"
            elif lead.is_driven_pipeline:
                if lead.driven_eligible:
                    text, level = "Éligible", "high"
                else:
                    text, level = "Non éligible", "low"
            elif lead.is_marketing_pipeline:
                budget = lead.marketing_monthly_budget or 0.0
                if budget:
                    text = "Budget %d $" % int(budget)
                    level = "high" if budget >= 5000 else "medium" if budget >= 2000 else "low"
                else:
                    text, level = "Budget n/d", "none"
            elif lead.is_renovation_pipeline:
                n = len(lead.service_category_ids)
                text = "%d service(s)" % n
                level = "high" if n >= 3 else "medium" if n >= 1 else "none"
            else:
                prob = lead.probability or 0.0
                text = "%d %%" % int(prob)
                level = "high" if prob >= 70 else "medium" if prob >= 40 else "low"
            lead.kpi_text = text
            lead.kpi_level = level

    @api.depends("team_id")
    def _compute_is_assurance_pipeline(self):
        assurance = self.env.ref(
            "renovation_conciergerie.crm_team_assurance", raise_if_not_found=False
        )
        for lead in self:
            lead.is_assurance_pipeline = bool(assurance and lead.team_id == assurance)

    @api.depends(
        "ins_montant_mensuel",
        "ins_anciennete",
        "ins_delai_souscription",
        "ins_source_acquisition",
        "ins_rappel_repondu",
        "is_assurance_pipeline",
    )
    def _compute_ins_score(self):
        for lead in self:
            if not lead.is_assurance_pipeline:
                lead.ins_score = 0
                continue
            score = 0
            if lead.ins_montant_mensuel == "p100":
                score += 30
            elif lead.ins_montant_mensuel == "60_100":
                score += 15
            if lead.ins_anciennete in ("1_3", "p3"):
                score += 25
            if lead.ins_delai_souscription == "urgent":
                score += 20
            if lead.ins_source_acquisition == "google":
                score += 15
            if lead.ins_rappel_repondu:
                score += 10
            lead.ins_score = min(score, 100)

    @api.depends("ins_tarif_propose", "ins_taux_commission")
    def _compute_ins_commission(self):
        for lead in self:
            lead.ins_commission_estimee = (
                (lead.ins_tarif_propose or 0.0)
                * 12.0
                * (lead.ins_taux_commission or 0.0)
                / 100.0
            )
