# -*- coding: utf-8 -*-
"""
Léa-QC — Instrumentation de précision (baseline mesurable).

Objectif : mesurer EXACTEMENT chaque appel Léa pour la rentabilité.
On stocke des données BRUTES (1 ligne par appel + 1 ligne par tour de parole),
jamais seulement des agrégats, afin de recalculer p50/p95, $/lead, % cacheable, etc.

Coûts : calculés à partir des UNITÉS RÉELLES facturables remontées par chaque
fournisseur (secondes audio Deepgram, caractères ElevenLabs + modèle, tokens
Claude in/out, secondes télécom connectées) — pas un forfait $/min.

NB sur la boucle actuelle : la voix de Léa est jouée à partir de répliques
ElevenLabs pré-générées (clips fixes) et l'aiguillage est déterministe (regex,
pas de Claude par tour). Les unités TTS/LLM ne se remplissent donc QUE si la
boucle pointe vers les endpoints instrumentés (/api/renov/tts/elevenlabs,
/api/renov/llm/claude). Le STT Deepgram et le télécom sont, eux, mesurés en
direct dès aujourd'hui (l'endpoint STT est déjà appelé à chaque tour).
"""
import hashlib
import json
import logging
import math
import re
import unicodedata

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Seuil minimal de connectés/bras sous lequel l'A/B est jugé non concluant.
AB_MIN_CONNECTED_PER_ARM = 30

# Aligné sur doorway_vicidial_campaigns / crm.lead.qualification_statut
QUALIFICATION_STATUT_SELECTION = [
    ("non_fait", "Pas encore qualifié"),
    ("qualifie", "Qualifié — lead chaud"),
    ("a_rappeler", "Rappel"),
    ("rdv", "RDV planifié"),
    ("pas_interesse", "Pas intéressé"),
    ("deja_servi", "Déjà servi"),
    ("locataire", "Locataire"),
    ("dnc", "DNC — Ne plus appeler"),
    ("messagerie", "Boîte vocale"),
    ("hors_cible", "Hors cible"),
    ("faux_num", "Faux numéro"),
    ("b2b_valide", "B2B validé pour Karine"),
]


def variant_for_sid(call_sid):
    """Assignation 50/50 déterministe d'une variante ('A'/'B') depuis le call_sid.

    ⚠️ SOURCE DE VÉRITÉ PARTAGÉE avec n8n (leaVariant dans lea_qc_config.js).
    Hash FNV-1a 32 bits portable : choisi (au lieu de md5) pour pouvoir être
    reproduit À L'IDENTIQUE dans le sandbox du Code node n8n, qui n'expose pas
    crypto/require de façon fiable. La parité (bit de poids faible) est
    strictement identique des deux côtés. NE PAS modifier d'un seul côté.
    """
    s = call_sid or ""
    h = 0x811C9DC5  # FNV offset basis (2166136261)
    for ch in s:
        h ^= ord(ch) & 0xFF
        h = (h * 0x01000193) & 0xFFFFFFFF  # FNV prime, 32 bits
    return "A" if (h % 2) == 0 else "B"


def wilson_interval(successes, total, z=1.96):
    """Intervalle de confiance de Wilson pour une proportion (par défaut 95%)."""
    if not total:
        return (0.0, 0.0)
    p = successes / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2 * total)) / denom
    margin = (
        z
        * math.sqrt((p * (1 - p) / total) + (z * z) / (4 * total * total))
        / denom
    )
    return (max(0.0, center - margin), min(1.0, center + margin))

# ── Tarifs par défaut (unité RÉELLE) — surchargeables via ir.config_parameter ──
# Valeurs publiques indicatives ; à ajuster au contrat réel.
DEFAULT_PRICES = {
    "lea_qc.price.telecom_per_sec": "0.00013333",   # 0.008 $/min (Africa-Con)
    "lea_qc.price.deepgram_per_sec": "0.0000717",   # ~0.0043 $/min (nova-2 pré-enregistré)
    "lea_qc.price.elevenlabs_per_char": "0.00018",  # ~0.18 $/1000 car. (multilingual_v2)
    "lea_qc.price.claude_in_per_token": "0.000003", # 3 $/M tokens entrée (Sonnet)
    "lea_qc.price.claude_out_per_token": "0.000015",# 15 $/M tokens sortie (Sonnet)
}


