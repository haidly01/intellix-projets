/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { onWillStart, useState } from "@odoo/owl";

export class CoachingListController extends ListController {
    static template = "people_engine.CoachingListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.header = useState({
            loaded: false,
            count: 0,
            avgScore: 0,
            unread: 0,
            pending: 0,
            done: 0,
        });
        onWillStart(async () => {
            await this.loadHeader();
        });
    }

    async loadHeader() {
        const data = await this.orm.call(
            "pe.coaching.session",
            "get_coaching_list_header_data",
            []
        );
        Object.assign(this.header, data, { loaded: true });
    }

    async onCreateManual() {
        const action = await this.orm.call(
            "pe.coaching.session",
            "action_create_manual_session",
            []
        );
        if (action) {
            await this.actionService.doAction(action);
        }
    }

    async onOpenCoachingCalls() {
        await this.actionService.doAction("people_engine.action_pe_coaching_call");
    }
}

export const peopleEngineCoachingListView = {
    ...listView,
    Controller: CoachingListController,
};

registry.category("views").add("people_engine_coaching_list", peopleEngineCoachingListView);
