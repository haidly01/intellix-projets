# -*- coding: utf-8 -*-
"""Prompts et config agents ElevenLabs — relances J+1 / J+3 / J+7 / J+14 (Sophie)."""

RELANCE_AGENT_SPECS = (
    {
        "key": "j1",
        "immo_role": "j1_relance",
        "xmlid": "doorway_agents_dashboard.agent_maison_relance_j1",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_relance_j1",
        "odoo_name": "Maison Recherchée · J+1 Relance",
        "temperature": 0.3,
        "max_tokens": 200,
        "max_duration_seconds": 240,
        "turn_timeout": 7,
        "silence_end_call_timeout": 15,
        "stability": 0.55,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Sophie de Maison Recherchée. "
            "J'essaie de vous rejoindre depuis hier pour votre évaluation marchande. "
            "Avez-vous deux minutes?"
        ),
        "prompt": """Tu es Sophie de Maison Recherchée. Tu rappelles un propriétaire qui n'a pas répondu à ton premier appel hier concernant son évaluation marchande.

CONTEXTE: {{lead_name}}, {{property_address}}, {{days_since_request}}, {{previous_call_attempts}}

OUVERTURE: "Bonjour {{lead_name}}, c'est Sophie de Maison Recherchée. J'essaie de vous rejoindre depuis hier concernant votre demande d'évaluation. Avez-vous deux minutes?"

SI OCCUPÉ: proposer un rappel précis aujourd'hui.

SI DISPONIBLE: confirmer que la demande est active, proposer un appel de 15 min avec un courtier cette semaine (demain 10h ou après-midi 14h).

OBJECTIF J+1: fixer rendez-vous ou date de rappel — NE PAS re-qualifier complètement.
DURÉE MAX: 3 minutes. Ton léger, pas insistant. Jamais parler de prix.""",
    },
    {
        "key": "j3",
        "immo_role": "j3_relance",
        "xmlid": "doorway_agents_dashboard.agent_maison_relance_j3",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_relance_j3",
        "odoo_name": "Maison Recherchée · J+3 Relance",
        "temperature": 0.4,
        "max_tokens": 250,
        "max_duration_seconds": 300,
        "turn_timeout": 8,
        "silence_end_call_timeout": 18,
        "stability": 0.5,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Sophie de Maison Recherchée. "
            "J'ai une information intéressante sur le marché dans votre secteur. "
            "Vous avez deux minutes?"
        ),
        "prompt": """Tu es Sophie de Maison Recherchée. Deuxième tentative — angle valeur marché local.

CONTEXTE: {{lead_name}}, {{property_address}}, {{neighborhood}}, {{market_insight}}

OUVERTURE: partager une info concrète sur le secteur (utiliser {{market_insight}} si fourni).

TRANSITION: proposer d'envoyer l'évaluation gratuite cette semaine. Mini-qualification max 2 questions si intéressé.

SI PAS INTÉRESSÉ: accepter gracieusement, tag mental warm-nurture-passif.

DURÉE MAX: 4 minutes. Réciprocité — donner avant demander. Ne jamais paraître désespéré.""",
    },
    {
        "key": "j7",
        "immo_role": "j7_relance",
        "xmlid": "doorway_agents_dashboard.agent_maison_relance_j7",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_relance_j7",
        "odoo_name": "Maison Recherchée · J+7 Relance",
        "temperature": 0.35,
        "max_tokens": 200,
        "max_duration_seconds": 240,
        "turn_timeout": 7,
        "silence_end_call_timeout": 15,
        "stability": 0.5,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Sophie de Maison Recherchée. "
            "Je vous appelle une dernière fois pour votre évaluation marchande. "
            "Je ne voulais pas que votre dossier reste sans suite!"
        ),
        "prompt": """Tu es Sophie. Dernière tentative d'appel actif — ton chaleureux, légère urgence naturelle.

CONTEXTE: {{lead_name}}, {{days_since_request}}, {{previous_attempts}}

OUVERTURE: dernier appel concernant l'évaluation de X jours — ton léger sur "dossier sans suite".

SI OUI: 2 questions max + appel courtier CETTE SEMAINE.
SI PROJET REPORTÉ: noter délai, nurture programmé.
SI PLUS INTÉRESSÉ: fermeture propre, arrêter relances.

DURÉE MAX: 3 minutes. Refus clair = arrêt immédiat. "Pas pour l'instant" = nurture 60-90 jours.""",
    },
    {
        "key": "j14",
        "immo_role": "j14_relance",
        "xmlid": "doorway_agents_dashboard.agent_maison_relance_j14",
        "icp_param": "doorway_agents_dashboard.elevenlabs_agent_id_relance_j14",
        "odoo_name": "Maison Recherchée · J+14 Re-engagement",
        "temperature": 0.5,
        "max_tokens": 200,
        "max_duration_seconds": 240,
        "turn_timeout": 8,
        "silence_end_call_timeout": 20,
        "stability": 0.5,
        "first_message": (
            "Bonjour {{lead_name}}, c'est Sophie de Maison Recherchée. "
            "On s'était parlé il y a quelques semaines pour votre évaluation marchande. "
            "Je voulais juste prendre des nouvelles!"
        ),
        "prompt": """Tu es Sophie. Re-engagement consultatif — pas commercial.

CONTEXTE: {{lead_name}}, {{property_address}}, {{season}}, {{market_update}}

OUVERTURE: prendre des nouvelles sans pression.

OFFRE: rapport de marché {{season}} pour le secteur — envoi par texto si OUI.

DURÉE MAX: 3 minutes. Ne jamais mentionner le nombre de tentatives. Appel frais et naturel.""",
    },
)

