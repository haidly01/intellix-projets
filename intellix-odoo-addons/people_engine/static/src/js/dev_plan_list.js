/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { onWillStart, useState } from "@odoo/owl";

export class DevPlanListController extends ListController {
    static template = "people_engine.DevPlanListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.header = useState({
            loaded: false,
            total: 0,
            active: 0,
            completed: 0,
            avg_completion: 0,
        });
        onWillStart(async () => {
            await this.loadHeader();
        });
    }

    async loadHeader() {
        const data = await this.orm.call(
            "pe.coaching.plan",
            "get_dev_plan_header_data",
            []
        );
        Object.assign(this.header, data, { loaded: true });
    }

    async onCreatePlan() {
        const action = await this.orm.call(
            "pe.coaching.plan",
            "action_create_dev_plan",
            []
        );
        if (action) {
            await this.actionService.doAction(action);
        }
    }
}

export const peopleEngineDevPlanListView = {
    ...listView,
    Controller: DevPlanListController,
};

registry.category("views").add("people_engine_dev_plan_list", peopleEngineDevPlanListView);
