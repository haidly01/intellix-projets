/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

class CoinsDetenteDashboard extends Component {
    static template = "coins_marocain.detente_dashboard";
}
registry.category("actions").add("coins_detente_dashboard", CoinsDetenteDashboard);
