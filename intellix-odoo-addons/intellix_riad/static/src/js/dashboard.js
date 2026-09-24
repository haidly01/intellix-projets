/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { NAV_ACTIONS, RiadShell } from "./shell";
import { riadLabels } from "./labels";

class RiadDashboard extends Component {
    static template = "intellix_riad.Dashboard";
    static components = { RiadShell };
    static props = ["*"];

    get shellPage() {
        return "dashboard";
    }

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.labels = riadLabels();
        this.state = useState({
            establishmentId: false,
            punchingId: false,
            punchMode: false,
            arrival: "09:00",
            data: {
                user: {},
                establishments: [],
                kpis: {},
                week: { days: [], groups: [] },
                terrace: {},
                wellness_today: [],
                attendance_today: [],
                inbox: [],
                events: [],
                pricing: {},
            },
        });
        onMounted(() => {
            this.load(this._contextEstablishmentId());
        });
    }

    _contextEstablishmentId() {
        const action = this.props.action || {};
        const ctx = action.context || {};
        const raw = ctx.establishment_id || ctx.default_establishment_id;
        const id = parseInt(raw, 10);
        return id || false;
    }

    get kpis() {
        return this.state.data.kpis || {};
    }

    get week() {
        return this.state.data.week || { days: [], groups: [] };
    }

    get terrace() {
        return this.state.data.terrace || {};
    }

    get pricing() {
        return this.state.data.pricing || {};
    }

    async load(establishmentId) {
        try {
            const data = await this.orm.call(
                "intellix.riad.dashboard",
                "get_dashboard_data",
                [establishmentId || this.state.establishmentId || false]
            );
            this.state.data = data;
            this.state.establishmentId = data.establishment ? data.establishment.id : false;
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Tableau de bord indisponible.",
                { type: "danger" }
            );
        }
    }

    async onEstablishmentChange(ev) {
        const id = parseInt(ev.target.value, 10);
        this.state.establishmentId = id;
        await this.load(id);
    }

    shellNav(page) {
        const target = NAV_ACTIONS[page];
        if (target) {
            this.action.doAction(target);
        }
    }

    openCalendar() {
        this.action.doAction(NAV_ACTIONS.reservations);
    }

    newReservation() {
        this.openReservationScreen({});
    }

    openReservationScreen(context) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "intellix_riad.calendar",
            context: context || {},
        });
    }

    onCellClick(room, cell) {
        if (cell.reservation_id) {
            this.openReservationScreen({ reservation_id: cell.reservation_id });
            return;
        }
        this.openReservationScreen({
            default_room_id: room.id,
            default_check_in: cell.date,
        });
    }

    openEvent(ev) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "intellix_riad.events",
            context: { event_id: ev.id },
        });
    }

    openStaff(person) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "intellix_riad.personnel",
            context: { profile_id: person.id },
        });
    }

    startPunch(person, mode) {
        this.state.punchingId = person.id;
        this.state.punchMode = mode;
        this.state.arrival = "09:00";
    }

    onArrivalChange(ev) {
        this.state.arrival = ev.target.value;
    }

    async punch(person, kind, arrival) {
        try {
            await this.orm.call("intellix.riad.dashboard", "punch_today", [
                person.id,
                kind,
                arrival || false,
            ]);
            this.state.punchingId = false;
            this.state.punchMode = false;
            await this.load(this.state.establishmentId);
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Pointage impossible.",
                { type: "danger" }
            );
        }
    }

    async confirmLate(person) {
        if (!this.state.arrival) {
            this.notification.add("Indiquez l'heure d'arrivée.", { type: "warning" });
            return;
        }
        await this.punch(person, "late", this.state.arrival);
    }

    openInbox(item) {
        if (item.kind === "booking" && item.res_id) {
            this.openReservationScreen({ reservation_id: item.res_id });
            return;
        }
        this.action.doAction({
            type: "ir.actions.client",
            tag: item.kind === "social" ? "intellix_riad.social" : "intellix_riad.inbox",
            context: {
                item_id: item.res_id || false,
                item_kind: item.kind || "mail",
            },
        });
    }
}

registry.category("actions").add("intellix_riad.dashboard", RiadDashboard);
