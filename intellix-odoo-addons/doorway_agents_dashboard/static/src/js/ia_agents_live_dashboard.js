/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpcErrorMessage } from "./rpc_error";

const AUTO_REFRESH_MS = 75000;
const CAMPAIGN_META = {
    DW_FRB2C: { title: "Sofia FR", flag: "🇫🇷", code: "DW_FRB2C" },
    DW_QCB2C: { title: "Léa QC", flag: "🇨🇦", code: "DW_QCB2C" },
};

class IaAgentsLiveDashboard extends Component {
    static template = "doorway_agents_dashboard.IaAgentsLiveDashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            refreshing: false,
            snapshot: null,
            error: null,
        });
        this._refreshTimer = null;
        onMounted(() => {
            this.loadSnapshot(false);
            this._refreshTimer = setInterval(
                () => this.loadSnapshot(false),
                AUTO_REFRESH_MS
            );
        });
        onWillUnmount(() => {
            if (this._refreshTimer) {
                clearInterval(this._refreshTimer);
            }
        });
    }

    get campaignIds() {
        const order = this.state.snapshot?.campaign_order;
        if (order?.length) {
            return order;
        }
        return Object.keys(this.state.snapshot?.campaigns || {});
    }

    campaignMeta(cid) {
        return CAMPAIGN_META[cid] || { title: cid, flag: "🤖", code: cid };
    }

    campaignData(cid) {
        return this.state.snapshot?.campaigns?.[cid] || {};
    }

    formatRate(value) {
        const num = Number(value);
        if (Number.isNaN(num)) {
            return "0.0";
        }
        return num.toFixed(1);
    }

    displayValue(value, fallback = "—") {
        if (value === null || value === undefined || value === "") {
            return fallback;
        }
        return value;
    }

    isBadEmptyRec(count) {
        return Number(count || 0) > 5;
    }

    async loadSnapshot(live = false) {
        if (live) {
            this.state.refreshing = true;
        } else if (!this.state.snapshot) {
            this.state.loading = true;
        }
        this.state.error = null;
        try {
            const snapshot = live
                ? await this.orm.call(
                      "doorway.ia.agents.live",
                      "refresh_snapshot",
                      []
                  )
                : await this.orm.call(
                      "doorway.ia.agents.live",
                      "get_snapshot",
                      [false]
                  );
            this.state.snapshot = snapshot;
        } catch (err) {
            this.state.error = rpcErrorMessage(err);
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
            this.state.refreshing = false;
        }
    }

    onManualRefresh() {
        if (this.state.refreshing) {
            return;
        }
        this.loadSnapshot(true);
    }
}

registry.category("actions").add(
    "doorway_ia_agents_live_dashboard",
    IaAgentsLiveDashboard
);
