/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { onWillStart, useState } from "@odoo/owl";

export class IntellixSupportKanbanController extends KanbanController {
    static template = "intellix_support.KanbanView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.supportKpis = useState({
            loaded: false,
            data: {
                open_total: 0,
                sla_breach: 0,
                avg_resolution: "—",
                satisfaction: "—",
                resolved_month: 0,
            },
        });
        onWillStart(async () => {
            this.supportKpis.data = await this.orm.call(
                "intellix.support.ticket",
                "get_dashboard_kpis",
                []
            );
            this.supportKpis.loaded = true;
        });
    }
}

export const intellixSupportKanbanView = {
    ...kanbanView,
    Controller: IntellixSupportKanbanController,
};

registry.category("views").add("intellix_support_kanban", intellixSupportKanbanView);