# Templates SMS / WhatsApp (n8n — variables {{first_name}}, etc.)
IMMO_RELANCE_MESSAGES = {
    "sms_j0_30min": (
        "Bonjour {{first_name}}! 👋\n\n"
        "Je viens d'essayer de vous joindre concernant votre évaluation marchande gratuite.\n\n"
        "Répondez simplement OUI ici et je vous rappelle dans les prochaines minutes!\n\n"
        "— Sophie, Maison Recherchée."
    ),
    "wa_j0_4h": (
        "Bonjour {{first_name}} 😊\n\n"
        "Votre demande d'évaluation marchande est bien reçue!\n\n"
        "Quel est le meilleur moment pour vous appeler cette semaine?\n\n"
        "☐ Matin (8h-12h)\n☐ Après-midi (12h-17h)\n☐ Soir (17h-20h)\n\n"
        "Répondez avec votre préférence!\n\n— Sophie, Maison Recherchée."
    ),
    "sms_j1": (
        "Bonjour {{first_name}}!\n\n"
        "💡 Les propriétés dans votre secteur se vendent en moyenne en {{market_days}} jours.\n\n"
        "Votre évaluation gratuite vous donne une fourchette précise.\n\n"
        "Disponible pour un appel rapide aujourd'hui?\n\n— Agence Doorway"
    ),
    "wa_j3": (
        "Bonjour {{first_name}} 🏡\n\n"
        "Cette semaine, on a aidé des propriétaires du secteur {{neighborhood}}.\n\n"
        "✅ Évaluation en 24h\n✅ Ventes comparables\n✅ Estimation nette\n\n"
        "Gratuit et sans engagement. On fixe ça cette semaine?"
    ),
    "sms_j5": (
        "Bonjour {{first_name}},\n\n"
        "Le marché {{season}} est actif dans votre secteur.\n\n"
        "On a de la disponibilité cette semaine pour votre évaluation.\n\n"
        "— Sophie, Maison Recherchée. 📞"
    ),
    "wa_j7": (
        "Bonjour {{first_name}},\n\n"
        "Dernier message 😊 — votre dossier d'évaluation expire dans 48h. "
        "Répondez OUI pour le garder actif.\n\n— Sophie, Maison Recherchée."
    ),
    "sms_j14": (
        "Bonjour {{first_name}} 👋\n\n"
        "Notre rapport de marché {{season}} pour votre secteur est prêt.\n\n"
        "Répondez OUI 📊 — Maison Recherchée."
    ),
    "sms_j30": (
        "Bonjour {{first_name}},\n\n"
        "Votre dossier sera archivé cette semaine. "
        "Écrivez RÉACTIVER pour reprendre.\n\n— Équipe Maison Recherchée. 🏡"
    ),
}

# n8n — mapping relance_number → agent ICP key
RELANCE_NUMBER_TO_KEY = {1: "j1", 2: "j3", 3: "j7", 4: "j14"}
RELANCE_OPTIMAL_HOUR = {1: 10, 2: 10, 3: 16, 4: 10}
