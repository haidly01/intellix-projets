/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class CoinsEquipeKpiDashboard extends Component {
    static template = "coins_marocain_partenariats.EquipeKpiDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            error: "",
            period: "day",
            commercialId: 0,
            data: {},
        });
        onWillStart(() => this.refresh());
    }

    async setPeriod(period) {
        this.state.period = period;
        await this.refresh();
    }

    async setCommercial(ev) {
        this.state.commercialId = parseInt(ev.target.value || "0", 10) || 0;
        await this.refresh();
    }

    async refresh() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "coins.partenariat.kpi.daily",
                "get_equipe_kpi",
                [],
                {
                    period: this.state.period,
                    commercial_id: this.state.commercialId || false,
                }
            );
            this.state.data = data || {};
        } catch (e) {
            this.state.error = (e && e.message) || "Erreur de chargement";
            this.state.data = {};
        } finally {
            this.state.loading = false;
        }
    }

    ratio(actual, target) {
        const a = Number(actual || 0);
        const t = Number(target || 0);
        if (!t) {
            return "0 / 0";
        }
        return `${a} / ${t}`;
    }

    barPct(actual, target) {
        const a = Number(actual || 0);
        const t = Number(target || 0);
        if (!t) {
            return 0;
        }
        return Math.min(100, Math.round((100.0 * a) / t));
    }
}

registry.category("actions").add("coins_equipe_kpi_dashboard", CoinsEquipeKpiDashboard);
