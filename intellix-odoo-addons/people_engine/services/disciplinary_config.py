# -*- coding: utf-8 -*-
"""
Seuils disciplinaires validés — IntelliX CRM — Maroc / Call Center — Juin 2026.
Source de vérité pour escalade, détection auto et matrice de décision.
"""
import datetime
import json

# ---------------------------------------------------------------------------
# 1. Logs de temps manquants
# ---------------------------------------------------------------------------
SEUILS_LOG_MANQUANT = {
    "alerte_warning": 4,
    "alerte_critique": 24,
    "incidents_30_jours": {
        1: "avertissement_verbal",
        2: "avertissement_ecrit",
        3: "mise_a_pied",
        4: "licenciement_faute_grave",
    },
    "deduction_paie": True,
    "deduction_mode": "heures_non_reconnues",
    "grace_period_minutes": 60,
}

# ---------------------------------------------------------------------------
# 2. Pauses et pausettes
# ---------------------------------------------------------------------------
SEUILS_PAUSES = {
    "pausette": {
        "duree_max_minutes": 15,
        "duree_critique_minutes": 20,
        "quota_max_par_shift": 3,
        "quota_alerte": 3,
        "deductible_paie": True,
    },
    "dejeuner": {
        "duree_min_minutes": 30,
        "duree_max_minutes": 60,
        "duree_critique_minutes": 75,
        "quota_max_par_shift": 1,
        "deductible_paie": False,
    },
    "personnelle": {
        "duree_max_minutes": 10,
        "duree_critique_minutes": 15,
        "quota_max_par_shift": 2,
        "deductible_paie": True,
        "validation_superviseur": True,
    },
    "escalade_quota_pauses": {
        1: "alerte_superviseur",
        3: "avertissement_verbal",
        6: "avertissement_ecrit",
        10: "mise_a_pied",
    },
}

# ---------------------------------------------------------------------------
# 3. Absences non déclarées
# ---------------------------------------------------------------------------
SEUILS_ABSENCES = {
    "delai_prevenance_heures": 48,
    "delai_urgence_avant_shift": True,
    "justificatif_delai_heures": 48,
    "escalade_30_jours": {
        1: "avertissement_ecrit",
        2: "mise_a_pied",
        3: "licenciement_faute_grave",
    },
    "deduction_paie": True,
    "deduction_mode": "journees_non_reconnues",
    "absences_injustifiees_licenciement": 4,
    "fenetre_licenciement_mois": 12,
}

# ---------------------------------------------------------------------------
# 4. Saisie CRM manquante
# ---------------------------------------------------------------------------
SEUILS_SAISIE_CRM = {
    "delai_saisie_minutes": 2,
    "alerte_superviseur_minutes": 10,
    "incident_auto_minutes": 30,
    "taux_saisie_minimum": 95,
    "taux_saisie_critique": 85,
    "deduction_facture_pc": 10,
    "deduction_facture_critique": 25,
    "deduction_facture_freelance": True,
    "escalade_semaine": {
        1: "alerte_superviseur",
        2: "avertissement_verbal",
        3: "avertissement_ecrit",
        4: "mise_a_pied",
    },
}

# ---------------------------------------------------------------------------
# Calendrier ouvrable Maroc
# ---------------------------------------------------------------------------
JOURS_FERIES_MAROC = [
    "01-01",
    "01-11",
    "01-14",
    "05-01",
    "07-30",
    "08-14",
    "08-20",
    "08-21",
    "10-31",
    "11-06",
    "11-18",
]

SHIFT_DEBUT_HEURE = 9
SHIFT_FIN_HEURE = 18
HEURES_JOURNEE_ABSENCE = 8.0


def est_jour_ouvrable(date_check, env=None):
    """True si jour ouvrable (lun-ven, hors fériés fixes Maroc et hr.leave.public)."""
    if isinstance(date_check, datetime.datetime):
        date_check = date_check.date()
    if date_check.weekday() >= 5:
        return False
    if date_check.strftime("%m-%d") in JOURS_FERIES_MAROC:
        return False
    if env is not None:
        dt_start = datetime.datetime.combine(date_check, datetime.time.min)
        dt_end = datetime.datetime.combine(date_check, datetime.time.max)
        if "hr.leave.public" in env:
            public = env["hr.leave.public"].sudo().search(
                [
                    ("date_from", "<=", dt_end),
                    ("date_to", ">=", dt_start),
                ],
                limit=1,
            )
            if public:
                return False
        if "resource.calendar.leaves" in env:
            public = env["resource.calendar.leaves"].sudo().search(
                [
                    ("resource_id", "=", False),
                    ("date_from", "<=", dt_end),
                    ("date_to", ">=", dt_start),
                ],
                limit=1,
            )
            if public:
                return False
    return True


