/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

async function openPeProfileIfAny(orm, actionService, record) {
    if (record.resModel !== "hr.employee" || !record.resId) {
        return false;
    }
    try {
        const action = await orm.call(
            "hr.employee",
            "action_open_pe_profile",
            [[record.resId]]
        );
        if (action && action.res_model === "pe.employee.profile") {
            await actionService.doAction(action);
            return true;
        }
    } catch (_e) {
        /* fallback fiche RH standard */
    }
    return false;
}

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.actionService = useService("action");
    },
    async openRecord(record, opts = {}) {
        if (await openPeProfileIfAny(this.orm, this.actionService, record)) {
            return;
        }
        return super.openRecord(record, opts);
    },
});

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.actionService = useService("action");
    },
    async openRecord(record, opts = {}) {
        if (await openPeProfileIfAny(this.orm, this.actionService, record)) {
            return;
        }
        return super.openRecord(record, opts);
    },
});
