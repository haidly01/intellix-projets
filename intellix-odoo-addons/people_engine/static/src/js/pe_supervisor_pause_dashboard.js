/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFRESH_MS = 10000;

class PeSupervisorPauseDashboard extends Component {
    static template = "people_engine.PeSupervisorPauseDashboard";

    setup() {
        this.notification = useService("notification");
        this.state = useState({ loading: true, agents: [], timestamp: "" });
        this._timer = null;
        onMounted(() => {
            this.load();
            this._timer = setInterval(() => this.load(false), REFRESH_MS);
        });
        onWillUnmount(() => {
            if (this._timer) {
                clearInterval(this._timer);
            }
        });
    }

    async load(showSpinner = true) {
        if (showSpinner) {
            this.state.loading = true;
        }
        try {
            const res = await fetch("/pe/supervisor/pause/status", {
                credentials: "same-origin",
            });
            const data = await res.json();
            this.state.agents = data.agents || [];
            this.state.timestamp = data.timestamp || "";
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    formatDuration(seconds) {
        const s = Math.max(seconds || 0, 0);
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${m}m ${String(r).padStart(2, "0")}s`;
    }

    pauseLabel(type) {
        const map = {
            pausette: "Pausette",
            dejeuner: "Déjeuner",
            personnelle: "Personnelle",
            autre: "Autre",
        };
        return map[type] || "—";
    }
}

registry.category("actions").add("pe_supervisor_pause_dashboard", PeSupervisorPauseDashboard);