# ---------------------------------------------------------------------------
# 5. Performance et KPIs
# ---------------------------------------------------------------------------
SEUILS_KPI = {
    "call_center": {
        "taux_joignabilite": {"cible": 30, "minimum": 20, "critique": 10},
        "taux_qualification": {"cible": 25, "minimum": 15, "critique": 8},
        "appels_par_heure": {"cible": 12, "minimum": 8, "critique": 5},
        "dmc_minutes": {"cible": 4, "maximum": 8, "minimum": 1},
    },
    "commercial": {
        "leads_par_semaine": {"cible": 10, "minimum": 5, "critique": 2},
        "taux_conversion": {"cible": 20, "minimum": 10, "critique": 5},
        "rdv_minimum": 2,
    },
    "marketing": {
        "taches_completees_semaine": {"minimum": 80, "critique": 60},
        "heures_minimum": 35,
        "heures_critique": 20,
    },
    "escalade_kpi": {
        1: "alerte_superviseur",
        2: "avertissement_ecrit",
        3: "mise_a_pied",
        4: "licenciement_insuffisance",
    },
}

# ---------------------------------------------------------------------------
# 6. Comportement et éthique
# ---------------------------------------------------------------------------
SEUILS_COMPORTEMENT = {
    "fraude_log": {
        1: "licenciement_faute_grave",
        "remuneration_suspendue": True,
        "acces_coupe_immediat": True,
    },
    "violation_confidentialite": {
        1: "licenciement_faute_grave",
        "penalite_minimale_mad": 10000,
    },
    "comportement_irrespectueux": {
        1: "avertissement_ecrit",
        2: "mise_a_pied",
        3: "licenciement_faute_grave",
    },
    "refus_instruction": {
        1: "avertissement_ecrit",
        2: "mise_a_pied",
        3: "licenciement_faute_grave",
    },
    "concurrence_deloyale": {
        1: "licenciement_faute_grave",
        "penalite_minimale_mad": 20000,
    },
}

# ---------------------------------------------------------------------------
# 7. Délais légaux Maroc
# ---------------------------------------------------------------------------
DELAIS_LEGAUX_MAROC = {
    "prescription_jours": 30,
    "alerte_prescription_jours": 20,
    "delai_min_convocation_entretien": 8,
    "delai_notification_decision": 48,
    "duree_max_mise_a_pied_jours": 8,
    "preavis_anciennete": {
        "moins_1_an": 8,
        "1_a_5_ans": 30,
        "plus_5_ans": 60,
    },
    "indemnite_par_annee": {
        "1_a_5_ans": 96,
        "6_a_10_ans": 144,
        "11_a_15_ans": 192,
        "plus_15_ans": 240,
    },
    "faute_grave_indemnite": False,
    "faute_grave_preavis": False,
}

# ---------------------------------------------------------------------------
# 8. Matrice de décision
# ---------------------------------------------------------------------------
LEGENDE_SANCTIONS = {
    "AV": "Avertissement verbal",
    "AE": "Avertissement écrit",
    "MAP1": "Mise à pied 1 jour",
    "MAP2": "Mise à pied 2 jours",
    "MAP3": "Mise à pied 3 jours",
    "LFS": "Licenciement faute simple (préavis + indemnités)",
    "LFG": "Licenciement faute grave (immédiat, sans indemnité)",
    "C": "Coaching + plan amélioration",
}

MATRICE_DECISION = {
    "log_manquant": ["AV", "AE", "MAP1", "LFG", True],
    "pause_depassee": ["AV", "AV", "AE", "MAP2", True],
    "pause_quota": ["AV", "AE", "MAP1", "MAP2", True],
    "absence": ["AE", "MAP2", "LFG", "LFG", True],
    "crm_note_manquante": ["AV", "AE", "MAP1", "LFG", True],
    "kpi_sous_seuil": ["C", "AE", "MAP3", "LFS", False],
    "comportement": ["AE", "MAP3", "LFG", "LFG", True],
    "refus_instruction": ["AE", "MAP3", "LFG", "LFG", True],
    "fraude_log": ["LFG", "LFG", "LFG", "LFG", True],
    "confidentialite": ["LFG", "LFG", "LFG", "LFG", True],
    "concurrence": ["LFG", "LFG", "LFG", "LFG", True],
    "session_inactive": ["AV", "AE", "AE", "MAP1", False],
    "retard": ["AV", "AE", "MAP1", "MAP2", True],
    "non_conformite": ["AE", "MAP1", "MAP2", "LFG", True],
    "recidive": ["AE", "MAP2", "LFG", "LFG", True],
    "autre": ["AV", "AE", "MAP1", "MAP2", False],
}

SANCTION_CODE_TO_ODOO = {
    "AV": "avertissement_verbal",
    "AE": "avertissement_ecrit",
    "C": "avertissement_verbal",
    "MAP1": "mise_a_pied",
    "MAP2": "mise_a_pied",
    "MAP3": "mise_a_pied",
    "LFS": "licenciement_insuffisance",
    "LFG": "licenciement_faute_grave",
    "alerte_superviseur": False,
    "coaching": "avertissement_verbal",
}

SANCTION_CODE_JOURS_MAP = {
    "MAP1": 1,
    "MAP2": 2,
    "MAP3": 3,
}

