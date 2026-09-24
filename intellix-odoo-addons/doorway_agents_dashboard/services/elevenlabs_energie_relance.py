# -*- coding: utf-8 -*-
"""Agents ElevenLabs relance — Énergie Pro (J+1, J+3, J+7)."""

RELANCE_ENERGIE_SPECS = (
    {
        "key": "j1",
        "energie_role": "j1_relance",
        "xmlid": "doorway_agents_dashboard.agent_energie_relance_j1",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_energie_j1",
        "odoo_name": "Énergie Pro · J+1 Relance",
        "temperature": 0.35,
        "max_tokens": 200,
        "max_duration_seconds": 150,
        "turn_timeout": 6,
        "silence_end_call_timeout": 12,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Alex de Doorway Énergie. "
            "J'avais essayé de vous joindre hier pour votre projet. "
            "C'est un meilleur moment?"
        ),
        "prompt": """Tu es Alex de Doorway Énergie. Relance J+1 — objectif: fixer rappel ou qualifier en 90 secondes.
Site: {{lead_site}}. Projet: {{project_type}}.
MAX 2 minutes. Transfert +14389929200 si intéressé et disponible.""",
    },
    {
        "key": "j3",
        "energie_role": "j3_relance",
        "xmlid": "doorway_agents_dashboard.agent_energie_relance_j3",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_energie_j3",
        "odoo_name": "Énergie Pro · J+3 Relance",
        "temperature": 0.4,
        "max_tokens": 220,
        "max_duration_seconds": 180,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Alex de Doorway Énergie. "
            "Je voulais vous partager un calcul rapide de subventions pour votre projet. "
            "Vous avez deux minutes?"
        ),
        "prompt": """Tu es Alex. Relance J+3 — angle subvention selon source:
Thermopompe: mazout/propane = jusqu'à 11 000 $ potentiels.
Isolation: évaluation Rénoclimat = porte d'entrée subventions.
Fenêtres: 150 $ par ouverture Rénoclimat.
MAX 2-3 min. Transfert si hot.""",
    },
    {
        "key": "j7",
        "energie_role": "j7_relance",
        "xmlid": "doorway_agents_dashboard.agent_energie_relance_j7",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_energie_j7",
        "odoo_name": "Énergie Pro · J+7 Fermeture",
        "temperature": 0.35,
        "max_tokens": 180,
        "max_duration_seconds": 150,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Alex de Doorway Énergie. "
            "Je vous appelle une dernière fois pour votre dossier. "
            "C'est toujours d'actualité?"
        ),
        "prompt": """Tu es Alex. Dernière relance J+7.
SI OUI → qualifier et transférer +14389929200.
SI NON → fermeture propre, arrêter relances.
SI reporté → noter délai rappel.
MAX 2 minutes.""",
    },
)
