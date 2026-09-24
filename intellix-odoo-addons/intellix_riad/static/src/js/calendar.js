/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { RiadShell } from "./shell";
import { riadLabels } from "./labels";

const EMPTY_VISIBLE = {
    rooms: true,
    restaurant: true,
    wellness: true,
    excursion: true,
    privatisation: true,
};

class RiadCalendar extends Component {
    static template = "intellix_riad.Calendar";
    static components = { RiadShell };
    static props = ["*"];

    get shellPage() {
        return "reservations";
    }

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.labels = riadLabels();
        this.state = useState({
            establishmentId: false,
            view: "list",
            statusTab: "all",
            paymentTab: "all",
            month: "",
            dateFrom: "",
            dateTo: "",
            form: this._emptyForm("room"),
            roomForm: { name: "", emplacement: "etage", price_per_night: "" },
            saving: false,
            visible: Object.assign({}, EMPTY_VISIBLE),
            data: {
                user: {},
                establishments: [],
                grid: { days: [], groups: [] },
                rooms: [],
                tables: [],
                practitioners: [],
                service_types: [],
                reservation_groups: [],
                payment_tabs: [],
                period: {},
            },
        });
        onMounted(async () => {
            const now = new Date();
            const y = now.getFullYear();
            const m = String(now.getMonth() + 1).padStart(2, "0");
            this.state.month = `${y}-${m}`;
            this.state.dateFrom = `${y}-${m}-01`;
            const last = new Date(y, now.getMonth() + 1, 0).getDate();
            this.state.dateTo = `${y}-${m}-${String(last).padStart(2, "0")}`;
            await this.load();
            await this.applyIncomingContext();
        });
    }

    _actionContext() {
        return (this.props.action && this.props.action.context) || {};
    }

    async applyIncomingContext() {
        const ctx = this._actionContext();
        if (ctx.reservation_id) {
            await this.openReservation(ctx.reservation_id);
            return;
        }
        if (ctx.default_room_id || ctx.default_check_in) {
            this.newReservation({ id: ctx.default_room_id, resource_type: "room" }, {
                date: ctx.default_check_in,
            });
        }
    }

    get grid() {
        return this.state.data.grid || { days: [], groups: [] };
    }

    get visibleGroups() {
        return (this.grid.groups || []).filter(
            (group) => this.state.visible[group.section || "rooms"] !== false
        );
    }

    get visibleReservationGroups() {
        const groups = this.state.data.reservation_groups || [];
        if (this.state.statusTab === "all") {
            return groups;
        }
        return groups.filter((g) => g.key === this.state.statusTab);
    }

    filteredRows(grp) {
        const rows = (grp && grp.rows) || [];
        if (this.state.paymentTab === "all") {
            return rows;
        }
        return rows.filter((r) => (r.payment_status || "unpaid") === this.state.paymentTab);
    }

    fmtMad(value) {
        const n = Number(value || 0);
        return (
            n.toLocaleString("fr-FR", {
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
            }) + " MAD"
        );
    }

    get rooms() {
        return this.state.data.rooms || [];
    }

    get tables() {
        return this.state.data.tables || [];
    }

    get practitioners() {
        return this.state.data.practitioners || [];
    }

    get serviceTypes() {
        return this.state.data.service_types || [];
    }

    isSectionOn(section) {
        return this.state.visible[section] !== false;
    }

    toggleSection(section) {
        this.state.visible[section] = !this.isSectionOn(section);
    }

    setMode(mode) {
        this.state.view = mode;
    }

    setStatusTab(key) {
        this.state.statusTab = key;
    }

    setPaymentTab(key) {
        this.state.paymentTab = key;
    }

    async load(establishmentId) {
        const data = await this.orm.call(
            "intellix.riad.dashboard",
            "get_calendar_data",
            [establishmentId || this.state.establishmentId || false],
            {
                days: 14,
                date_from: this.state.dateFrom || false,
                date_to: this.state.dateTo || false,
            }
        );
        this.state.data = data;
        this.state.establishmentId = data.establishment ? data.establishment.id : false;
        if (data.period) {
            this.state.dateFrom = data.period.date_from || this.state.dateFrom;
            this.state.dateTo = data.period.date_to || this.state.dateTo;
            this.state.month = data.period.month || this.state.month;
        }
    }

    async onMonthChange(ev) {
        const month = ev.target.value;
        if (!month) {
            return;
        }
        this.state.month = month;
        const [y, m] = month.split("-").map((x) => parseInt(x, 10));
        const last = new Date(y, m, 0).getDate();
        this.state.dateFrom = `${month}-01`;
        this.state.dateTo = `${month}-${String(last).padStart(2, "0")}`;
        await this.load();
    }

    async onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        await this.load();
    }

    async onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        await this.load();
    }

    async onSpanPreset(ev) {
        const days = parseInt(ev.target.value, 10);
        if (!days) {
            return;
        }
        const start = this.state.dateFrom || new Date().toISOString().slice(0, 10);
        const d0 = new Date(start + "T12:00:00");
        const d1 = new Date(d0);
        d1.setDate(d1.getDate() + days - 1);
        this.state.dateFrom = d0.toISOString().slice(0, 10);
        this.state.dateTo = d1.toISOString().slice(0, 10);
        this.state.month = this.state.dateFrom.slice(0, 7);
        await this.load();
    }

    async onEstablishmentChange(ev) {
        const id = parseInt(ev.target.value, 10);
        this.state.establishmentId = id;
        await this.load(id);
    }

    async nudgeReservation(id) {
        try {
            await this.orm.call(
                "intellix.riad.establishment",
                "portal_reservation_nudge",
                [this.state.establishmentId, id, "relance"]
            );
            this.notification.add("Relance créée dans Messages / WhatsApp.", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Relance impossible.",
                { type: "danger" }
            );
        }
    }

    _isoDate(value) {
        if (!value) {
            const d = new Date();
            return [
                d.getFullYear(),
                String(d.getMonth() + 1).padStart(2, "0"),
                String(d.getDate()).padStart(2, "0"),
            ].join("-");
        }
        return value;
    }

    _nextDay(iso) {
        const d = new Date(iso + "T12:00:00");
        d.setDate(d.getDate() + 1);
        return [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, "0"),
            String(d.getDate()).padStart(2, "0"),
        ].join("-");
    }

    _emptyForm(kind, row, cell) {
        const checkIn = this._isoDate(cell && cell.date);
        return {
            id: false,
            kind: kind || "room",
            guest_name: "",
            name: "",
            room_id: row && row.resource_type === "room" && row.id ? row.id : "",
            table_id: row && row.resource_type === "restaurant" && row.id ? row.id : "",
            practitioner_id: row && row.resource_type === "wellness" && row.id ? row.id : "",
            type_id: "",
            check_in: checkIn,
            check_out: this._nextDay(checkIn),
            guests: "2",
            covers: "2",
            breakfast: true,
            source_label: "",
            state_label: "",
            restaurant_note: 0,
            guest_residency: "unknown",
            police_status: "",
            tourist_tax_amount: 0,
            checkin_can_send: true,
        };
    }

    setKind(kind) {
        const form = this.state.form;
        this.state.form = this._emptyForm(kind, null, { date: form.check_in });
        this.state.form.guest_name = form.guest_name || "";
        this.state.form.name = form.name || "";
        this.state.form.guests = form.guests || "2";
    }

    newReservation(row, cell) {
        const kind = (row && row.resource_type) || "room";
        this.state.form = this._emptyForm(kind, row && row.id ? row : null, cell);
        this.state.view = "form";
    }

    async openReservation(reservationId) {
        try {
            const data = await this.orm.call("intellix.riad.dashboard", "get_reservation", [
                this.state.establishmentId || false,
                reservationId,
            ]);
            const row = data.reservation || {};
            this.state.form = Object.assign(this._emptyForm("room"), {
                id: row.id,
                is_demo: !!row.is_demo,
                guest_name: row.guest_name || "",
                room_id: row.room_id || "",
                check_in: row.check_in || "",
                check_out: row.check_out || "",
                guests: row.guests || 2,
                breakfast: !!row.breakfast,
                source_label: row.source_label || "",
                state_label: row.state_label || "",
                restaurant_note: row.restaurant_note || 0,
                guest_residency: row.guest_residency || "unknown",
                police_status: row.police_status || "",
                tourist_tax_amount: row.tourist_tax_amount || 0,
                checkin_can_send: row.checkin_can_send !== false,
            });
            this.state.view = "form";
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Fiche indisponible.",
                { type: "danger" }
            );
        }
    }

    backToCalendar() {
        this.state.view = "list";
    }

    newRoom() {
        this.state.roomForm = { name: "", emplacement: "etage", price_per_night: "" };
        this.state.view = "room";
    }

    onRoomChange(ev) {
        const field = ev.target.getAttribute("data-field");
        if (field) {
            this.state.roomForm[field] = ev.target.value;
        }
    }

    async saveRoom() {
        if (!this.state.roomForm.name) {
            this.notification.add("Indiquez le nom de la chambre.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "create_room", [
                this.state.establishmentId || false,
                this.state.roomForm,
            ]);
            this.state.view = "list";
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
        if (field === "guest_residency") {
            this.state.form.checkin_can_send = ev.target.value !== "moroccan";
            if (ev.target.value === "moroccan") {
                this.state.form.police_status = "Non applicable (résident marocain)";
            }
        }
    }

    _reservationValues() {
        const form = this.state.form;
        return {
            guest_name: form.guest_name,
            room_id: form.room_id,
            check_in: form.check_in,
            check_out: form.check_out,
            guests: form.guests,
            meal_breakfast: !!form.breakfast,
            guest_residency: form.guest_residency || "unknown",
        };
    }

    async sendCheckinLink() {
        const form = this.state.form;
        if (!form.id) {
            this.notification.add("Enregistrez d'abord la réservation.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("intellix.riad.dashboard", "write_room_reservation", [
                this.state.establishmentId || false,
                form.id,
                this._reservationValues(),
            ]);
            const data = await this.orm.call("intellix.riad.dashboard", "send_checkin_link", [
                this.state.establishmentId || false,
                form.id,
            ]);
            const row = (data && data.reservation) || {};
            this.state.form.police_status = row.police_status || "Lien de check-in envoyé";
            this.state.form.checkin_can_send = row.checkin_can_send !== false;
            this.state.form.guest_residency = row.guest_residency || form.guest_residency;
            this.state.form.tourist_tax_amount = row.tourist_tax_amount || form.tourist_tax_amount;
            this.notification.add("Lien de check-in envoyé (e-mail / WhatsApp).", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Envoi du lien impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    async saveReservation() {
        const form = this.state.form;
        const kind = form.kind || "room";
        this.state.saving = true;
        try {
            if (kind === "restaurant") {
                if (!form.table_id || !form.guest_name || !form.check_in) {
                    this.notification.add("Nom, table et date sont requis.", { type: "warning" });
                    return;
                }
                await this.orm.call("intellix.riad.dashboard", "create_table_booking", [
                    this.state.establishmentId || false,
                    {
                        table_id: parseInt(form.table_id, 10),
                        guest_name: form.guest_name,
                        covers: form.covers || form.guests || 2,
                        date: form.check_in,
                    },
                ]);
                this.notification.add("Table réservée.", { type: "success" });
            } else if (kind === "wellness") {
                if (!form.guest_name || !form.practitioner_id || !form.type_id || !form.check_in) {
                    this.notification.add("Nom, soin, prestataire et date sont requis.", {
                        type: "warning",
                    });
                    return;
                }
                await this.orm.call("intellix.riad.dashboard", "create_wellness_slot", [
                    this.state.establishmentId || false,
                    {
                        guest_kind: "externe",
                        guest_name: form.guest_name,
                        practitioner_id: parseInt(form.practitioner_id, 10),
                        type_id: parseInt(form.type_id, 10),
                        date_start: form.check_in + " 10:00:00",
                        date_end: form.check_in + " 11:00:00",
                    },
                ]);
                this.notification.add("Soin réservé.", { type: "success" });
            } else if (kind === "excursion") {
                const title = form.name || form.guest_name;
                if (!title || !form.check_in) {
                    this.notification.add("Nom et date de l'excursion sont requis.", {
                        type: "warning",
                    });
                    return;
                }
                await this.orm.call("intellix.riad.dashboard", "create_event", [
                    this.state.establishmentId || false,
                    {
                        name: title,
                        day_start: form.check_in,
                        day_end: form.check_out || form.check_in,
                        guest_count: form.guests || 2,
                        event_kind: "excursion",
                        checklist_kind: "none",
                    },
                ]);
                this.notification.add("Excursion ajoutée.", { type: "success" });
            } else if (kind === "privatisation") {
                const title = form.name || form.guest_name;
                if (!title || !form.check_in || !form.check_out) {
                    this.notification.add("Nom du groupe et dates sont requis.", {
                        type: "warning",
                    });
                    return;
                }
                const result = await this.orm.call(
                    "intellix.riad.dashboard",
                    "create_privatisation",
                    [
                        this.state.establishmentId || false,
                        {
                            name: title,
                            guest_name: title,
                            check_in: form.check_in,
                            check_out: form.check_out,
                            guests: form.guests || 0,
                        },
                    ]
                );
                if (result && result.warning) {
                    this.notification.add(result.warning, { type: "warning" });
                } else {
                    this.notification.add("Privatisation enregistrée.", { type: "success" });
                }
            } else {
                if (!form.guest_name || !form.room_id || !form.check_in || !form.check_out) {
                    this.notification.add("Nom, chambre et dates sont requis.", {
                        type: "warning",
                    });
                    return;
                }
                if (form.id) {
                    await this.orm.call("intellix.riad.dashboard", "write_room_reservation", [
                        this.state.establishmentId || false,
                        form.id,
                        this._reservationValues(),
                    ]);
                    this.notification.add("Réservation enregistrée.", { type: "success" });
                } else {
                    await this.orm.call("intellix.riad.dashboard", "create_room_reservation", [
                        this.state.establishmentId || false,
                        this._reservationValues(),
                    ]);
                    this.notification.add("Réservation créée.", { type: "success" });
                }
            }
            this.state.view = "list";
            await this.load(this.state.establishmentId);
        } catch (error) {
            this.notification.add(
                (error.data && error.data.message) || "Enregistrement impossible.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    onCellClick(row, cell) {
        const kind = (row && row.resource_type) || "room";
        if (kind === "room" && cell.reservation_id) {
            this.openReservation(cell.reservation_id);
            return;
        }
        this.newReservation(row, cell);
        if (cell.guest) {
            this.state.form.guest_name = cell.guest;
            this.state.form.name = cell.guest;
        }
    }
}

registry.category("actions").add("intellix_riad.calendar", RiadCalendar);
