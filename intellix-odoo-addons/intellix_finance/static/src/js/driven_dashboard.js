/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class IntellixDrivenDashboard extends Component {
    static template = "intellix_finance.DrivenDashboard";
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
                "crm.lead",
                "get_driven_dashboard_stats",
                [],
                { period_days: this.state.period }
            );
            this.state.stats = stats || {};
        } catch (e) {
            this.state.error = (e && e.message) || "Erreur de chargement";
            this.state.stats = {
                leads_period: 0,
                interested: 0,
                qualified: 0,
                callbacks: 0,
                stages: [],
                sources: [],
                recent_leads: [],
            };
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("intellix_finance_driven_dashboard", IntellixDrivenDashboard);
