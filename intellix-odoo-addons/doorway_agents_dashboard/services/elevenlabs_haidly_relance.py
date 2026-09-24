# -*- coding: utf-8 -*-
"""Agents ElevenLabs relance — Haidly (J+1, J+3, J+7, J+14)."""

RELANCE_HAIDLY_SPECS = (
    {
        "key": "j1",
        "haidly_role": "j1_relance",
        "xmlid": "doorway_agents_dashboard.agent_haidly_relance_j1",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j1",
        "odoo_name": "Haidly · J+1 Relance",
        "temperature": 0.5,
        "max_tokens": 220,
        "max_duration_seconds": 150,
        "stability": 0.42,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Haidly de SoumissionEntrepreneurs! "
            "J'ai regardé des idées pour votre projet et j'avais une question rapide. "
            "Vous avez deux minutes?"
        ),
        "prompt": """Tu es Haidly. Relance J+1 — obtenir photos via soumissionentrepreneurs.com ou intérêt plans 3D.
Variables: {{lead_name}}, {{project_type}}, {{city}}. Max 2 min.""",
    },
    {
        "key": "j3",
        "haidly_role": "j3_relance",
        "xmlid": "doorway_agents_dashboard.agent_haidly_relance_j3",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j3",
        "odoo_name": "Haidly · J+3 Relance",
        "temperature": 0.52,
        "max_tokens": 240,
        "max_duration_seconds": 180,
        "stability": 0.42,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Haidly! "
            "J'ai une info sur les aides pour votre projet. Vous avez deux minutes?"
        ),
        "prompt": """Tu es Haidly. Relance J+3 — angle subvention selon projet (Rénoclimat, CIRHM, CIAD, plans 3D, patio saison).
Max 2-3 min. Transfert si hot.""",
    },
    {
        "key": "j7",
        "haidly_role": "j7_relance",
        "xmlid": "doorway_agents_dashboard.agent_haidly_relance_j7",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j7",
        "odoo_name": "Haidly · J+7 Fermeture",
        "temperature": 0.48,
        "max_tokens": 200,
        "max_duration_seconds": 150,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Haidly de SoumissionEntrepreneurs. "
            "Je voulais pas laisser votre dossier sans nouvelles — c'est toujours d'actualité?"
        ),
        "prompt": """Tu es Haidly. Dernière relance active J+7. OUI → qualifier + transfert. NON → fermeture propre.
Max 2 min.""",
    },
    {
        "key": "j14",
        "haidly_role": "j14_relance",
        "xmlid": "doorway_agents_dashboard.agent_haidly_relance_j14",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j14",
        "odoo_name": "Haidly · J+14 Re-engagement",
        "temperature": 0.55,
        "max_tokens": 200,
        "max_duration_seconds": 150,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Haidly! "
            "Je pensais à votre projet — une petite info qui pourrait vous intéresser. "
            "Deux minutes?"
        ),
        "prompt": """Tu es Haidly. Re-engagement consultatif J+14, pas de pression. Info saison/tendance/subvention.
Max 2 min.""",
    },
)
