# Léa QC — Roadmap objections

## Phase 1 (2026-06-13) — Incrémental regex

- Fichier de référence : `objections_library.yaml` (26 nœuds brief + statut implemented/partial/future)
- Détection : `detectIntent` regex post-`normTranscript` dans `lib/conversation_sofia_process.js`
- Top 10 fréquence : soft PI, pas le temps v2, locataire info, qui êtes-vous, arnaque, rappeler plus tard, sonder_futur, entrepreneur
- **Gelé** : greeting actuel, arbre GREETING→CLOSING, campagne DW_QCB2C, voix Sophie

## Phase 2 — Claude classificateur (INCONNU seulement)

**Pas** de Claude par tour (latence/stabilité). Quand `intent === 'incertain'` après regex :

1. Appel Claude API avec prompt court (voir brief §7)
2. Si `confidence >= 0.6` → router vers `node_id` YAML
3. Sinon → `lea_fallback` (comportement actuel)

Prérequis : métriques Phase 1 sur volume réel, golden transcripts élargis, coût/latence budgetés.

## Phase 3 — Automatisations brief non intégrées

- SMS (INFO, LIEN_SITE, CONFIRMATION) via Twilio/n8n
- Activités Odoo J3/J30/J90/S1AN
- PITCH_SUBVENTIONS clip dédié + branche post-soft-PI
- Campagne SE_RENO_QC / arbre 9 nœuds (hors DW_QCB2C)
