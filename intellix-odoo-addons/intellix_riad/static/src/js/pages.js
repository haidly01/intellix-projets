/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { NAV_ACTIONS, RiadShell } from "./shell";
import { riadLabels } from "./labels";

class RiadScreen extends Component {
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
            data: {},
        });
        onMounted(() => {
            this.load();
        });
    }

    methodName() {
        return "get_dashboard_data";
    }

    methodArgs() {
        return [this.state.establishmentId || false];
    }

    async load(establishmentId) {
        const data = await this.orm.call(
            "intellix.riad.dashboard",
            this.methodName(),
            establishmentId ? [establishmentId] : this.methodArgs()
        );
        this.state.data = data;
        this.state.establishmentId = data.establishment ? data.establishment.id : false;
    }

    async onEstablishmentChange(ev) {
        const id = parseInt(ev.target.value, 10);
        this.state.establishmentId = id;
        await this.load(id);
    }

    openCatalog(kind) {
        const xmlId =
            kind === "restaurant"
                ? "intellix_riad.action_riad_restaurant_menu"
                : "intellix_riad.action_riad_wellness_menu";
        this.action.doAction(xmlId);
    }
}

export class RiadRestaurant extends RiadScreen {
    static template = "intellix_riad.Restaurant";

    get shellPage() {
        return "restaurant";
    }

    setup() {
        super.setup();
        this.state.view = "planning";
        this.state.form = this._emptyBooking();
        this.state.plan = [];
        this.state.saving = false;
    }

    methodName() {
        return "get_restaurant_data";
    }

    get tables() {
        return this.state.data.tables || [];
    }

    get restaurantMenu() {
        const now = this.state.data.menu_now || [];
        if (now.length) {
            return now;
        }
        return this.state.data.menu || [];
    }

    get zones() {
        return this.state.data.zones || [
            { id: "terrasse", name: "Terrasse" },
            { id: "patio", name: "Patio" },
            { id: "salon", name: "Salon" },
        ];
    }

    get residents() {
        return this.state.data.residents || [];
    }

    get tickets() {
        return this.state.data.tickets || [];
    }

    _emptyBooking(table) {
        return {
            ticket_id: table && table.ticket_id ? table.ticket_id : false,
            table_id: table && table.id ? table.id : "",
            guest_kind: table && table.guest_kind ? table.guest_kind : "externe",
            guest_name: table && table.guest_name ? table.guest_name : "",
            covers: table && table.covers ? table.covers : "2",
            reservation_id: table && table.reservation_id ? table.reservation_id : "",
            amount: table && table.amount ? table.amount : "",
            tip_amount: table && table.tip_amount ? table.tip_amount : "",
            tip_mode: table && table.tip_mode ? table.tip_mode : "cash",
            charge_to_room: table ? !!table.charge_to_room : false,
        };
    }

    editPlan() {
        this.state.plan = (this.state.data.tables || []).map((row, index) => ({
            key: row.id || "new-" + index,
            id: row.id || false,
            name: row.name || "",
            seats: String(row.seats || 2),
            zone: row.zone || "terrasse",
        }));
        this.state.view = "plan";
    }

    addPlanRow() {
        this.state.plan.push({
            key: "new-" + Date.now(),
            id: false,
            name: "",
            seats: "2",
            zone: "terrasse",
        });
    }

    removePlanRow(index) {
        this.state.plan.splice(index, 1);
    }

