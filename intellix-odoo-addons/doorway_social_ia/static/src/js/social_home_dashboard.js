/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class DoorwaySocialHomeDashboard extends Component {
    static template = "doorway_social_ia.HomeDashboard";
    static props = { "*": true };

    get iframeSrc() {
        return "/doorway/social-dash/";
    }
}

registry.category("actions").add("social_home_dashboard_action", DoorwaySocialHomeDashboard);
