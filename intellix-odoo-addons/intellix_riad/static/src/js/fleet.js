/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { NAV_ACTIONS, RiadShell } from "./shell";
import { riadLabels } from "./labels";

class RiadFleet extends Component {
    static template = "intellix_riad.Fleet";
    static components = { RiadShell };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.labels = riadLabels();
        this.state = useState({
            loading: true,
            period: "today",
            statusFilter: "all",
            cityFilter: "all",
            typeFilter: "all",
            sortKey: "alert",
            sortDir: "asc",
            data: {
                user: {},
                rows: [],
                cities: [],
                types: [],
                alert_count: 0,
                stale_hours: 24,
                channex_live_count: 0,
                channex_live_ok: false,
            },
        });
        onMounted(() => this.load());
    }

    get rows() {
        const status = this.state.statusFilter;
        const city = this.state.cityFilter;
        const type = this.state.typeFilter;
        let rows = (this.state.data.rows || []).filter((row) => {
            if (status !== "all" && row.status !== status) {
                return false;
            }
            if (city !== "all" && row.city !== city) {
                return false;
            }
            if (type !== "all" && row.type_label !== type) {
                return false;
            }
            return true;
        });
        const key = this.state.sortKey;
        const dir = this.state.sortDir === "desc" ? -1 : 1;
        rows = rows.slice().sort((a, b) => {
            if (key === "alert") {
                if (a.critical !== b.critical) {
                    return a.critical ? -dir : dir;
                }
                if (a.status !== b.status) {
                    return a.status === "error" ? -dir : dir;
                }
                return (a.name || "").localeCompare(b.name || "");
            }
            if (key === "occupancy_pct" || key === "revenue") {
                return ((a[key] || 0) - (b[key] || 0)) * dir;
            }
            if (key === "last_sync") {
                return ((a.last_sync || "") > (b.last_sync || "") ? 1 : -1) * dir;
            }
            return ((a[key] || "") + "").localeCompare((b[key] || "") + "") * dir;
        });
        return rows;
    }

    async load(period) {
        this.state.loading = true;
        try {
            const data = await this.orm.call("intellix.riad.dashboard", "get_fleet_data", [
                period || this.state.period || "today",
            ]);
            this.state.data = data;
            this.state.period = data.period || this.state.period;
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Vue globale indisponible.",
                { type: "danger" }
            );
        }
        this.state.loading = false;
    }

    setPeriod(period) {
        this.state.period = period;
        this.load(period);
    }

    setSort(key) {
        if (this.state.sortKey === key) {
            this.state.sortDir = this.state.sortDir === "asc" ? "desc" : "asc";
            return;
        }
        this.state.sortKey = key;
        this.state.sortDir = key === "alert" || key === "name" ? "asc" : "desc";
    }

    sortMark(key) {
        if (this.state.sortKey !== key) {
            return "";
        }
        return this.state.sortDir === "desc" ? " ↓" : " ↑";
    }

    openDashboard(row) {
        if (!row.establishment_id) {
            this.notification.add(
                "Pas encore de tableau de bord Hébergement pour " + (row.name || "cet établissement") + ".",
                { type: "warning" }
            );
            return;
        }
        this.action.doAction({
            type: "ir.actions.client",
            tag: "intellix_riad.dashboard",
            context: { establishment_id: row.establishment_id },
        });
    }

    rowClass(row) {
        const bits = ["fleet-row"];
        if (row.critical) {
            bits.push("is-critical");
        }
        if (row.status === "error") {
            bits.push("is-error");
        }
        if (row.establishment_id) {
            bits.push("is-openable");
        }
        return bits.join(" ");
    }
}

registry.category("actions").add("intellix_riad.fleet", RiadFleet);
