/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

class CoinsActiviteDashboard extends Component {
    static template = "coins_marocain.activite_dashboard";
}
registry.category("actions").add("coins_activite_dashboard", CoinsActiviteDashboard);
