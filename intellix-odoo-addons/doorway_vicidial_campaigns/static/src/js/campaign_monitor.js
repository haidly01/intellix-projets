/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFRESH_MS = 30000;

const MODE_LABELS = {
    ia_agent: "IA",
    human_agent: "Humain",
    mixed: "Mixte",
};

const STATE_LABELS = {
    draft: "Brouillon",
    ready: "Prêt",
    active: "Actif",
    paused: "Pause",
    completed: "Terminé",
    cancelled: "Annulé",
};

const STATE_BADGE = {
    draft: "text-bg-secondary",
    ready: "text-bg-info",
    active: "text-bg-success",
    paused: "text-bg-warning",
    completed: "text-bg-dark",
    cancelled: "text-bg-danger",
};

class CampaignMonitor extends Component {
    static template = "doorway_vicidial_campaigns.CampaignMonitor";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            campaigns: [],
            kpis: { active: 0, calls: 0, live_agents: 0, amd_human: 0, amd_machine: 0 },
            loading: true,
        });
        this._timer = null;
        this._onVisibilityChange = () => {
            if (document.hidden) {
                this._pausePolling();
            } else {
                this.load(false);
                this._resumePolling();
            }
        };

        onMounted(() => {
            document.addEventListener("visibilitychange", this._onVisibilityChange);
            this.load(true);
            this._resumePolling();
        });
        onWillUnmount(() => {
            document.removeEventListener("visibilitychange", this._onVisibilityChange);
            this._pausePolling();
        });
    }

    _resumePolling() {
        if (this._timer || document.hidden) {
            return;
        }
        this._timer = setInterval(() => this.load(false), REFRESH_MS);
    }

    _pausePolling() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    async load(initial = false) {
        if (document.hidden) {
            return;
        }
        if (initial) {
            this.state.loading = true;
        }
        try {
            const rows = await this.orm.call(
                "doorway.campaign",
                "action_get_monitor_dashboard",
                []
            );
            const enriched = [];
            let calls = 0;
            let live = 0;
            let amdH = 0;
            let amdM = 0;
            for (const c of rows) {
                const liveStats = c.live_stats || {};
                calls += liveStats.total_calls || c.total_called || 0;
                live += liveStats.live_agents || 0;
                amdH += liveStats.amd_human || 0;
                amdM += liveStats.amd_machine || 0;
                enriched.push({
                    ...c,
                    agent_mode_label: MODE_LABELS[c.campaign_mode] || c.campaign_mode,
                    state_label: STATE_LABELS[c.state] || c.state,
                    state_badge: STATE_BADGE[c.state] || "text-bg-secondary",
                    calls_today: liveStats.total_calls || c.total_called || 0,
                    answered_today: c.total_answered || 0,
                    live_agent_count: liveStats.live_agents || 0,
                    amd_machine_count: liveStats.amd_machine || 0,
                    amd_human_count: liveStats.amd_human || 0,
                    auto_dial_level:
                        c.dial_site === "hostinger"
                            ? (c.vicidial_adl ?? c.dial_level ?? "—")
                            : (c.vicidial_adl ?? c.dial_level ?? "—"),
                });
            }
            this.state.campaigns = enriched;
            this.state.kpis = {
                active: rows.filter((c) => c.state === "active").length,
                calls,
                live_agents: live,
                amd_human: amdH,
                amd_machine: amdM,
            };
        } finally {
            if (initial) {
                this.state.loading = false;
            }
        }
    }

    openCampaign(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "doorway.campaign",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("vicidial_campaign_monitor_action", CampaignMonitor);
