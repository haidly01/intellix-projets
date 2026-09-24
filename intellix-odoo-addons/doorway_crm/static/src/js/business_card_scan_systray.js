/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

export class DoorwayBusinessCardScanSystray extends Component {
    static template = "doorway_crm.BusinessCardScanSystray";
    static props = {};

    setup() {
        this.action = useService("action");
    }

    get title() {
        return _t("Scanner carte de visite");
    }

    onClick() {
        this.action.doAction("doorway_crm.action_business_card_scan_client");
    }
}

export const systrayItem = {
    Component: DoorwayBusinessCardScanSystray,
    isDisplayed: () => user.hasGroup("sales_team.group_sale_salesman"),
};

registry.category("systray").add(
    "doorway_crm.business_card_scan",
    systrayItem,
    { sequence: 50 }
);
