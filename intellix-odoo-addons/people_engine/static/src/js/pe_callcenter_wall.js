/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

const REFRESH_MS = 30000;

class PeCallcenterWall extends Component {
    static template = "people_engine.PeCallcenterWall";

    setup() {
        this.state = useState({
            loading: true,
            refreshedAt: "",
            leaderboard: [],
            recentBadges: [],
            challenge: null,
            stats: {},
        });
        this._timer = null;
        onMounted(() => {
            this.load();
            this._timer = setInterval(() => this.load(true), REFRESH_MS);
        });
        onWillUnmount(() => {
            if (this._timer) {
                clearInterval(this._timer);
            }
        });
    }

    formatTime(value) {
        if (!value) {
            return "";
        }
        return value.replace("T", " ").slice(0, 19);
    }

    async load(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            const response = await fetch("/pe/callcenter/wall/data", {
                credentials: "same-origin",
            });
            if (!response.ok) {
                throw new Error("load_failed");
            }
            const data = await response.json();
            this.state.refreshedAt = data.refreshed_at || "";
            this.state.leaderboard = data.leaderboard || [];
            this.state.recentBadges = data.recent_badges || [];
            this.state.challenge = data.challenge || null;
            this.state.stats = data.stats || {};
        } catch (_e) {
            // ignore transient errors on wall display
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("pe_callcenter_wall_action", PeCallcenterWall);
