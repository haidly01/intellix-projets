/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DoorwayVeilleDashboard extends Component {
    static template = "doorway_veille_sociale.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            hot: 0,
            warm: 0,
            cold: 0,
            pending: 0,
            reactivation: 0,
            signals: [],
            loading: true,
        });
        onWillStart(() => this.refreshStats());
    }

    async refreshStats() {
        this.state.loading = true;
        const rows = await this.orm.searchRead(
            "doorway.veille.config",
            [],
            ["count_hot", "count_warm", "count_cold", "count_en_attente", "count_reactivation"],
            { limit: 1 }
        );
        const cfg = rows[0] || {};
        this.state.hot = cfg.count_hot || 0;
        this.state.warm = cfg.count_warm || 0;
        this.state.cold = cfg.count_cold || 0;
        this.state.pending = cfg.count_en_attente || 0;
        this.state.reactivation = cfg.count_reactivation || 0;

        this.state.signals = await this.orm.searchRead(
            "doorway.veille.signal",
            [["statut", "=", "en_attente"]],
            ["titre", "source", "temperature", "score_final", "auteur", "plateforme", "url", "resume", "statut"],
            { limit: 15, order: "score_final desc, date_detection desc" }
        );
        this.state.loading = false;
    }

    async ignoreSignal(ev, signalId) {
        ev.stopPropagation();
        await this.orm.call("doorway.veille.signal", "action_ignorer", [[signalId]]);
        await this.refreshStats();
    }

    async replySignal(ev, signalId) {
        ev.stopPropagation();
        const action = await this.orm.call(
            "doorway.veille.signal",
            "action_repondre",
            [[signalId]]
        );
        if (action) {
            this.action.doAction(action);
        }
    }

    async reactivateSignal(ev, signalId) {
        ev.stopPropagation();
        const action = await this.orm.call(
            "doorway.veille.signal",
            "action_reactivation_douce",
            [[signalId]]
        );
        if (action) {
            this.action.doAction(action);
        }
    }

    openReactivation() {
        this.action.doAction("doorway_veille_sociale.action_veille_signal_reactivation");
    }

    tempLabel(temp) {
        if (temp === "hot") return "🔥 Hot";
        if (temp === "warm") return "🌡 Warm";
        return "❄ Cold";
    }

    sourceLabel(source) {
        const map = {
            reddit: "Reddit",
            google_alerts: "Google",
            instagram: "Instagram",
            facebook: "Facebook",
        };
        return map[source] || source || "—";
    }

    openSignal(signalId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Signal",
            res_model: "doorway.veille.signal",
            res_id: signalId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openHot() {
        this.action.doAction("doorway_veille_sociale.action_veille_signal_hot");
    }

    openAll() {
        this.action.doAction("doorway_veille_sociale.action_veille_signal_all");
    }

    openCreated() {
        this.action.doAction("doorway_veille_sociale.action_veille_signal_created");
    }

    openCalendar() {
        this.action.doAction("doorway_veille_sociale.action_community_post_calendar");
    }

    openNewPost() {
        this.action.doAction("doorway_veille_sociale.action_community_post_new");
    }
}

registry.category("actions").add("doorway_veille_dashboard", DoorwayVeilleDashboard);