def normalize_text(text):
    """Normalise un texte TTS pour détecter répétition/cacheabilité."""
    t = unicodedata.normalize("NFKD", (text or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def text_hash(text):
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def percentile(values, pct):
    """p-ième percentile (interpolation linéaire). values: list[float]."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return 0.0
    if len(data) == 1:
        return float(data[0])
    k = (len(data) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(data) - 1)
    frac = k - lo
    return float(data[lo] + (data[hi] - data[lo]) * frac)


class LeaQcSampleCall(models.Model):
    _name = "lea.qc.sample.call"
    _description = "Léa-QC — Appel échantillon (mesure de précision)"
    _order = "call_date desc, id desc"
    _rec_name = "call_sid"

    # ── Identité / contexte ──
    call_sid = fields.Char(string="Call SID", index=True, required=True)
    agent_id = fields.Char(default="lea-qc-2026", index=True)
    campaign = fields.Char(default="DW_QCB2C", index=True)
    variant = fields.Selection(
        [("A", "A — script actuel (contrôle)"), ("B", "B — accroche alternative")],
        string="Variante A/B",
        index=True,
        help="Bras du test A/B de scripts. Assigné de façon déterministe "
        "(50/50) par hash du call_sid — voir variant_for_sid().",
    )
    phone = fields.Char(string="Téléphone")
    phone_display = fields.Char(
        string="Téléphone (affichage)",
        compute="_compute_phone_display",
        store=True,
    )
    prenom = fields.Char()
    partner_id = fields.Many2one("res.partner", ondelete="set null", index=True)
    lead_id = fields.Many2one("crm.lead", ondelete="set null", index=True)
    company_id = fields.Many2one("res.company", index=True)

    # ── Horodatage ──
    start_at = fields.Datetime(string="Début (1er tour)")
    call_date = fields.Datetime(string="Heure appel", index=True)
    end_at = fields.Datetime(string="Fin (call-ended)")

    # ── Issue de connexion ──
    connected = fields.Boolean(index=True)
    connect_outcome = fields.Selection(
        [
            ("connected", "Connecté (humain)"),
            ("voicemail", "Messagerie / répondeur"),
            ("no_answer", "Pas de réponse"),
            ("busy", "Occupé"),
            ("invalid", "Numéro invalide"),
            ("unknown", "Inconnu"),
        ],
        default="unknown",
        index=True,
    )
    amd_result = fields.Char(string="AMD brut")
    duration_sec = fields.Integer(string="Durée connectée (s)")
    duration_display = fields.Char(
        string="Durée",
        compute="_compute_duration_display",
        store=True,
        index=True,
    )
    ended_reason = fields.Char()

    # ── Qualification ──
    qualified = fields.Boolean(index=True)
    qualification_statut = fields.Selection(
        QUALIFICATION_STATUT_SELECTION,
        string="Résultat qualification",
        default="non_fait",
        index=True,
    )
    statut = fields.Char()
    crm_action = fields.Char()
    lead_type = fields.Char()
    call_result_category = fields.Selection(
        [
            ("positif", "Succès positif"),
            ("negatif", "Négatif"),
            ("neutre", "Neutre"),
            ("insucces", "Insuccès"),
        ],
        string="Résultat appel",
        compute="_compute_call_result_category",
        store=True,
        index=True,
    )

    # ── Conversation ──
    turn_ids = fields.One2many("lea.qc.turn", "call_id")
    turn_count = fields.Integer(compute="_compute_aggregates", store=True)
    transcript = fields.Text()
    recording_url = fields.Char()
    has_recording = fields.Boolean(
        string="Enregistrement disponible",
        compute="_compute_has_recording",
        store=True,
    )

    # ── Concurrence ──
    concurrency_at_start = fields.Integer(
        string="Sessions simultanées au démarrage", default=0
    )

    # ── Unités RÉELLES (agrégées des tours + appel) ──
    telecom_sec = fields.Integer(string="Secondes télécom")
    stt_audio_sec = fields.Float(string="Secondes audio Deepgram", digits=(12, 2))
    tts_chars = fields.Integer(string="Caractères TTS synthétisés")
    tts_chars_cacheable = fields.Integer(string="Caractères TTS cacheables")
    llm_tokens_in = fields.Integer(string="Tokens Claude (entrée)")
    llm_tokens_out = fields.Integer(string="Tokens Claude (sortie)")

    # ── Latence par étape (ms) — percentiles calculés sur les tours ──
    stt_ms_p50 = fields.Float(compute="_compute_aggregates", store=True)
    stt_ms_p95 = fields.Float(compute="_compute_aggregates", store=True)
    stt_ms_max = fields.Float(compute="_compute_aggregates", store=True)
    llm_ttft_ms_p50 = fields.Float(compute="_compute_aggregates", store=True)
    llm_ttft_ms_p95 = fields.Float(compute="_compute_aggregates", store=True)
    llm_total_ms_p95 = fields.Float(compute="_compute_aggregates", store=True)
    tts_ttfb_ms_p50 = fields.Float(compute="_compute_aggregates", store=True)
    tts_ttfb_ms_p95 = fields.Float(compute="_compute_aggregates", store=True)
    tts_total_ms_p95 = fields.Float(compute="_compute_aggregates", store=True)
    e2e_ms_p50 = fields.Float(
        string="Latence réponse p50 (ms)", compute="_compute_aggregates", store=True
    )
    e2e_ms_p95 = fields.Float(
        string="Latence réponse p95 (ms)", compute="_compute_aggregates", store=True
    )
    e2e_ms_max = fields.Float(compute="_compute_aggregates", store=True)

    # ── Coûts (à partir des unités réelles) ──
    cost_telecom = fields.Float(digits=(12, 5), compute="_compute_cost", store=True)
    cost_stt = fields.Float(digits=(12, 5), compute="_compute_cost", store=True)
    cost_llm = fields.Float(digits=(12, 5), compute="_compute_cost", store=True)
    cost_tts = fields.Float(digits=(12, 5), compute="_compute_cost", store=True)
    cost_total = fields.Float(
        string="Coût total ($)", digits=(12, 5), compute="_compute_cost", store=True
    )
    cost_per_min = fields.Float(
        string="$/min réel", digits=(12, 5), compute="_compute_cost", store=True
    )
    cacheable_pct = fields.Float(
        string="% caractères TTS cacheables",
        digits=(6, 2),
        compute="_compute_cost",
        store=True,
    )

    # ── Brut ──
    raw_payload = fields.Text(string="Payload brut (JSON)")

    # ── Analyse Claude A/B (post-appel, fail-open) ──
    claude_analysis = fields.Json(string="Analyse Claude (JSON)")
    claude_analyzed_at = fields.Datetime(string="Analysé par Claude", index=True)
    claude_comprehension_score = fields.Float(
        string="Score compréhension Claude",
        digits=(4, 2),
        index=True,
        help="0-10 : clarté du dialogue et adéquation script/prospect.",
    )
    claude_variant_hint = fields.Selection(
        [
            ("A", "Indice gagnant A"),
            ("B", "Indice gagnant B"),
            ("tie", "Égalité"),
            ("unclear", "Indéterminé"),
        ],
        string="Indice variant gagnant (Claude)",
        index=True,
    )

    _sql_constraints = [
        ("call_sid_uniq", "unique(call_sid)", "Cet appel Léa est déjà enregistré."),
    ]

    _QUAL_POSITIF = frozenset({"qualifie", "rdv", "b2b_valide"})
    _QUAL_NEGATIF = frozenset(
        {"pas_interesse", "deja_servi", "locataire", "dnc", "hors_cible", "faux_num"}
    )
    _QUAL_NEUTRE = frozenset({"a_rappeler", "messagerie"})
    _CRM_ACTION_QUAL_MAP = {
        "tag_locataire": "locataire",
        "tag_pas_projet": "pas_interesse",
        "tag_pas_interesse": "pas_interesse",
        "tag_dnc": "dnc",
        "tag_rappeler": "a_rappeler",
        "tag_rappeler_plus_tard": "a_rappeler",
        "tag_lead_qualifie": "qualifie",
        "retirer_liste": "locataire",
        "noter_rappel": "a_rappeler",
        "creer_lead_immo": "qualifie",
        "creer_lead_reno": "qualifie",
        "creer_les_deux": "qualifie",
    }
    _STATUT_QUAL_MAP = {
        "qualifie": "qualifie",
        "qualified": "qualifie",
        "intent_positif": "qualifie",
        "locataire": "locataire",
        "pas_interesse": "pas_interesse",
        "pas_projet": "pas_interesse",
        "non_qualifie": "pas_interesse",
        "refus": "pas_interesse",
        "negatif": "pas_interesse",
        "non": "pas_interesse",
        "dnc": "dnc",
        "messagerie": "messagerie",
        "voicemail": "messagerie",
        "rappeler": "a_rappeler",
        "rappeler_plus_tard": "a_rappeler",
        "rappel": "a_rappeler",
        "a_rappeler": "a_rappeler",
        "rdv": "rdv",
        "deja_servi": "deja_servi",
        "hors_cible": "hors_cible",
        "faux_num": "faux_num",
        "b2b_valide": "b2b_valide",
        "non_fait": "non_fait",
    }
    _NEGATIVE_STATUTS = frozenset(
        {
            "locataire",
            "pas_interesse",
            "pas_projet",
            "dnc",
            "non_qualifie",
            "refus",
            "non",
            "negatif",
        }
    )
    _NEGATIVE_ACTIONS = frozenset(
        {
            "tag_locataire",
            "tag_pas_projet",
            "tag_pas_interesse",
            "tag_dnc",
            "retirer_liste",
        }
    )
    _NEUTRE_STATUTS = frozenset(
        {
            "messagerie",
            "voicemail",
            "rappeler",
            "rappeler_plus_tard",
            "rappel",
        }
    )
    _NEUTRE_ACTIONS = frozenset(
        {
            "tag_rappeler",
            "tag_rappeler_plus_tard",
            "noter_rappel",
        }
    )

    def _effective_duration_sec(self):
        """Durée en secondes : champ stocké ou delta start/end."""
        self.ensure_one()
        secs = self.duration_sec or 0
        if not secs and self.start_at and self.end_at:
            secs = max(0, int((self.end_at - self.start_at).total_seconds()))
        return secs

    @staticmethod
    def _format_duration(secs):
        secs = int(secs or 0)
        if secs <= 0:
            return "—"
        minutes, seconds = divmod(secs, 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            return "%d:%02d:%02d" % (hours, minutes, seconds)
        return "%d:%02d" % (minutes, seconds)

    @api.model
    def _recordings_base_url(self):
        ICP = self.env["ir.config_parameter"].sudo()
        base = (
            ICP.get_param("lea_qc.recordings_base_url")
            or "https://intellixcrm.com/lea-recordings"
        )
        return base.rstrip("/")

    @api.model
    def _normalize_recording_url(self, url, call_sid=None):
        """URL HTTPS jouable (alias nginx /lea-recordings/)."""
        url = (url or "").strip()
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        sid = (call_sid or "").strip()
        base = self._recordings_base_url()
        if url.startswith("/lea-recordings/"):
            return base + url[len("/lea-recordings") :]
        if url.startswith("file://"):
            name = url.rsplit("/", 1)[-1]
            if name.endswith(".wav"):
                return "%s/%s" % (base, name)
            if sid:
                return "%s/%s_0.wav" % (base, sid)
            return ""
        if url.endswith(".wav"):
            return "%s/%s" % (base, url.rsplit("/", 1)[-1])
        if sid and not url.startswith("/"):
            return "%s/%s" % (base, url.lstrip("/"))
        return url

    @api.depends("duration_sec", "start_at", "end_at")
    def _compute_duration_display(self):
        for rec in self:
            rec.duration_display = rec._format_duration(rec._effective_duration_sec())

    @api.depends("phone")
    def _compute_phone_display(self):
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_phone import (
            format_phone_display,
        )

        for rec in self:
            rec.phone_display = format_phone_display(rec.phone)

    def _resolve_lea_phone(self, raw, partner=None):
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_phone import (
            is_garbage_phone,
            resolve_phone,
        )

        partner = partner or self.partner_id
        resolved = resolve_phone(
            raw,
            call_sid=self.call_sid,
            partner_phone=partner.phone if partner else None,
        )
        if resolved:
            return resolved
        if raw and not is_garbage_phone(raw):
            return raw
        return ""

    @api.depends("recording_url")
    def _compute_has_recording(self):
        for rec in self:
            rec.has_recording = bool((rec.recording_url or "").strip())

    @api.model
    def _qualification_keys(self):
        return {key for key, _label in QUALIFICATION_STATUT_SELECTION}

    @api.model
    def _resolve_qualification_statut(
        self,
        payload=None,
        *,
        statut="",
        crm_action="",
        lead_type="",
        connect_outcome="",
        amd_result="",
        qualified=False,
        proprietaire=False,
        intent_positif=False,
    ):
        """Mappe payload Léa / champs existants vers qualification_statut VICIdial."""
        payload = payload or {}
        valid = self._qualification_keys()

        direct = (
            payload.get("qualification_statut")
            or payload.get("qualification")
            or ""
        )
        direct = (direct or "").lower().strip()
        if direct in valid:
            return direct

        action = (
            (payload.get("crm_action") or payload.get("action_crm") or crm_action or "")
            .lower()
            .strip()
        )
        if action in self._CRM_ACTION_QUAL_MAP:
            return self._CRM_ACTION_QUAL_MAP[action]

        raw_statut = (
            payload.get("statut")
            or payload.get("etat_final")
            or statut
            or ""
        )
        raw_statut = (raw_statut or "").lower().strip()
        if raw_statut in self._STATUT_QUAL_MAP:
            return self._STATUT_QUAL_MAP[raw_statut]

        lt = (payload.get("lead_type") or lead_type or "").lower().strip()
        if lt == "locataire":
            return "locataire"
        if lt == "negatif":
            return "pas_interesse"
        if lt == "rappeler":
            return "a_rappeler"

        amd = (payload.get("amd_result") or amd_result or "").lower()
        outcome = (payload.get("connect_outcome") or connect_outcome or "").lower()
        if amd in ("machine", "fax", "not_sure") or outcome == "voicemail":
            return "messagerie"

        is_qualified = bool(
            payload.get("qualified")
            or payload.get("lead_ganador")
            or qualified
            or action == "tag_lead_qualifie"
            or raw_statut in ("qualifie", "qualified", "intent_positif")
            or (
                bool(payload.get("proprietaire") or payload.get("propietario") or proprietaire)
                and bool(
                    payload.get("intention_vente")
                    or payload.get("type_projet")
                    or intent_positif
                )
            )
        )
        if is_qualified:
            return "qualifie"

        if payload.get("etat_suivant") == "rappel" or action == "noter_rappel":
            return "a_rappeler"

        if outcome in ("no_answer", "busy", "invalid") or amd == "invalid":
            return "non_fait"

        return "non_fait"

    @api.model
    def _merge_qualification_statut(self, current, incoming):
        """Ne rétrograde pas une qualification déjà posée (posteurs multiples)."""
        current = current or "non_fait"
        incoming = incoming or "non_fait"
        if current != "non_fait" and incoming == "non_fait":
            return current
        rank = {
            "non_fait": 0,
            "messagerie": 1,
            "a_rappeler": 2,
            "pas_interesse": 3,
            "deja_servi": 3,
            "locataire": 3,
            "dnc": 4,
            "hors_cible": 3,
            "faux_num": 3,
            "qualifie": 5,
            "rdv": 5,
            "b2b_valide": 5,
        }
        if rank.get(incoming, 0) >= rank.get(current, 0):
            return incoming
        return current

    @api.depends(
        "qualified",
        "qualification_statut",
        "connect_outcome",
        "connected",
        "duration_sec",
        "statut",
        "crm_action",
        "lead_type",
    )
    def _compute_call_result_category(self):
        for rec in self:
            qual = rec.qualification_statut or "non_fait"
            if qual in rec._QUAL_POSITIF or rec.qualified:
                rec.call_result_category = "positif"
                continue
            if qual in rec._QUAL_NEGATIF:
                rec.call_result_category = "negatif"
                continue
            if qual in rec._QUAL_NEUTRE:
                rec.call_result_category = "neutre"
                continue

            statut = (rec.statut or "").lower().strip()
            action = (rec.crm_action or "").lower().strip()
            lead_type = (rec.lead_type or "").lower().strip()

            if rec.qualified:
                rec.call_result_category = "positif"
                continue

            if rec.connect_outcome in ("no_answer", "busy", "invalid"):
                rec.call_result_category = "insucces"
                continue

            if (
                rec.connect_outcome == "voicemail"
                or statut in rec._NEUTRE_STATUTS
                or action in rec._NEUTRE_ACTIONS
                or "rappel" in statut
                or lead_type == "rappeler"
            ):
                rec.call_result_category = "neutre"
                continue

            if (
                statut in rec._NEGATIVE_STATUTS
                or action in rec._NEGATIVE_ACTIONS
                or lead_type in ("locataire", "negatif")
            ):
                rec.call_result_category = "negatif"
                continue

            if not rec.connected and (rec.duration_sec or 0) <= 0:
                rec.call_result_category = "insucces"
                continue

            if rec.connected:
                rec.call_result_category = "negatif" if (statut or action) else "neutre"
                continue

            rec.call_result_category = "insucces"

    # ── Agrégats latence / tours ──
    @api.depends(
        "turn_ids.stt_ms",
        "turn_ids.llm_ttft_ms",
        "turn_ids.llm_total_ms",
        "turn_ids.tts_ttfb_ms",
        "turn_ids.tts_total_ms",
        "turn_ids.e2e_ms",
    )
    def _compute_aggregates(self):
        for rec in self:
            turns = rec.turn_ids
            rec.turn_count = len(turns)
            stt = [t.stt_ms for t in turns if t.stt_ms]
            llm_ttft = [t.llm_ttft_ms for t in turns if t.llm_ttft_ms]
            llm_tot = [t.llm_total_ms for t in turns if t.llm_total_ms]
            tts_ttfb = [t.tts_ttfb_ms for t in turns if t.tts_ttfb_ms]
            tts_tot = [t.tts_total_ms for t in turns if t.tts_total_ms]
            e2e = [t.e2e_ms for t in turns if t.e2e_ms]
            rec.stt_ms_p50 = percentile(stt, 50)
            rec.stt_ms_p95 = percentile(stt, 95)
            rec.stt_ms_max = max(stt) if stt else 0.0
            rec.llm_ttft_ms_p50 = percentile(llm_ttft, 50)
            rec.llm_ttft_ms_p95 = percentile(llm_ttft, 95)
            rec.llm_total_ms_p95 = percentile(llm_tot, 95)
            rec.tts_ttfb_ms_p50 = percentile(tts_ttfb, 50)
            rec.tts_ttfb_ms_p95 = percentile(tts_ttfb, 95)
            rec.tts_total_ms_p95 = percentile(tts_tot, 95)
            rec.e2e_ms_p50 = percentile(e2e, 50)
            rec.e2e_ms_p95 = percentile(e2e, 95)
            rec.e2e_ms_max = max(e2e) if e2e else 0.0

    @api.depends(
        "duration_sec",
        "telecom_sec",
        "stt_audio_sec",
        "tts_chars",
        "tts_chars_cacheable",
        "llm_tokens_in",
        "llm_tokens_out",
    )
    def _compute_cost(self):
        prices = self._prices()
        for rec in self:
            telecom_sec = rec.telecom_sec or rec.duration_sec or 0
            rec.cost_telecom = telecom_sec * prices["telecom_per_sec"]
            rec.cost_stt = (rec.stt_audio_sec or 0.0) * prices["deepgram_per_sec"]
            rec.cost_tts = (rec.tts_chars or 0) * prices["elevenlabs_per_char"]
            rec.cost_llm = (
                (rec.llm_tokens_in or 0) * prices["claude_in_per_token"]
                + (rec.llm_tokens_out or 0) * prices["claude_out_per_token"]
            )
            rec.cost_total = (
                rec.cost_telecom + rec.cost_stt + rec.cost_tts + rec.cost_llm
            )
            minutes = (telecom_sec or 0) / 60.0
            rec.cost_per_min = (rec.cost_total / minutes) if minutes else 0.0
            rec.cacheable_pct = (
                100.0 * rec.tts_chars_cacheable / rec.tts_chars
                if rec.tts_chars
                else 0.0
            )

    @api.model
    def _prices(self):
        ICP = self.env["ir.config_parameter"].sudo()
        out = {}
        for key, default in DEFAULT_PRICES.items():
            short = key.rsplit(".", 1)[1]
            try:
                out[short] = float(ICP.get_param(key, default))
            except (TypeError, ValueError):
                out[short] = float(default)
        return out

    # ── Upsert (utilisé par endpoints STT/TTS/LLM et call-ended) ──
    @api.model
    def _get_or_create(self, call_sid, defaults=None):
        call_sid = (call_sid or "").strip()
        if not call_sid:
            call_sid = "_unknown_%s" % fields.Datetime.now().strftime("%Y%m%d%H%M%S%f")
        rec = self.search([("call_sid", "=", call_sid)], limit=1)
        if not rec:
            vals = {
                "call_sid": call_sid,
                "start_at": fields.Datetime.now(),
                "variant": variant_for_sid(call_sid),
            }
            if defaults:
                vals.update(defaults)
            try:
                rec = self.create(vals)
            except Exception:
                # course possible (création concurrente) — relire
                self.env.cr.rollback()
                rec = self.search([("call_sid", "=", call_sid)], limit=1)
        return rec

    @api.model
    def _concurrency_at(self, moment):
        """Nombre de sessions actives à l'instant `moment`."""
        if not moment:
            return 0
        return self.search_count(
            [
                ("start_at", "!=", False),
                ("start_at", "<=", moment),
                "|",
                ("end_at", "=", False),
                ("end_at", ">=", moment),
            ]
        )

    @api.model
    def register_call_ended(self, payload):
        """Point d'entrée appelé par le webhook call-ended Léa."""
        payload = payload or {}
        call_sid = (payload.get("call_sid") or "").strip()
        rec = self._get_or_create(call_sid)
        if not rec:
            return False

        duration = int(payload.get("duration_sec") or payload.get("duration_seconds") or 0)
        # Durée connectée RÉALISTE : on garde la plus grande valeur observée (l'AGI
        # poste désormais l'horloge mur ; le proxy octets de n8n peut arriver d'abord
        # et sous-évaluer). On ne rétrécit jamais une durée déjà enregistrée.
        duration = max(duration, rec.duration_sec or 0)
        amd = (payload.get("amd_result") or "").lower()
        statut = (payload.get("statut") or payload.get("etat_final") or "").lower()
        crm_action = payload.get("crm_action") or ""
        # Signal d'intention vendeur/acheteur exprimée (propriétaire compris).
        proprietaire = bool(payload.get("proprietaire") or payload.get("propietario"))
        besoin = (payload.get("besoin") or "").lower()
        intent_positif = bool(
            payload.get("intention_vente")
            or payload.get("type_projet")
            or besoin in ("reno", "immo", "les_deux")
        )
        # Lead POSITIF (qualifié) = signal explicite (reached CLOSING / lead_ganador)
        # OU propriétaire AYANT exprimé une intention vente/réno. Définition qui reste
        # SIGNIFICATIVE (pas « tout le monde ») et qui ne dépend plus du proxy de durée.
        qualified = bool(
            payload.get("qualified")
            or payload.get("lead_ganador")
            or crm_action == "tag_lead_qualifie"
            or statut in ("qualifie", "qualified", "intent_positif")
            or (proprietaire and intent_positif)
        )
        # On ne RÉTROGRADE jamais un lead déjà qualifié : plusieurs posteurs (n8n via
        # crm_payload PUIS l'AGI) écrivent la même ligne ; un post tardif sans le
        # drapeau ne doit pas effacer une qualification authentique.
        qualified = qualified or bool(rec.qualified)

        transcript = (payload.get("transcript") or "").strip()

        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        conv_payload = {
            **payload,
            "transcript": transcript,
            "duration_sec": duration,
            "amd_result": amd,
        }
        is_conversation = VicidialService(self.env).is_sofia_conversation(conv_payload)

        if amd in ("machine", "fax", "not_sure") or statut in ("messagerie", "voicemail"):
            outcome = "voicemail"
            connected = False
        elif duration <= 0:
            outcome = "no_answer"
            connected = False
        elif not transcript and duration < 25 and not qualified:
            # Ouverture seule / répondeur muet : durée > 0 mais aucune parole STT.
            outcome = "voicemail"
            connected = False
        else:
            outcome = "connected"
            connected = True

        qual_statut = self._merge_qualification_statut(
            rec.qualification_statut,
            self._resolve_qualification_statut(
                payload,
                statut=statut,
                crm_action=crm_action,
                lead_type=payload.get("lead_type") or rec.lead_type or "",
                connect_outcome=outcome,
                amd_result=amd,
                qualified=qualified,
                proprietaire=proprietaire,
                intent_positif=intent_positif,
            ),
        )

        now = fields.Datetime.now()
        start = rec.start_at or now
        # Variante : on fait CONFIANCE à n8n si fourni (même algo partagé), sinon
        # on (re)calcule depuis le call_sid. On ne réécrit jamais une valeur déjà
        # posée à la création pour garder l'assignation stable.
        payload_variant = (payload.get("variant") or "").strip().upper()
        variant = (
            rec.variant
            or (payload_variant if payload_variant in ("A", "B") else "")
            or variant_for_sid(call_sid)
        )
        raw_phone = payload.get("telephone") or payload.get("phone") or rec.phone
        resolved_phone = rec._resolve_lea_phone(raw_phone)
        vals = {
            "agent_id": payload.get("agent_id") or rec.agent_id or "lea-qc-2026",
            "campaign": payload.get("campaign") or rec.campaign or "DW_QCB2C",
            "variant": variant,
            "phone": resolved_phone or raw_phone or rec.phone,
            "prenom": payload.get("prenom") or rec.prenom,
            "call_date": payload.get("call_date") or rec.call_date or start,
            "end_at": now,
            "connected": connected,
            "connect_outcome": outcome,
            "amd_result": amd or rec.amd_result,
            "duration_sec": duration,
            "telecom_sec": duration,
            "qualified": qualified,
            "qualification_statut": qual_statut,
            "statut": statut,
            "crm_action": crm_action,
            "lead_type": payload.get("lead_type") or "",
            "transcript": payload.get("transcript") or rec.transcript,
            "raw_payload": json.dumps(payload, ensure_ascii=False)[:60000],
        }
        if is_conversation:
            normalized_rec = self._normalize_recording_url(
                payload.get("recording_url") or rec.recording_url,
                call_sid=call_sid,
            )
            if normalized_rec:
                vals["recording_url"] = normalized_rec
        if not rec.concurrency_at_start:
            vals["concurrency_at_start"] = self._concurrency_at(start)
        rec.write(vals)
        rec._rollup_units_from_turns()
        # Analyse Claude : jamais synchrone ici (cron / bouton manuel).
        return {"id": rec.id, "call_sid": rec.call_sid, "qualified": qualified}

    def _claude_transcript_ready(self):
        self.ensure_one()
        if (self.transcript or "").strip():
            return True
        return bool(self.turn_ids)

    def action_analyze_claude(self):
        """Bouton formulaire : analyse Claude de l'appel courant."""
        for rec in self:
            rec._run_claude_analysis()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Léa-QC — Analyse Claude",
                "message": "Analyse terminée pour %d appel(s)." % len(self),
                "type": "success",
                "sticky": False,
            },
        }

    def _run_claude_analysis(self):
        """Exécute l'analyse Claude et persiste le résultat (fail-open)."""
        self.ensure_one()
        if not self._claude_transcript_ready():
            return False
        try:
            from odoo.addons.doorway_agents_dashboard.services.lea_qc_ab_analyzer import (
                LeaQcAbAnalyzer,
            )

            result = LeaQcAbAnalyzer(self.env).analyze_call_record(self)
        except Exception as exc:  # pragma: no cover
            _logger.warning("Léa Claude analyse skip call=%s: %s", self.call_sid, exc)
            return False
        if not result or result.get("error"):
            _logger.info(
                "Léa Claude analyse non persistée call=%s: %s",
                self.call_sid,
                result.get("error") if result else "empty",
            )
            return False
        hint = (result.get("variant_winner_hint") or "unclear").lower()
        if hint == "tie":
            hint_val = "tie"
        elif hint in ("a", "b"):
            hint_val = hint.upper()
        else:
            hint_val = "unclear"
        self.write(
            {
                "claude_analysis": result,
                "claude_analyzed_at": fields.Datetime.now(),
                "claude_comprehension_score": result.get("comprehension_score") or 0.0,
                "claude_variant_hint": hint_val,
            }
        )
        return True

    @api.model
    def cron_analyze_pending_claude(self, limit=20):
        """Cron : analyse les appels connectés récents sans analyse Claude."""
        limit = int(limit or 20)
        pending = self.search(
            [
                ("claude_analyzed_at", "=", False),
                ("connect_outcome", "=", "connected"),
                "|",
                ("transcript", "!=", False),
                ("turn_ids", "!=", False),
            ],
            order="call_date desc",
            limit=limit,
        )
        done = 0
        for rec in pending:
            if rec._run_claude_analysis():
                done += 1
        if done:
            _logger.info("[Léa-QC Claude] %d/%d appels analysés", done, len(pending))
        return done

    @api.model
    def action_batch_analyze_claude(self, limit=50):
        """Action serveur : batch analyse des appels en attente."""
        done = self.cron_analyze_pending_claude(limit=limit)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Léa-QC — Batch Claude",
                "message": "%d appel(s) analysé(s)." % done,
                "sticky": True,
                "type": "info",
            },
        }

    def _rollup_units_from_turns(self):
        """Agrège les unités réelles depuis les tours (STT/TTS/LLM)."""
        for rec in self:
            turns = rec.turn_ids
            rec.stt_audio_sec = sum(t.stt_audio_sec or 0.0 for t in turns)
            rec.tts_chars = sum(t.tts_chars or 0 for t in turns)
            rec.tts_chars_cacheable = sum(
                (t.tts_chars or 0)
                for t in turns
                if t.tts_is_scripted or t.tts_cache_hit
            )
            rec.llm_tokens_in = sum(t.llm_tokens_in or 0 for t in turns)
            rec.llm_tokens_out = sum(t.llm_tokens_out or 0 for t in turns)

    # ── Agrégats échantillon (lecture rapide pour la canvas rentabilité) ──
    @api.model
    def sample_aggregates(self, date_from=None, date_to=None):
        domain = []
        if date_from:
            domain.append(("call_date", ">=", date_from))
        if date_to:
            domain.append(("call_date", "<=", date_to))
        calls = self.search(domain)
        total = len(calls)
        connected = calls.filtered("connected")
        qualified = calls.filtered("qualified")
        e2e = []
        stt = []
        for c in calls:
            e2e += [t.e2e_ms for t in c.turn_ids if t.e2e_ms]
            stt += [t.stt_ms for t in c.turn_ids if t.stt_ms]
        cost_total = sum(connected.mapped("cost_total"))
        telecom_min = sum(connected.mapped("telecom_sec")) / 60.0
        tts_chars = sum(calls.mapped("tts_chars"))
        tts_cache = sum(calls.mapped("tts_chars_cacheable"))
        return {
            "calls_total": total,
            "connect_rate": (len(connected) / total) if total else 0.0,
            "avg_duration_connected": (
                sum(connected.mapped("duration_sec")) / len(connected)
                if connected
                else 0.0
            ),
            "qualif_rate": (len(qualified) / len(connected)) if connected else 0.0,
            "e2e_ms_p50": percentile(e2e, 50),
            "e2e_ms_p95": percentile(e2e, 95),
            "stt_ms_p50": percentile(stt, 50),
            "stt_ms_p95": percentile(stt, 95),
            "peak_concurrency": self.get_peak_concurrency(date_from, date_to),
            "blended_cost_per_min": (cost_total / telecom_min) if telecom_min else 0.0,
            "cost_per_qualified": (cost_total / len(qualified)) if qualified else 0.0,
            "cacheable_pct": (100.0 * tts_cache / tts_chars) if tts_chars else 0.0,
            "cost_total": cost_total,
        }

    # ── Agrégats A/B (rentabilité par bras de script) ──
    @api.model
    def _arm_stats(self, calls):
        """Statistiques d'un bras (recordset déjà filtré sur une variante)."""
        total = len(calls)
        connected = calls.filtered("connected")
        qualified = calls.filtered("qualified")
        n_conn = len(connected)
        n_qual = len(qualified)
        cost_total = sum(connected.mapped("cost_total"))
        telecom_min = sum(connected.mapped("telecom_sec")) / 60.0
        blended = (cost_total / telecom_min) if telecom_min else 0.0
        # Coût par lead POSITIF (qualifié) = minutes connectées × $/min / nb qualifiés
        cost_per_positive = ((telecom_min * blended) / n_qual) if n_qual else 0.0
        qualif_rate = (n_qual / n_conn) if n_conn else 0.0
        lo, hi = wilson_interval(n_qual, n_conn) if n_conn else (0.0, 0.0)
        analyzed = calls.filtered("claude_analyzed_at")
        scores = [c.claude_comprehension_score for c in analyzed if c.claude_comprehension_score]
        routing_err_calls = sum(
            1
            for c in analyzed
            if (c.claude_analysis or {}).get("routing_errors")
        )
        quality_flag_calls = sum(
            1
            for c in analyzed
            if (c.claude_analysis or {}).get("quality_flags")
        )
        hint_a = len(analyzed.filtered(lambda c: c.claude_variant_hint == "A"))
        hint_b = len(analyzed.filtered(lambda c: c.claude_variant_hint == "B"))
        return {
            "calls_total": total,
            "connected": n_conn,
            "connect_rate": (n_conn / total) if total else 0.0,
            "qualified": n_qual,
            "qualif_rate": qualif_rate,
            "qualif_rate_ci95": [round(lo, 4), round(hi, 4)],
            "avg_connected_min": (
                (sum(connected.mapped("duration_sec")) / 60.0 / n_conn)
                if n_conn
                else 0.0
            ),
            "connected_min_total": telecom_min,
            "blended_cost_per_min": blended,
            "cost_total": cost_total,
            "cost_per_positive_lead": cost_per_positive,
            "claude_analyzed": len(analyzed),
            "claude_comprehension_avg": (
                sum(scores) / len(scores) if scores else 0.0
            ),
            "claude_routing_error_rate": (
                routing_err_calls / len(analyzed) if analyzed else 0.0
            ),
            "claude_quality_flag_rate": (
                quality_flag_calls / len(analyzed) if analyzed else 0.0
            ),
            "claude_variant_hint_a": hint_a,
            "claude_variant_hint_b": hint_b,
            "insufficient": n_conn < AB_MIN_CONNECTED_PER_ARM,
        }

    @api.model
    def ab_aggregates(self, date_from=None, date_to=None, campaign=None):
        """Comparaison A/B : par bras, le coût par lead POSITIF est le chiffre clé.

        Retourne, pour chaque bras 'A' et 'B' : n appels, taux de connexion,
        taux de qualification (+ IC95 Wilson), minutes connectées moyennes,
        $/min mélangé (unités réelles) et le COÛT PAR LEAD QUALIFIÉ. Plus un
        bloc `delta` (B − A) et une note de confiance (z-test sur la différence
        des taux de qualification + drapeau « échantillon insuffisant »).
        """
        domain = []
        if date_from:
            domain.append(("call_date", ">=", date_from))
        if date_to:
            domain.append(("call_date", "<=", date_to))
        if campaign:
            domain.append(("campaign", "=", campaign))
        calls = self.search(domain)

        arms = {}
        for arm in ("A", "B"):
            arms[arm] = self._arm_stats(calls.filtered(lambda c, a=arm: c.variant == a))

        a, b = arms["A"], arms["B"]
        # z-test (deux proportions) sur la différence de taux de qualification.
        z = None
        p_value_note = "n/a"
        na, nb = a["connected"], b["connected"]
        xa, xb = a["qualified"], b["qualified"]
        if na and nb:
            p_pool = (xa + xb) / (na + nb)
            se = math.sqrt(p_pool * (1 - p_pool) * (1.0 / na + 1.0 / nb))
            if se > 0:
                z = (b["qualif_rate"] - a["qualif_rate"]) / se
        if z is not None:
            if abs(z) >= 1.96:
                p_value_note = "significatif à 95% (|z|≥1.96)"
            elif abs(z) >= 1.64:
                p_value_note = "tendance à 90% (|z|≥1.64)"
            else:
                p_value_note = "non significatif"

        insufficient = a["insufficient"] or b["insufficient"]
        if insufficient:
            confidence_note = (
                "Échantillon insuffisant (< %d connectés/bras) — résultat "
                "indicatif seulement." % AB_MIN_CONNECTED_PER_ARM
            )
        else:
            confidence_note = "Échantillon suffisant. Différence taux qualif : %s." % (
                p_value_note
            )

        def _delta(key):
            return b[key] - a[key]

        # Bras gagnant sur le coût/lead positif (plus bas = mieux), si exploitable.
        winner = None
        if not insufficient and a["qualified"] and b["qualified"]:
            winner = "A" if a["cost_per_positive_lead"] <= b["cost_per_positive_lead"] else "B"

        # Indice Claude (score compréhension moyen par bras, si analysé).
        claude_winner = None
        if a["claude_analyzed"] and b["claude_analyzed"]:
            if a["claude_comprehension_avg"] > b["claude_comprehension_avg"]:
                claude_winner = "A"
            elif b["claude_comprehension_avg"] > a["claude_comprehension_avg"]:
                claude_winner = "B"
            else:
                claude_winner = "tie"

        return {
            "headline_metric": "cost_per_positive_lead",
            "A": a,
            "B": b,
            "delta": {
                "connect_rate": _delta("connect_rate"),
                "qualif_rate": _delta("qualif_rate"),
                "blended_cost_per_min": _delta("blended_cost_per_min"),
                "cost_per_positive_lead": _delta("cost_per_positive_lead"),
                "claude_comprehension_avg": _delta("claude_comprehension_avg"),
                "claude_routing_error_rate": _delta("claude_routing_error_rate"),
            },
            "z_score": round(z, 3) if z is not None else None,
            "winner_cost_per_positive_lead": winner,
            "claude_comprehension_winner": claude_winner,
            "min_connected_per_arm": AB_MIN_CONNECTED_PER_ARM,
            "confidence_note": confidence_note,
        }

    @api.model
    def action_ab_comparison(self):
        """Action serveur : journalise + notifie la comparaison A/B courante."""
        res = self.ab_aggregates()
        a, b = res["A"], res["B"]
        msg = (
            "A/B Léa-QC — coût par lead positif (chiffre clé)\n"
            "  A : %d connectés, qualif %.1f%%, $/min %.4f, $/lead positif %.3f\n"
            "      Claude: %d analysés, score compréh. %.1f/10, err. routing %.0f%%\n"
            "  B : %d connectés, qualif %.1f%%, $/min %.4f, $/lead positif %.3f\n"
            "      Claude: %d analysés, score compréh. %.1f/10, err. routing %.0f%%\n"
            "  Δ qualif (B−A) : %+.1f pts | Δ $/lead positif : %+.3f\n"
            "  Δ score Claude (B−A) : %+.1f | Indice Claude : %s\n"
            "  z=%s — %s"
            % (
                a["connected"], a["qualif_rate"] * 100, a["blended_cost_per_min"],
                a["cost_per_positive_lead"],
                a["claude_analyzed"], a["claude_comprehension_avg"],
                a["claude_routing_error_rate"] * 100,
                b["connected"], b["qualif_rate"] * 100, b["blended_cost_per_min"],
                b["cost_per_positive_lead"],
                b["claude_analyzed"], b["claude_comprehension_avg"],
                b["claude_routing_error_rate"] * 100,
                res["delta"]["qualif_rate"] * 100, res["delta"]["cost_per_positive_lead"],
                res["delta"]["claude_comprehension_avg"],
                res.get("claude_comprehension_winner") or "n/a",
                res["z_score"], res["confidence_note"],
            )
        )
        _logger.info("[Léa-QC A/B] %s", msg)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Léa-QC — Comparaison A/B",
                "message": msg,
                "sticky": True,
                "type": "info",
            },
        }

    @api.model
    def get_peak_concurrency(self, date_from=None, date_to=None):
        """Balayage d'intervalles [start_at, end_at] pour le pic de simultanéité."""
        domain = [("start_at", "!=", False)]
        if date_from:
            domain.append(("call_date", ">=", date_from))
        if date_to:
            domain.append(("call_date", "<=", date_to))
        calls = self.search(domain)
        events = []
        for c in calls:
            start = c.start_at
            end = c.end_at or c.start_at
            events.append((start, 1))
            events.append((end, -1))
        events.sort(key=lambda e: (e[0], -e[1]))
        cur = peak = 0
        for _ts, delta in events:
            cur += delta
            peak = max(peak, cur)
        return peak

    def action_open_recording(self):
        self.ensure_one()
        url = self._normalize_recording_url(self.recording_url, call_sid=self.call_sid)
        if not url:
            return False
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    @api.model
    def backfill_qualification_statut(self):
        """Remplit qualification_statut sur les lignes existantes."""
        pending = self.search(
            [
                "|",
                ("qualification_statut", "=", False),
                ("qualification_statut", "=", "non_fait"),
            ]
        )
        updated = 0
        for rec in pending:
            qual = self._resolve_qualification_statut(
                statut=rec.statut or "",
                crm_action=rec.crm_action or "",
                lead_type=rec.lead_type or "",
                connect_outcome=rec.connect_outcome or "",
                amd_result=rec.amd_result or "",
                qualified=rec.qualified,
            )
            if qual and qual != (rec.qualification_statut or "non_fait"):
                rec.write({"qualification_statut": qual})
                updated += 1
        if updated:
            _logger.info(
                "[Léa-QC] backfill qualification_statut : %d/%d lignes",
                updated,
                len(pending),
            )
        return updated

    def _sync_phone_to_related(self):
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_phone import (
            is_garbage_phone,
        )

        for rec in self:
            if not rec.phone or is_garbage_phone(rec.phone):
                continue
            if rec.partner_id:
                rec.partner_id.sudo().write({"phone": rec.phone})
            if rec.lead_id:
                rec.lead_id.sudo().write({"phone": rec.phone})

    @api.model
    def backfill_qualified_phones(self):
        """Rétro-remplit les téléphones des appels qualifiés (VICIdial + parsing)."""
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_phone import (
            is_garbage_phone,
        )

        calls = self.sudo().search(
            [
                "|",
                ("qualified", "=", True),
                ("qualification_statut", "=", "qualifie"),
            ]
        )
        rows = []
        for rec in calls:
            old = rec.phone or ""
            if old and not is_garbage_phone(old):
                rows.append(
                    {
                        "call_sid": rec.call_sid,
                        "before": old,
                        "after": old,
                        "status": "ok",
                    }
                )
                continue
            resolved = rec._resolve_lea_phone(old)
            if resolved:
                rec.write({"phone": resolved})
                rec._sync_phone_to_related()
                rows.append(
                    {
                        "call_sid": rec.call_sid,
                        "before": old,
                        "after": resolved,
                        "status": "updated",
                    }
                )
            else:
                rows.append(
                    {
                        "call_sid": rec.call_sid,
                        "before": old,
                        "after": "",
                        "status": "unresolved",
                    }
                )
        return rows


