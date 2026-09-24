/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function pct(rate) {
    if (rate === null || rate === undefined) {
        return "—";
    }
    return `${Math.round(rate * 1000) / 10} %`;
}

class IntellixFinanceDashboard extends Component {
    static template = "intellix_finance.FinanceDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: "",
            tab: "itex",
            province: "",
            lang: "",
            provinces: [
                { key: "AB", label: "Alberta" },
                { key: "BC", label: "Colombie-Britannique" },
                { key: "MB", label: "Manitoba" },
                { key: "NB", label: "Nouveau-Brunswick" },
                { key: "NL", label: "Terre-Neuve-et-Labrador" },
                { key: "NS", label: "Nouvelle-Écosse" },
                { key: "NT", label: "Territoires du Nord-Ouest" },
                { key: "NU", label: "Nunavut" },
                { key: "ON", label: "Ontario" },
                { key: "PE", label: "Île-du-Prince-Édouard" },
                { key: "QC", label: "Québec" },
                { key: "SK", label: "Saskatchewan" },
                { key: "YT", label: "Yukon" },
            ],
            stats: {
                itex: {},
                driven: {},
                growth_capital: {},
                targets: { approval_rate: 0.3, cycle_min_days: 30, cycle_max_days: 90 },
            },
        });
        onWillStart(() => this.refresh());
    }

    pct(rate) {
        return pct(rate);
    }

    async refresh() {
        const firstLoad = !this.state.stats || this.state.loading;
        if (firstLoad) {
            this.state.loading = true;
        }
        this.state.error = "";
        try {
            const stats = await this.orm.call("crm.lead", "get_finance_dashboard_stats", [], {
                province: this.state.province || false,
                lang: this.state.lang || false,
            });
            const emptyBrand = {
                name: "—",
                stages: [],
                conversions: [],
                loss: {},
                segments: { by_province: [], by_lang: [] },
            };
            this.state.stats = {
                itex: {
                    segments: { by_province: [], by_lang: [] },
                    stages: [],
                    conversions: [],
                    silence: {},
                    documentary: {},
                    ...((stats && stats.itex) || {}),
                },
                driven: { ...emptyBrand, ...((stats && stats.driven) || {}) },
                growth_capital: { ...emptyBrand, ...((stats && stats.growth_capital) || {}) },
                targets: (stats && stats.targets) || this.state.stats.targets,
            };
            if (stats && stats.filters && Array.isArray(stats.filters.provinces)) {
                this.state.provinces = stats.filters.provinces;
            }
        } catch (e) {
            this.state.error = (e && e.message) || "Erreur de chargement";
        } finally {
            this.state.loading = false;
        }
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    onProvinceChange(ev) {
        this.state.province = ev.target.value || "";
        this.refresh();
    }

    onLangChange(ev) {
        this.state.lang = ev.target.value || "";
        this.refresh();
    }

    async openFunnel(brand) {
        const xmlid =
            brand === "growth_capital"
                ? "intellix_finance.action_finance_funnel_growth"
                : "intellix_finance.action_finance_funnel_driven";
        await this.action.doAction(xmlid);
    }

    async openNotQualified(brand) {
        const xmlid =
            brand === "growth_capital"
                ? "intellix_finance.action_finance_not_qualified_growth"
                : "intellix_finance.action_finance_not_qualified_driven";
        await this.action.doAction(xmlid);
    }

    async openItex() {
        await this.action.doAction("intellix_finance.action_finance_itex_leads");
    }
}

registry.category("actions").add("intellix_finance_dashboard", IntellixFinanceDashboard);
