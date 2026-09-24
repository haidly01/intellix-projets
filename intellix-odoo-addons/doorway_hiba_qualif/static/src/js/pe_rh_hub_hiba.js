/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";

const actions = registry.category("actions");
const PeRhHub = actions.contains("pe_rh_hub_action")
    ? actions.get("pe_rh_hub_action")
    : null;

if (PeRhHub) {
    patch(PeRhHub.prototype, {
        async load() {
            await super.load();
            this.state.hiba_clock = this.state.hiba_clock || (this.state.payroll && {
                checked_in: Boolean(this.state.payroll.checked_in),
            }) || { checked_in: false };
        },
        async hibaToggleClock() {
            try {
                const res = await this.orm.call(
                    "pe.employee.profile",
                    "action_hiba_toggle_attendance",
                    []
                );
                if (res && res.error) {
                    this.notification.add(res.error, { type: "danger" });
                    return;
                }
                await this.load();
            } catch (err) {
                this.notification.add(err?.message || "Pointage impossible", { type: "danger" });
            }
        },
        hibaCheckIn() {
            return this.hibaToggleClock();
        },
        hibaCheckOut() {
            return this.hibaToggleClock();
        },
    });
}
