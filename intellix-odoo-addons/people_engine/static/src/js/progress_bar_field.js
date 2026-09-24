/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

export class ProgressBarCustomField extends Component {
    static template = "people_engine.ProgressBarCustomField";
    static props = {
        ...standardFieldProps,
    };

    get value() {
        return Math.round(this.props.record.data[this.props.name] || 0);
    }

    get fillColor() {
        const v = this.value;
        if (v >= 100) return "#4ade80";
        if (v >= 50) return "#fbbf24";
        return "#a5b4fc";
    }
}

registry.category("fields").add("ix_progress", {
    component: ProgressBarCustomField,
});
