# Maison Recherchée — agents immo (sans confusion)

## Règle d’or

Ne **jamais** choisir un agent par `name ilike 'Maison Recherchée'` : tous les profils de la séquence partagent la marque.

Utiliser **`immo_agent_role`** ou le xmlid **`agent_maison_recherchee`**.

## Profils Odoo (séquence Meta)

| Rôle (`immo_agent_role`) | Nom affiché | Xmlid | Usage |
|--------------------------|-------------|-------|--------|
| `j0_qualification` | Maison Recherchée · J+0 Qualification | `agent_maison_recherchee` | Appel J+0 Meta, CRM défaut |
| `j1_relance` | Maison Recherchée · J+1 Relance | `agent_maison_relance_j1` | n8n relance #1 |
| `j3_relance` | Maison Recherchée · J+3 Relance | `agent_maison_relance_j3` | n8n relance #2 |
| `j7_relance` | Maison Recherchée · J+7 Relance | `agent_maison_relance_j7` | n8n relance #3 |
| `j14_relance` | Maison Recherchée · J+14 Re-engagement | `agent_maison_relance_j14` | n8n relance #4 |

## Code Python

```python
agent = env["doorway.agent.profile"].get_maison_immo_qualification_profile()
```

Meta webhook : `renovation.meta.immo.webhook._default_maison_agent()` appelle la même méthode.

## ICP ElevenLabs

| Clé | Rôle |
|-----|------|
| `doorway_agents_dashboard.elevenlabs_agent_id_immo` | J+0 |
| `…_relance_j1` / `j3` / `j7` / `j14` | Relances |

Nom ConvAI côté ElevenLabs : **Sophie — Qualification Immo Doorway** (API) — peut différer du nom Odoo.

## Boutons Odoo

**Setup ElevenLabs (Sophie)** et **Setup relances** : visibles uniquement si `immo_agent_role = j0_qualification`.

## Anciens profils

Ids 22, 28, 32 et doublons (ex. second profil « Sophie — Qualification ») : **inactifs** après upgrade / `_post_init_maison_recherchee`.

## Meta Ads

`renovation_conciergerie.meta_immo_reference_ad_id` = ID pub attendu ; le webhook renvoie `warnings` si `ad_id` différent.