INCIDENT_TYPE_ALIASES = {
    "absence_injustifiee": "absence",
    "absence_non_justifiee": "absence",
    "performance_insuffisante": "kpi_sous_seuil",
    "saisie_crm": "crm_note_manquante",
    "kpi_insuffisant": "kpi_sous_seuil",
    "violation_confidentialite": "confidentialite",
    "concurrence_deloyale": "concurrence",
    "comportement_irrespectueux": "comportement",
}

# ---------------------------------------------------------------------------
# 9. Configuration globale
# ---------------------------------------------------------------------------
INTELLIX_DISCIPLINAIRE_CONFIG = {
    "fenetre_recidive_jours": 30,
    "reset_compteur_apres_mois": 6,
    "acces_coupe_immediatement": [
        "fraude_log",
        "confidentialite",
        "concurrence",
        "mise_a_pied",
    ],
    "notifier_superviseur": True,
    "notifier_rh": True,
    "notifier_employe_email": True,
    "notifier_direction_si_lf": True,
    "pdf_auto_avertissement": True,
    "pdf_auto_mise_a_pied": True,
    "pdf_auto_licenciement": True,
    "archivage_enregistrements_jours": 90,
    "archivage_dossier_disciplinaire": 365 * 5,
    "validation_humaine_requise": [
        "mise_a_pied",
        "licenciement_insuffisance",
        "licenciement_faute_grave",
    ],
}

# Rétrocompatibilité ESCALADE → construit depuis MATRICE_DECISION
ESCALADE = {
    type_key: [
        (idx + 1, SANCTION_CODE_TO_ODOO.get(code) or code)
        for idx, code in enumerate(row[:4])
        if SANCTION_CODE_TO_ODOO.get(code)
    ]
    for type_key, row in MATRICE_DECISION.items()
}


def normalize_incident_type(type_incident):
    """Normalise le type d'incident vers la clé MATRICE_DECISION."""
    if not type_incident:
        return "autre"
    return INCIDENT_TYPE_ALIASES.get(type_incident, type_incident)


def resolve_sanction_from_matrice(type_incident, occurrence):
    """
    Retourne (code_matrice, sanction_odoo, jours_map, impact_paie, coaching_requis).
    occurrence : numéro d'occurrence 1-based dans la fenêtre de récidive.
    """
    matrix_key = normalize_incident_type(type_incident)
    row = MATRICE_DECISION.get(matrix_key, MATRICE_DECISION["autre"])
    codes = row[:4]
    impact_paie = row[4] if len(row) > 4 else False
    idx = min(max(int(occurrence or 1), 1), len(codes)) - 1
    code = codes[idx]
    sanction_odoo = SANCTION_CODE_TO_ODOO.get(code)
    jours = SANCTION_CODE_JOURS_MAP.get(code, 0)
    coaching = code == "C"
    return code, sanction_odoo, jours, impact_paie, coaching


def requires_human_validation(sanction_type):
    """True si la sanction nécessite validation RH/Direction."""
    if not sanction_type:
        return False
    return sanction_type in INTELLIX_DISCIPLINAIRE_CONFIG["validation_humaine_requise"]


def requires_immediate_access_cut(type_incident):
    """True si l'accès doit être coupé immédiatement."""
    key = normalize_incident_type(type_incident)
    return key in INTELLIX_DISCIPLINAIRE_CONFIG["acces_coupe_immediatement"]


def get_recidive_window_days(env=None):
    """Fenêtre glissante (jours) — surcharge possible via ir.config_parameter."""
    default = INTELLIX_DISCIPLINAIRE_CONFIG["fenetre_recidive_jours"]
    if env is None:
        return default
    param = env["ir.config_parameter"].sudo().get_param(
        "people_engine.disciplinary.fenetre_recidive_jours"
    )
    try:
        return int(param) if param else default
    except (TypeError, ValueError):
        return default


def get_prescription_days(env=None):
    default = DELAIS_LEGAUX_MAROC["prescription_jours"]
    if env is None:
        return default
    param = env["ir.config_parameter"].sudo().get_param(
        "people_engine.disciplinary.prescription_jours"
    )
    try:
        return int(param) if param else default
    except (TypeError, ValueError):
        return default


def get_prescription_alert_days(env=None):
    default = DELAIS_LEGAUX_MAROC["alerte_prescription_jours"]
    if env is None:
        return default
    param = env["ir.config_parameter"].sudo().get_param(
        "people_engine.disciplinary.alerte_prescription_jours"
    )
    try:
        return int(param) if param else default
    except (TypeError, ValueError):
        return default


def export_config_json():
    """Export JSON pour diagnostic / ir.config_parameter."""
    return json.dumps(
        {
            "seuils_log_manquant": SEUILS_LOG_MANQUANT,
            "seuils_pauses": SEUILS_PAUSES,
            "seuils_absences": SEUILS_ABSENCES,
            "seuils_saisie_crm": SEUILS_SAISIE_CRM,
            "seuils_kpi": SEUILS_KPI,
            "seuils_comportement": SEUILS_COMPORTEMENT,
            "delais_legaux_maroc": DELAIS_LEGAUX_MAROC,
            "matrice_decision": MATRICE_DECISION,
            "intellix_config": INTELLIX_DISCIPLINAIRE_CONFIG,
        },
        ensure_ascii=False,
        indent=2,
    )