class LeaQcTurn(models.Model):
    _name = "lea.qc.turn"
    _description = "Léa-QC — Tour de parole (latence par étape + unités réelles)"
    _order = "call_id, turn_index"

    call_id = fields.Many2one(
        "lea.qc.sample.call", ondelete="cascade", index=True
    )
    call_sid = fields.Char(index=True)
    turn_index = fields.Integer(default=0, index=True)
    ts = fields.Datetime(default=fields.Datetime.now)

    prospect_transcript = fields.Text(string="Transcription prospect")
    bot_text = fields.Text(string="Texte Léa (TTS)")

    # ── STT (Deepgram) — mesuré en direct via l'endpoint Odoo ──
    stt_model = fields.Char(default="nova-2")
    stt_audio_sec = fields.Float(string="Secondes audio STT", digits=(12, 2))
    stt_ms = fields.Float(string="Latence finalisation STT (ms)")
    stt_confidence = fields.Float(digits=(5, 3))

    # ── LLM (Claude) — rempli si la boucle appelle l'endpoint LLM ──
    llm_model = fields.Char()
    llm_tokens_in = fields.Integer()
    llm_tokens_out = fields.Integer()
    llm_ttft_ms = fields.Float(string="LLM time-to-first-token (ms)")
    llm_total_ms = fields.Float(string="LLM total (ms)")

    # ── TTS (ElevenLabs) — rempli si la boucle appelle l'endpoint TTS ──
    tts_model = fields.Char()
    tts_chars = fields.Integer(string="Caractères synthétisés")
    tts_ttfb_ms = fields.Float(string="TTS time-to-first-byte (ms)")
    tts_total_ms = fields.Float(string="TTS total (ms)")
    tts_is_scripted = fields.Boolean(string="Ligne scriptée (fixe)")
    tts_cache_hit = fields.Boolean(string="Déjà synthétisé (cacheable)")
    tts_text_hash = fields.Char(string="Hash texte normalisé", index=True)

    # ── Bout-en-bout : prospect arrête de parler → audio Léa démarre ──
    e2e_ms = fields.Float(string="Latence réponse bout-en-bout (ms)")

    @api.model
    def log_stage(self, call_sid, turn_index, stage, metrics):
        """Upsert d'un tour (par call_sid + turn_index) pour une étape donnée.

        stage ∈ {'stt','llm','tts','e2e'} ; metrics = dict des champs à écrire.
        Jamais bloquant : toute erreur est avalée par l'appelant.
        """
        Call = self.env["lea.qc.sample.call"].sudo()
        call = Call._get_or_create(call_sid)
        turn_index = int(turn_index or 0)
        turn = self.search(
            [("call_id", "=", call.id), ("turn_index", "=", turn_index)], limit=1
        )
        vals = dict(metrics or {})
        if not turn:
            vals.update(
                {
                    "call_id": call.id,
                    "call_sid": call.call_sid,
                    "turn_index": turn_index,
                }
            )
            turn = self.create(vals)
        else:
            turn.write(vals)
        # rollup léger des unités au fil de l'eau
        call._rollup_units_from_turns()
        return turn


class LeaQcScriptedLine(models.Model):
    _name = "lea.qc.scripted.line"
    _description = "Léa-QC — Catalogue des répliques fixes (cacheabilité TTS)"
    _order = "key"

    key = fields.Char(required=True, index=True)
    text = fields.Text(required=True)
    text_hash = fields.Char(index=True)
    voice_id = fields.Char()

    @api.model
    def hash_for(self, text):
        return text_hash(text)

    @api.model
    def is_scripted_hash(self, h):
        return bool(h) and bool(self.search_count([("text_hash", "=", h)]))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("text") and not vals.get("text_hash"):
                vals["text_hash"] = text_hash(vals["text"])
        return super().create(vals_list)
