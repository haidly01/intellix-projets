/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class CoinsPartenairesDashboard extends Component {
    static template = "coins_marocain_partenariats.PartenairesDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            error: "",
            period: 30,
            stats: {},
        });
        onWillStart(() => this.refresh());
    }

    async setPeriod(days) {
        this.state.period = days;
        await this.refresh();
    }

    async refresh() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const stats = await this.orm.call(
                "coins.entente",
                "get_live_dashboard_stats",
                [],
                { period_days: this.state.period }
            );
            this.state.stats = stats || {};
        } catch (e) {
            this.state.error = (e && e.message) || "Erreur de chargement";
            this.state.stats = {
                members_active: 0,
                crm_opportunities: 0,
                sale_orders: 0,
                categories: [],
            };
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("coins_partenaires_dashboard", CoinsPartenairesDashboard);
