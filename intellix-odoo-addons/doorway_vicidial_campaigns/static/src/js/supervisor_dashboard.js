/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFRESH_MS = 8000;

function todayIso() {
    return new Date().toISOString().slice(0, 10);
}

function daysAgoIso(days) {
    const d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 10);
}

const STATE_BADGE = {
    active: "text-bg-success",
    paused: "text-bg-warning",
    ready: "text-bg-info",
    draft: "text-bg-secondary",
};

class SupervisorDashboard extends Component {
    static template = "doorway_vicidial_campaigns.SupervisorDashboard";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.state = useState({
            loading: true,
            silentRefresh: false,
            refreshedAt: "",
            dateFrom: daysAgoIso(0),
            dateTo: todayIso(),
            activeCampaign: "all",
            activeCampaignState: "all",
            campaignOptions: [],
            campaignStates: [],
            kpis: {},
            campaigns: [],
            agents: [],
            activeSessions: [],
            recentCalls: [],
        });
        this._timer = null;
        onMounted(() => {
            this.load();
            this._timer = setInterval(() => this.load(true), REFRESH_MS);
            this.busService.subscribe(
                "doorway/vicidial/qualification_updated",
                () => this.load(true)
            );
            this.busService.subscribe("doorway/vicidial/lead_open", () =>
                this.load(true)
            );
            this.busService.subscribe("doorway/vicidial/call_ended", () =>
                this.load(true)
            );
        });
        onWillUnmount(() => {
            if (this._timer) {
                clearInterval(this._timer);
            }
        });
    }

    formatDuration(seconds) {
        const s = Number(seconds) || 0;
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return h ? `${h}h${String(m).padStart(2, "0")}` : `${m} min`;
    }

    formatDate(value) {
        if (!value) {
            return "—";
        }
        return value.replace("T", " ").slice(0, 16);
    }

    formatRefreshedAt(value) {
        if (!value) {
            return "";
        }
        return value.replace("T", " ").slice(0, 19);
    }

    stateBadge(state) {
        return STATE_BADGE[state] || "text-bg-secondary";
    }

    async load(silent = false) {
        if (!silent) {
            this.state.loading = true;
        } else {
            this.state.silentRefresh = true;
        }
        try {
            const url =
                `/doorway/vicidial/supervisor/dashboard?date_from=${this.state.dateFrom}` +
                `&date_to=${this.state.dateTo}` +
                `&campaign_vicidial_id=${encodeURIComponent(this.state.activeCampaign)}` +
                `&campaign_state=${encodeURIComponent(this.state.activeCampaignState)}`;
            const response = await fetch(url, { credentials: "same-origin" });
            if (!response.ok) {
                throw new Error("load_failed");
            }
            const data = await response.json();
            this.state.refreshedAt = data.refreshed_at || "";
            this.state.kpis = data.kpis || {};
            this.state.campaignOptions = data.campaign_options || [];
            this.state.campaignStates = data.campaign_states || [];
            this.state.campaigns = data.campaigns || [];
            this.state.agents = data.agents || [];
            this.state.activeSessions = data.active_sessions || [];
            this.state.recentCalls = data.recent_calls || [];
        } catch (_e) {
            if (!silent) {
                this.notification.add("Impossible de charger le tableau superviseurs.", {
                    type: "danger",
                });
            }
        } finally {
            this.state.loading = false;
            this.state.silentRefresh = false;
        }
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.load();
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.load();
    }

    onCampaignChange(ev) {
        this.state.activeCampaign = ev.target.value || "all";
        this.load();
    }

    onCampaignStateChange(ev) {
        this.state.activeCampaignState = ev.target.value || "all";
        this.load();
    }

    openDashboardGlobal() {
        this.action.doAction("doorway_vicidial_campaigns.action_calls_coaching_dashboard");
    }

    openMonitoring() {
        this.action.doAction("doorway_vicidial_campaigns.action_vicidial_campaign_monitor");
    }

    openLead(leadId) {
        if (!leadId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "crm.lead",
            res_id: leadId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("supervisor_dashboard_action", SupervisorDashboard);
