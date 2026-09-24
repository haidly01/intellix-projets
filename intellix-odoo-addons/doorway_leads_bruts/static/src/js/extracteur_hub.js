/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const LEAD_TYPES = [
    {
        id: "configurateur",
        title: "Campagne automatisée",
        description:
            "Configurez une campagne d'extraction no-code en 4 étapes : ciblage, sources recommandées par l'IA, estimation tarifaire, puis génération automatique d'un workflow n8n.",
        color: "#6c63ff",
        icon: "fa-magic",
        action: "doorway_leads_bruts.action_extracteur_configurateur",
    },
    {
        id: "raw",
        title: "Leads bruts",
        description:
            "Extrayez des contacts B2B depuis 23+ sources (Pages Jaunes, Google Maps, Kompass…). Idéal pour alimenter vos campagnes rapidement.",
        color: "#34a8ff",
        icon: "fa-check",
        action: "doorway_leads_bruts.action_extraction_wizard",
    },
    {
        id: "enriched",
        title: "Leads enrichis",
        description:
            "Contacts complétés avec données firmographiques (adresse, secteur, effectifs). Enrichissement Melissa — prochainement disponible.",
        color: "#7F77DD",
        icon: "fa-check",
        action: "doorway_leads_bruts.action_leads_enriched_list",
        notify: "L'enrichissement Melissa sera bientôt disponible. Consultez vos leads en cours d'enrichissement.",
    },
    {
        id: "qualified",
        title: "Leads qualifiés",
        description:
            "Leads qualifiés par nos agents IA (Sofia, Léa). Assignez des milliers de contacts et lancez une campagne Africa-Con automatiquement.",
        color: "#ff9f33",
        icon: "fa-shield",
        action: "doorway_leads_bruts.action_leads_qualified_list",
        secondaryAction: "doorway_leads_bruts.action_ia_campaign_wizard",
        secondaryLabel: "🚀 Lancer campagne IA",
    },
];

class ExtracteurHub extends Component {
    static template = "doorway_leads_bruts.ExtracteurHub";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.cards = LEAD_TYPES;
        this.onSelect = this.onSelect.bind(this);
        this.onSecondaryAction = this.onSecondaryAction.bind(this);
    }

    async onSelect(card) {
        if (card.notify) {
            this.notification.add(card.notify, { type: "info" });
        }
        await this.action.doAction(card.action);
    }

    async onSecondaryAction(card) {
        await this.action.doAction(card.secondaryAction);
    }
}

registry.category("actions").add("extracteur_hub_action", ExtracteurHub);