    onPlanChange(index, ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.plan[index][field] = ev.target.value;
        }
    }

    async savePlan() {
        const tables = this.state.plan
            .filter((row) => (row.name || "").trim())
            .map((row) => ({
                id: row.id || false,
                name: row.name.trim(),
                seats: parseInt(row.seats, 10) || 2,
                zone: row.zone || "terrasse",
            }));
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "save_floor_plan", [
                this.state.establishmentId || false,
                tables,
            ]);
            this.state.view = "planning";
            await this.load(this.state.establishmentId);
            this.notification.add("Plan de salle enregistré.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Enregistrement impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    newBooking(table) {
        this.state.form = this._emptyBooking(table);
        this.state.view = "form";
    }

    setGuestKind(kind) {
        this.state.form.guest_kind = kind;
        if (kind === "externe") {
            this.state.form.reservation_id = "";
            this.state.form.charge_to_room = false;
            this.state.form.tip_mode = "cash";
        } else {
            this.state.form.charge_to_room = true;
        }
    }

    backToPlanning() {
        this.state.view = "planning";
    }

    openSettings() {
        this.action.doAction({ type: "ir.actions.client", tag: "intellix_riad.settings" });
    }

    onFormChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (!field) {
            return;
        }
        if (ev.target.type === "checkbox") {
            this.state.form[field] = ev.target.checked;
            if (field === "charge_to_room" && ev.target.checked) {
                this.state.form.tip_mode = this.state.form.tip_mode || "cash";
            }
            if (field === "charge_to_room" && !ev.target.checked) {
                this.state.form.tip_mode = "cash";
            }
            return;
        }
        this.state.form[field] = ev.target.value;
    }

    async saveBooking() {
        const form = this.state.form;
        if (!form.table_id) {
            this.notification.add("Choisissez une table.", { type: "warning" });
            return;
        }
        if (form.guest_kind === "resident" && !form.reservation_id) {
            this.notification.add("Liez la table à un séjour.", { type: "warning" });
            return;
        }
        if (form.guest_kind !== "resident" && !form.guest_name) {
            this.notification.add("Indiquez le nom de la cliente extérieure.", {
                type: "warning",
            });
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "intellix.riad.dashboard",
                "create_table_booking",
                [
                    this.state.establishmentId || false,
                    {
                        ticket_id: form.ticket_id || false,
                        table_id: parseInt(form.table_id, 10),
                        guest_kind: form.guest_kind || "externe",
                        guest_name: form.guest_name,
                        covers: parseInt(form.covers, 10) || 2,
                        reservation_id: parseInt(form.reservation_id, 10) || false,
                        amount: form.amount ? parseFloat(form.amount) : 0,
                        tip_amount: form.tip_amount ? parseFloat(form.tip_amount) : 0,
                        tip_mode: form.tip_mode || "cash",
                        charge_to_room: !!form.charge_to_room,
                    },
                ]
            );
            this.state.view = "planning";
            await this.load(this.state.establishmentId);
            const message =
                result && result.state === "charged"
                    ? "Note poussée à la chambre."
                    : "Table enregistrée.";
            this.notification.add(message, { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Réservation impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

export class RiadWellness extends RiadScreen {
    static template = "intellix_riad.Wellness";

    get shellPage() {
        return "wellness";
    }

    setup() {
        super.setup();
        this.state.view = "planning";
        this.state.form = this._emptyWellnessForm();
        this.state.saving = false;
        this.state.providerFilter = "all";
    }

    methodName() {
        return "get_wellness_data";
    }

    get serviceTypes() {
        return this.state.data.service_types || [];
    }

    get practitioners() {
        const typeId = parseInt(this.state.form.type_id, 10) || 0;
        const rows = this.state.data.practitioners || [];
        if (!typeId) {
            return rows;
        }
        return rows.filter(
            (row) => !row.type_ids || !row.type_ids.length || row.type_ids.indexOf(typeId) !== -1
        );
    }

    get residents() {
        return this.state.data.residents || [];
    }

    get staffCandidates() {
        return this.state.data.staff_candidates || [];
    }

    get visibleProviders() {
        const rows = this.state.data.providers || [];
        if (this.state.providerFilter === "all") {
            return rows;
        }
        return rows.filter((row) => row.kind === this.state.providerFilter);
    }

    setProviderFilter(kind) {
        this.state.providerFilter = kind;
    }

    _pad(value) {
        return String(value).padStart(2, "0");
    }

    _localInput(date) {
        return (
            date.getFullYear() +
            "-" +
            this._pad(date.getMonth() + 1) +
            "-" +
            this._pad(date.getDate()) +
            "T" +
            this._pad(date.getHours()) +
            ":" +
            this._pad(date.getMinutes())
        );
    }

    _odooDatetime(value) {
        if (!value) {
            return false;
        }
        return value.replace("T", " ") + ":00";
    }

    _emptyWellnessForm() {
        const start = new Date();
        start.setMinutes(0, 0, 0);
        if (start.getHours() < 9) {
            start.setHours(10);
        }
        const end = new Date(start);
        end.setHours(start.getHours() + 1);
        return {
            guest_kind: "externe",
            guest_name: "",
            offer_id: "",
            type_id: "",
            practitioner_id: "",
            date_start: this._localInput(start),
            date_end: this._localInput(end),
            amount: "",
            reservation_id: "",
            experience_brief: "",
        };
    }

    newSlot() {
        this.state.form = this._emptyWellnessForm();
        this.state.view = "form";
    }

    newPractitioner() {
        this.state.form = { name: "", type_ids: [], kind: "external", staff_id: "" };
        this.state.view = "practitioner";
    }

    setPractitionerKind(kind) {
        this.state.form.kind = kind;
        if (kind === "external") {
            this.state.form.staff_id = "";
        }
    }

    onStaffPick(ev) {
        const id = ev.target.value;
        this.state.form.staff_id = id;
        const row = this.staffCandidates.find((item) => item.id == id);
        if (row && row.name) {
            this.state.form.name = row.name;
        }
    }

    toggleType(typeId) {
        const id = parseInt(typeId, 10);
        const current = this.state.form.type_ids || [];
        const index = current.indexOf(id);
        if (index >= 0) {
            current.splice(index, 1);
        } else {
            current.push(id);
        }
        this.state.form.type_ids = current;
    }

    async savePractitioner() {
        if (!this.state.form.name && !this.state.form.staff_id) {
            this.notification.add("Indiquez le nom ou choisissez un membre du staff.", {
                type: "warning",
            });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "create_practitioner", [
                this.state.establishmentId || false,
                {
                    name: this.state.form.name,
                    kind: this.state.form.kind || "external",
                    staff_id: parseInt(this.state.form.staff_id, 10) || false,
                    type_ids: this.state.form.type_ids || [],
                },
            ]);
            this.state.view = "planning";
            await this.load(this.state.establishmentId);
            this.notification.add(
                this.state.form.kind === "staff"
                    ? "Staff interne ajouté au planning."
                    : "Prestataire ajoutée.",
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Création impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    backToPlanning() {
        this.state.view = "planning";
    }

    setGuestKind(kind) {
        this.state.form.guest_kind = kind;
        if (kind === "externe") {
            this.state.form.reservation_id = "";
        }
    }

    onFormChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (!field) {
            return;
        }
        this.state.form[field] = ev.target.value;
        if (field === "offer_id") {
            this.applyOffer(ev.target.value);
        }
    }

    applyOffer(offerId) {
        const id = parseInt(offerId, 10);
        const row = (this.state.data.menu || []).find((item) => item.id === id);
        if (!row) {
            return;
        }
        if (row.type_id) {
            this.state.form.type_id = String(row.type_id);
        }
        if (row.price) {
            this.state.form.amount = String(row.price);
        }
        if (row.duration_minutes && this.state.form.date_start) {
            const start = new Date(this.state.form.date_start);
            if (!Number.isNaN(start.getTime())) {
                start.setMinutes(start.getMinutes() + row.duration_minutes);
                this.state.form.date_end = this._localInput(start);
            }
        }
    }

    async saveSlot() {
        const form = this.state.form;
        if (!form.type_id || !form.practitioner_id || !form.date_start) {
            this.notification.add("Choisissez le soin, la prestataire et l'horaire.", {
                type: "warning",
            });
            return;
        }
        if (form.guest_kind === "externe" && !form.guest_name) {
            this.notification.add("Indiquez le nom de la cliente.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "create_wellness_slot", [
                this.state.establishmentId || false,
                {
                    offer_id: parseInt(form.offer_id, 10) || false,
                    type_id: parseInt(form.type_id, 10),
                    practitioner_id: parseInt(form.practitioner_id, 10),
                    date_start: this._odooDatetime(form.date_start),
                    date_end: this._odooDatetime(form.date_end),
                    guest_kind: form.guest_kind,
                    guest_name: form.guest_name || false,
                    reservation_id: parseInt(form.reservation_id, 10) || false,
                    amount: form.amount ? parseFloat(form.amount) : 0,
                    experience_brief: form.experience_brief || false,
                },
            ]);
            this.state.view = "planning";
            await this.load(this.state.establishmentId);
            this.notification.add("Réservation confirmée.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Réservation impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

export class RiadEvents extends RiadScreen {
    static template = "intellix_riad.Events";

    get shellPage() {
        return "events";
    }

    setup() {
        super.setup();
        const ctx = (this.props.action && this.props.action.context) || {};
        this.state.view = ctx.event_id ? "kanban" : "list";
        this.state.eventId = ctx.event_id || false;
        this.state.filter = "upcoming";
        this.state.form = {};
        this.state.saving = false;
    }

    methodName() {
        return this.state.view === "kanban" ? "get_event_detail" : "get_events_data";
    }

    methodArgs() {
        if (this.state.view === "kanban") {
            return [this.state.establishmentId || false, this.state.eventId];
        }
        return [this.state.establishmentId || false];
    }

    async load(establishmentId) {
        if (establishmentId) {
            this.state.establishmentId = establishmentId;
        }
        const data = await this.orm.call(
            "intellix.riad.dashboard",
            this.methodName(),
            this.methodArgs()
        );
        this.state.data = data;
        this.state.establishmentId = data.establishment ? data.establishment.id : false;
    }

    get events() {
        const rows = (this.state.data.events || []).filter((ev) => {
            if (this.state.filter === "upcoming") {
                return ev.bucket === "upcoming";
            }
            if (this.state.filter === "current") {
                return ev.bucket === "current";
            }
            return ev.bucket === "past";
        });
        return rows;
    }

    setFilter(filter) {
        this.state.filter = filter;
        this.state.view = "list";
    }

    async openEvent(ev) {
        this.state.view = "kanban";
        this.state.eventId = ev.id;
        await this.load(this.state.establishmentId);
    }

    async backToList() {
        this.state.view = "list";
        this.state.eventId = false;
        await this.load(this.state.establishmentId);
    }

    newEvent() {
        const today = new Date();
        const iso = [
            today.getFullYear(),
            String(today.getMonth() + 1).padStart(2, "0"),
            String(today.getDate()).padStart(2, "0"),
        ].join("-");
        this.state.form = {
            name: "",
            day_start: iso,
            day_end: iso,
            guest_count: "6",
            checklist_kind: "privatisation_weekend",
            is_full_privatisation: false,
            include_half_board: true,
        };
        this.state.view = "form";
        this.state.saving = false;
    }

    get checklistKinds() {
        return this.state.data.checklist_kinds || [];
    }

    onFormChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (!field) {
            return;
        }
        if (ev.target.type === "checkbox") {
            this.state.form[field] = ev.target.checked;
            return;
        }
        this.state.form[field] = ev.target.value;
    }

    async saveEvent() {
        if (!this.state.form.name) {
            this.notification.add("Donnez un nom à l'événement.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const created = await this.orm.call("intellix.riad.dashboard", "create_event", [
                this.state.establishmentId || false,
                this.state.form,
            ]);
            this.state.view = "kanban";
            this.state.eventId = created.id;
            await this.load(this.state.establishmentId);
            this.notification.add("Événement créé.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Création impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

export class RiadPersonnel extends RiadScreen {
    static template = "intellix_riad.Personnel";

    get shellPage() {
        return "personnel";
    }

    setup() {
        super.setup();
        const ctx = (this.props.action && this.props.action.context) || {};
        this.state.view = ctx.profile_id ? "fiche" : "list";
        this.state.profileId = ctx.profile_id || false;
        this.state.form = { name: "", role_id: "", phone: "", email: "", hire_date: "" };
        this.state.saving = false;
        this.state.punchingId = false;
        this.state.punchingDate = false;
        this.state.punchMode = false;
        this.state.arrival = "09:00";
    }

    methodName() {
        return this.state.view === "fiche" ? "get_staff_detail" : "get_personnel_data";
    }

    methodArgs() {
        if (this.state.view === "fiche") {
            return [this.state.establishmentId || false, this.state.profileId];
        }
        return [this.state.establishmentId || false];
    }

    async load(establishmentId) {
        if (establishmentId) {
            this.state.establishmentId = establishmentId;
        }
        const data = await this.orm.call(
            "intellix.riad.dashboard",
            this.methodName(),
            this.methodArgs()
        );
        this.state.data = data;
        this.state.establishmentId = data.establishment ? data.establishment.id : false;
    }

    async openStaff(row) {
        this.state.view = "fiche";
        this.state.profileId = row.id;
        await this.load(this.state.establishmentId);
    }

    async backToList() {
        this.state.view = "list";
        this.state.profileId = false;
        await this.load(this.state.establishmentId);
    }

    startPunch(row, mode) {
        this.state.punchingId = row.id;
        this.state.punchingDate = false;
        this.state.punchMode = mode;
        this.state.arrival = "09:00";
    }

    startDayPunch(day, mode) {
        this.state.punchingDate = day.date;
        this.state.punchingId = false;
        this.state.punchMode = mode;
        this.state.arrival = "09:00";
    }

    onArrivalChange(ev) {
        this.state.arrival = ev.target.value;
    }

    async punch(row, kind, arrival) {
        try {
            await this.orm.call("intellix.riad.dashboard", "punch_today", [
                row.id,
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

    async punchDay(day, kind, arrival) {
        try {
            await this.orm.call("intellix.riad.dashboard", "punch_today", [
                this.state.profileId,
                kind,
                arrival || false,
                day.date,
            ]);
            this.state.punchingDate = false;
            this.state.punchMode = false;
            await this.load(this.state.establishmentId);
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Correction impossible.",
                { type: "danger" }
            );
        }
    }

    async confirmLate(row) {
        if (!this.state.arrival) {
            this.notification.add("Indiquez l'heure d'arrivée.", { type: "warning" });
            return;
        }
        await this.punch(row, "late", this.state.arrival);
    }

    async confirmDayLate(day) {
        if (!this.state.arrival) {
            this.notification.add("Indiquez l'heure d'arrivée.", { type: "warning" });
            return;
        }
        await this.punchDay(day, "late", this.state.arrival);
    }

    newEmployee() {
        this.state.form = { name: "", role_id: "", phone: "", email: "", hire_date: "" };
        this.state.view = "form";
        this.state.saving = false;
    }

    openPunchHistory() {
        this.action.doAction("intellix_riad.action_riad_punch");
    }

    get staffRoles() {
        return this.state.data.staff_roles || [];
    }

    onFormChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.form[field] = ev.target.value;
        }
    }

    async saveEmployee() {
        if (!this.state.form.name) {
            this.notification.add("Indiquez le nom de l'employé.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "create_staff", [
                this.state.establishmentId || false,
                {
                    name: this.state.form.name,
                    role_id: parseInt(this.state.form.role_id, 10) || false,
                    phone: this.state.form.phone || false,
                    email: this.state.form.email || false,
                    hire_date: this.state.form.hire_date || false,
                },
            ]);
            this.state.view = "list";
            await this.load(this.state.establishmentId);
            this.notification.add("Employé ajouté.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Création impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    async sendPayroll() {
        if (!this.state.establishmentId) {
            return;
        }
        try {
            await this.orm.call(
                "intellix.riad.establishment",
                "action_send_last_month_payroll_report",
                [[this.state.establishmentId]]
            );
            this.notification.add("Rapport envoyé au comptable.", { type: "success" });
        } catch (error) {
            this.notification.add(error.data && error.data.message || "Envoi impossible.", {
                type: "danger",
            });
        }
    }
}

export class RiadSettings extends RiadScreen {
    static template = "intellix_riad.Settings";

    get shellPage() {
        return "settings";
    }

    setup() {
        super.setup();
        this.state.view = "hub";
        this.state.settings = {};
        this.state.form = {};
        this.state.plan = [];
        this.state.saving = false;
    }

    methodName() {
        return "get_settings_data";
    }

    async load(establishmentId) {
        await super.load(establishmentId);
        this.state.settings = Object.assign({}, this.state.data.settings || {});
        this.state.plan = (this.state.data.tables || []).map((row, index) => ({
            key: row.id || "new-" + index,
            id: row.id || false,
            name: row.name || "",
            seats: String(row.seats || 2),
            zone: row.zone || "terrasse",
        }));
    }

    get zones() {
        return this.state.data.zones || [];
    }

    onSettingsChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.settings[field] = ev.target.value;
        }
    }

    async saveHours() {
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "save_settings", [
                this.state.establishmentId || false,
                this.state.settings,
            ]);
            await this.load(this.state.establishmentId);
            this.notification.add("Horaires enregistrés.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Enregistrement impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    addPlanRow() {
        this.state.plan.push({
            key: "new-" + Date.now(),
            id: false,
            name: "",
            seats: "2",
            zone: "terrasse",
        });
    }

    removePlanRow(index) {
        this.state.plan.splice(index, 1);
    }

    onPlanChange(index, ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.plan[index][field] = ev.target.value;
        }
    }

    async savePlan() {
        const tables = this.state.plan
            .filter((row) => (row.name || "").trim())
            .map((row) => ({
                id: row.id || false,
                name: row.name.trim(),
                seats: parseInt(row.seats, 10) || 2,
                zone: row.zone || "terrasse",
            }));
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "save_floor_plan", [
                this.state.establishmentId || false,
                tables,
            ]);
            await this.load(this.state.establishmentId);
            this.notification.add("Plan de salle enregistré.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Enregistrement impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    newRoom() {
        this.state.form = { name: "", emplacement: "etage", price_per_night: "" };
        this.state.view = "room";
    }

    newPractitioner() {
        this.state.form = { name: "", type_ids: [], kind: "external", staff_id: "" };
        this.state.view = "practitioner";
    }

    get staffCandidates() {
        return this.state.data.staff_candidates || [];
    }

    setPractitionerKind(kind) {
        this.state.form.kind = kind;
        if (kind === "external") {
            this.state.form.staff_id = "";
        }
    }

    onStaffPick(ev) {
        const id = ev.target.value;
        this.state.form.staff_id = id;
        const row = this.staffCandidates.find((item) => item.id == id);
        if (row && row.name) {
            this.state.form.name = row.name;
        }
    }

    backToHub() {
        this.state.view = "hub";
    }

    onFormChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.form[field] = ev.target.value;
        }
    }

    toggleType(typeId) {
        const id = parseInt(typeId, 10);
        const current = this.state.form.type_ids || [];
        const index = current.indexOf(id);
        if (index >= 0) {
            current.splice(index, 1);
        } else {
            current.push(id);
        }
        this.state.form.type_ids = current;
    }

    async saveRoom() {
        if (!this.state.form.name) {
            this.notification.add("Indiquez le nom de la chambre.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "create_room", [
                this.state.establishmentId || false,
                {
                    name: this.state.form.name,
                    emplacement: this.state.form.emplacement || "etage",
                    price_per_night: this.state.form.price_per_night || 0,
                },
            ]);
            this.state.view = "hub";
            await this.load(this.state.establishmentId);
            this.notification.add("Chambre ajoutée.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Création impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    async savePractitioner() {
        if (!this.state.form.name && !this.state.form.staff_id) {
            this.notification.add("Indiquez le nom ou choisissez un membre du staff.", {
                type: "warning",
            });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "create_practitioner", [
                this.state.establishmentId || false,
                {
                    name: this.state.form.name,
                    kind: this.state.form.kind || "external",
                    staff_id: parseInt(this.state.form.staff_id, 10) || false,
                    type_ids: this.state.form.type_ids || [],
                },
            ]);
            this.state.view = "hub";
            await this.load(this.state.establishmentId);
            this.notification.add("Prestataire ajoutée.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Création impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

export class RiadInbox extends RiadScreen {
    static template = "intellix_riad.Inbox";

    get shellPage() {
        return "mails";
    }

    setup() {
        super.setup();
        this.state.item = false;
    }

    methodName() {
        return "get_inbox_data";
    }

    openItem(item) {
        if (item.kind === "booking" && item.res_id && item.res_model !== "intellix.riad.experience.thread") {
            this.action.doAction({
                type: "ir.actions.client",
                tag: "intellix_riad.calendar",
                context: { reservation_id: item.res_id },
            });
            return;
        }
        this.state.item = item;
    }

    backToList() {
        this.state.item = false;
    }
}

export class RiadSocial extends RiadInbox {
    static template = "intellix_riad.Social";

    get shellPage() {
        return "social";
    }

    setup() {
        super.setup();
        this.state.view = "list";
        this.state.form = { platform: "instagram", caption: "", hashtags: "" };
        this.state.saving = false;
    }

    methodName() {
        return "get_social_data";
    }

    get accounts() {
        return this.state.data.accounts || [];
    }

    get posts() {
        return this.state.data.posts || [];
    }

    setPlatform(platform) {
        this.state.form.platform = platform;
    }

    onFormChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.form[field] = ev.target.value;
        }
    }

    newPost() {
        this.state.form = { platform: "instagram", caption: "", hashtags: "" };
        this.state.view = "compose";
    }

    backToFeed() {
        this.state.view = "list";
        this.state.item = false;
    }

    async connectAccount(platform) {
        try {
            const result = await this.orm.call(
                "intellix.riad.dashboard",
                "connect_social_account",
                [this.state.establishmentId || false, platform]
            );
            if (result && result.url) {
                this.action.doAction({
                    type: "ir.actions.act_url",
                    url: result.url,
                    target: "new",
                });
            }
            await this.load(this.state.establishmentId);
            this.notification.add("Compte préparé — terminez la connexion dans l'onglet ouvert.", {
                type: "info",
            });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Connexion impossible.",
                { type: "danger" }
            );
        }
    }

    async publishPost() {
        const form = this.state.form;
        if (!form.caption) {
            this.notification.add("Écrivez le texte de la publication.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "intellix.riad.dashboard",
                "publish_social_post",
                [
                    this.state.establishmentId || false,
                    {
                        platform: form.platform,
                        caption: form.caption,
                        hashtags: form.hashtags,
                    },
                ]
            );
            this.state.view = "list";
            await this.load(this.state.establishmentId);
            if (result && result.warning) {
                this.notification.add(result.warning, { type: "warning" });
            } else {
                this.notification.add("Publication envoyée.", { type: "success" });
            }
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Publication impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

export class RiadChannels extends RiadScreen {
    static template = "intellix_riad.Channels";

    get shellPage() {
        return "channels";
    }

    setup() {
        super.setup();
        this.state.saving = false;
    }

    methodName() {
        return "get_channels_data";
    }

    async markPending(code) {
        this.state.saving = true;
        try {
            const data = await this.orm.call("intellix.riad.dashboard", "mark_ota_pending", [
                this.state.establishmentId || false,
                [code],
            ]);
            this.state.data = data || this.state.data;
            this.notification.add("Statut mis à jour : connexion en cours.", { type: "success" });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Mise à jour impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    async refreshFromChannex() {
        this.state.saving = true;
        try {
            const data = await this.orm.call(
                "intellix.riad.dashboard",
                "refresh_ota_from_channex",
                [this.state.establishmentId || false]
            );
            this.state.data = data || this.state.data;
            if (data && data.refresh_error) {
                this.notification.add(data.refresh_error, { type: "warning" });
            } else {
                this.notification.add("Statuts OTA rafraîchis depuis Channex.", {
                    type: "success",
                });
            }
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Rafraîchissement impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

export class RiadFinance extends RiadScreen {
    static template = "intellix_riad.Finance";

    get shellPage() {
        return "finance";
    }

    methodName() {
        return "get_finance_data";
    }

    fmtMad(value) {
        const n = Number(value || 0);
        return (
            n.toLocaleString("fr-FR", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }) + " MAD"
        );
    }
}

export class RiadWhatsApp extends RiadInbox {
    static template = "intellix_riad.WhatsApp";

    get shellPage() {
        return "whatsapp";
    }

    methodName() {
        return "get_whatsapp_data";
    }
}

registry.category("actions").add("intellix_riad.restaurant", RiadRestaurant);
registry.category("actions").add("intellix_riad.wellness", RiadWellness);
registry.category("actions").add("intellix_riad.events", RiadEvents);
registry.category("actions").add("intellix_riad.personnel", RiadPersonnel);
registry.category("actions").add("intellix_riad.settings", RiadSettings);
registry.category("actions").add("intellix_riad.inbox", RiadInbox);
registry.category("actions").add("intellix_riad.social", RiadSocial);
registry.category("actions").add("intellix_riad.channels", RiadChannels);
registry.category("actions").add("intellix_riad.finance", RiadFinance);
registry.category("actions").add("intellix_riad.whatsapp", RiadWhatsApp);

export { NAV_ACTIONS };
