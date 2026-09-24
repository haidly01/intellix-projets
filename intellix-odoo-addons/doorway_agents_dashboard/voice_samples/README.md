# Échantillon voix — Sophie (Maison Recherchée)

Placez le fichier audio ici :

```
Rue_Ibnou_Jahir_3.m4a
```

Puis dans Odoo : **Agents IA → Maison Recherchée · J+0 Qualification → Setup ElevenLabs (Sophie)**

Voir `doc/MAISON_IMMO_AGENTS.md` pour les rôles J+0 / relances.

Ou en CLI :

```bash
export ELEVENLABS_API_KEY=sk_...
python3 /odoo/custom/addons/doorway_agents_dashboard/scripts/setup_elevenlabs_maison_immo.py
```

Le script génère `elevenlabs_ids.json` avec `voice_id` et `agent_id`.
