/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function isoDate(d) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function defaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 29);
    return { dateFrom: isoDate(from), dateTo: isoDate(to) };
}

function ensureFonts() {
    if (document.getElementById("reno-ix-fonts")) {
        return;
    }
    const link = document.createElement("link");
    link.id = "reno-ix-fonts";
    link.rel = "stylesheet";
    link.href =
        "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap";
    document.head.appendChild(link);
}

class RenoImmobilierDashboard extends Component {
    static template = "reno_immobilier.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        const range = defaultRange();
        this.state = useState({
            loading: true,
            error: "",
            dateFrom: range.dateFrom,
            dateTo: range.dateTo,
            showAllPartners: false,
            data: {},
        });
        onWillStart(async () => {
            ensureFonts();
            await this.refresh();
        });
    }

    get data() {
        return this.state.data || {};
    }

    get visiblePartners() {
        const cards = this.data.partners || [];
        const preview = this.data.partners_preview || 4;
        if (this.state.showAllPartners) {
            return cards;
        }
        return cards.slice(0, preview);
    }

    kpiClass(value) {
        return Number(value || 0) === 0 ? "kpi-value zero" : "kpi-value";
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value || this.state.dateFrom;
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value || this.state.dateTo;
    }

    showMorePartners() {
        this.state.showAllPartners = true;
    }

    async refresh() {
        const firstLoad = !this.state.data || !this.state.data.kpis;
        if (firstLoad) {
            this.state.loading = true;
        }
        this.state.error = "";
        try {
            const data = await this.orm.call(
                "reno.immobilier.dashboard",
                "get_dashboard_payload",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                }
            );
            this.state.data = data || {};
            this.state.showAllPartners = false;
            if (data && data.date_from) {
                this.state.dateFrom = data.date_from;
            }
            if (data && data.date_to) {
                this.state.dateTo = data.date_to;
            }
        } catch (e) {
            this.state.error = (e && e.message) || "Impossible de charger le tableau de bord.";
            this.state.data = this.state.data || {};
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("reno_immobilier_dashboard", RenoImmobilierDashboard);
