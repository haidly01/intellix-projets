# -*- coding: utf-8 -*-
"""Messages campagne IntelliX — WhatsApp / SMS (templates Meta à soumettre)."""

OPT_OUT = "\n\nRépondez STOP pour ne plus recevoir de messages."


def message_j0(company_name, agent_name="l'équipe IntelliX"):
    name = company_name or "Bonjour"
    return (
        "Bonjour %s 👋\n\n"
        "Je suis %s de *IntelliX CRM* — plateforme call center et agents IA "
        "pour les centres de contact.\n\n"
        "Offre *démo exclusive* ce mois-ci :\n"
        "✅ Appels illimités France 🇫🇷 Espagne 🇪🇸 Canada 🇨🇦\n"
        "✅ Agents IA vocaux 24h/24\n"
        "✅ Leads qualifiés dans votre CRM\n"
        "✅ Campagnes SMS + WhatsApp automatisées\n"
        "✅ *Prix cassé* — offre démo limitée\n\n"
        "15 minutes cette semaine pour voir la plateforme ?\n"
        "Répondez *OUI* pour recevoir un lien de démo 🎯"
        % (name, agent_name)
    ) + OPT_OUT


def message_j2(company_name):
    return (
        "Bonjour 👋 Je reviens vers vous concernant IntelliX.\n\n"
        "Des call centers au Maroc et en Tunisie utilisent déjà notre plateforme pour :\n"
        "📞 Appeler France/Canada sans limite\n"
        "🤖 Déployer des agents IA\n"
        "📊 Recevoir des leads pré-qualifiés\n\n"
        "Notre promo démo se termine bientôt.\n"
        "Répondez *OUI* pour une démo en 24h."
    ) + OPT_OUT


def message_j5(company_name):
    ent = company_name or "votre entreprise"
    return (
        "Dernier message 🙏\n\n"
        "%s, notre offre IntelliX expire cette semaine.\n"
        "Démo 15 min sans engagement : répondez *DÉMO*.\n"
        "Sinon bonne continuation 👌"
        % ent
    ) + OPT_OUT


def message_sms_fallback():
    return (
        "IntelliX CRM — call center + agents IA. "
        "Appels illimités FR/ES/CA, leads qualifiés, prix cassé. "
        "Démo gratuite cette semaine. Répondez OUI."
    )


def message_qualified_demo(booking_url, contact_name=""):
    prenom = contact_name or "!"
    url = booking_url or "https://intellixcrm.com"
    return (
        "Super ! 🎉 Merci %s.\n\n"
        "Réservez votre démo IntelliX (20 min) :\n"
        "👉 %s\n\n"
        "Ou indiquez votre disponibilité (jour + heure) et le meilleur numéro."
        % (prenom, url)
    )
