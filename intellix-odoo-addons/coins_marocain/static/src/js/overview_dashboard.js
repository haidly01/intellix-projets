/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Tableau de bord global Coins Marocain.
 * Front OWL reconstruit pour consommer coins.overview.get_dashboard_data
 * (contrat restauré depuis le .pyc d'origine — UI JS/XML perdues le 31/07/2026).
 */
class CoinsOverviewDashboard extends Component {
    static template = "coins_marocain.overview_dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            data: null,
        });
        onWillStart(async () => {
            try {
                this.state.data = await this.orm.call(
                    "coins.overview",
                    "get_dashboard_data",
                    []
                );
            } catch (err) {
                this.state.error = (err && err.message) || String(err);
            } finally {
                this.state.loading = false;
            }
        });
    }

    openVoyageursSansCoord() {
        this.action.doAction(
            "coins_marocain_partenariats.action_pipeline_coins_voyageurs",
            { additionalContext: { search_default_filter_sans_tel: 1 } }
        );
    }

    formatMoney(value, symbol) {
        const n = Number(value || 0);
        const formatted = n.toLocaleString("fr-FR", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
        return `${formatted} ${symbol || "MAD"}`;
    }
}

registry.category("actions").add("coins_overview_dashboard", CoinsOverviewDashboard);
