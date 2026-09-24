/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function rpcErrorMessage(err) {
    return (
        err?.data?.message ||
        err?.data?.arguments?.[0] ||
        err?.message ||
        "Erreur inconnue."
    );
}

const TREND_ICON = {
    up: { icon: "fa-arrow-up", cls: "ix-perf-trend--up" },
    down: { icon: "fa-arrow-down", cls: "ix-perf-trend--down" },
    stable: { icon: "fa-minus", cls: "ix-perf-trend--stable" },
};

const SENTIMENT_CLS = {
    positif: "ix-perf-sent--pos",
    neutre: "ix-perf-sent--neu",
    "négatif": "ix-perf-sent--neg",
};

class PerformanceDashboard extends Component {
    static template = "doorway_agents_dashboard.PerformanceDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            view: "list",
            loading: true,
            agents: [],
            pipelines: [],
            filters: {
                pipeline: "",
                agent_type: "",
                language: "",
                campaign_id: "",
                status: "",
                period_days: 7,
            },
            campaigns: [],
            languages: [],
            selectedAgentId: null,
            detail: null,
            callPage: 1,
            periodDays: 30,
            expandedCall: null,
            analyzing: false,
            detailError: null,
        });
        onMounted(() => this.bootstrap());
    }

    get initialAgentId() {
        const params = this.props.action?.params || {};
        const ctx = this.props.action?.context || {};
        return params.agent_id || ctx.default_agent_id || null;
    }

    async bootstrap() {
        const agentId = parseInt(this.initialAgentId, 10);
        if (agentId) {
            await this.openAgent(agentId);
            return;
        }
        await this.loadList();
    }

    _filtersPayload() {
        const f = { period_days: this.state.filters.period_days };
        if (this.state.filters.pipeline) {
            f.pipeline = this.state.filters.pipeline;
        }
        if (this.state.filters.agent_type) {
            f.agent_type = this.state.filters.agent_type;
        }
        if (this.state.filters.language) {
            f.language = this.state.filters.language;
        }
        if (this.state.filters.campaign_id) {
            f.campaign_id = this.state.filters.campaign_id;
        }
        if (this.state.filters.status) {
            f.status = this.state.filters.status;
        }
        return f;
    }

    async loadList() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "doorway.agent.profile",
                "performance_list_agents",
                [this._filtersPayload()]
            );
            this.state.agents = data.agents || [];
            this.state.pipelines = data.pipelines || [];
            this.state.campaigns = data.campaigns || [];
            this.state.languages = data.languages || [];
        } catch (err) {
            this.notification.add(rpcErrorMessage(err), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async openAgent(id) {
        this.state.selectedAgentId = id;
        this.state.view = "detail";
        this.state.callPage = 1;
        this.state.detail = null;
        this.state.detailError = null;
        await this.loadDetail();
    }

    async loadDetail() {
        if (!this.state.selectedAgentId) return;
        this.state.loading = true;
        this.state.detailError = null;
        try {
            const data = await this.orm.call(
                "doorway.agent.profile",
                "performance_agent_detail",
                [[this.state.selectedAgentId], this.state.periodDays, this.state.callPage, 20]
            );
            this.state.detail = data;
        } catch (err) {
            this.state.detail = null;
            this.state.detailError = rpcErrorMessage(err);
            this.notification.add(this.state.detailError, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    backToList() {
        this.state.view = "list";
        this.state.selectedAgentId = null;
        this.state.detail = null;
        this.state.detailError = null;
        this.loadList();
    }

    setFilter(key, value) {
        this.state.filters[key] = value;
        this.loadList();
    }

    setPeriod(days) {
        this.state.periodDays = parseInt(days, 10) || 30;
        this.loadDetail();
    }

    trendMeta(trend) {
        return TREND_ICON[trend] || TREND_ICON.stable;
    }

    metricPct(value) {
        return Math.min(100, Math.round((value / 20) * 100));
    }

    sentimentClass(key) {
        return SENTIMENT_CLS[key] || "";
    }

    toggleCallExpand(callId) {
        this.state.expandedCall =
            this.state.expandedCall === callId ? null : callId;
    }

    async runAnalysis() {
        this.state.analyzing = true;
        try {
            await this.orm.call(
                "doorway.agent.profile",
                "performance_run_analysis",
                [[this.state.selectedAgentId]]
            );
            this.notification.add("Analyse Claude terminée.", { type: "success" });
            await this.loadDetail();
        } catch (err) {
            this.notification.add(rpcErrorMessage(err), { type: "danger" });
        } finally {
            this.state.analyzing = false;
        }
    }

    async applySuggestions() {
        try {
            const action = await this.orm.call(
                "doorway.agent.profile",
                "performance_apply_suggestions",
                [[this.state.selectedAgentId]]
            );
            if (action) {
                this.action.doAction(action);
            } else {
                this.notification.add("Suggestions appliquées au prompt.", {
                    type: "success",
                });
                await this.loadDetail();
            }
        } catch (err) {
            this.notification.add(rpcErrorMessage(err), { type: "danger" });
        }
    }

    roundScore(score) {
        return Math.round(score || 0);
    }

    async changeCallPage(delta) {
        const pages = this.state.detail?.pagination?.pages || 1;
        const next = this.state.callPage + delta;
        if (next < 1 || next > pages) return;
        this.state.callPage = next;
        await this.loadDetail();
    }
}

registry.category("actions").add("performance_dashboard_action", PerformanceDashboard);
