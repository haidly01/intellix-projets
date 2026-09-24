/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class HibaMartinSlotsField extends Component {
    static template = "doorway_hiba_qualif.HibaMartinSlotsField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            days: [],
            selectedDay: null,
            selectedTime: null,
            loading: true,
        });
        onWillStart(async () => {
            const days = await this.orm.call("hiba.book.martin.wizard", "get_slots_ui", []);
            this.state.days = days || [];
            this.state.loading = false;
        });
    }

    onClickDay(ev) {
        const date = ev.currentTarget.dataset.date;
        const day = this.state.days.find((item) => item.date === date);
        if (!day) {
            return;
        }
        this.state.selectedDay = day;
        this.state.selectedTime = null;
        this.props.record.update({ [this.props.name]: false });
    }

    onClickTime(ev) {
        const time = ev.currentTarget.dataset.time;
        const value = this.state.selectedDay?.time_values?.[time];
        this.state.selectedTime = time;
        this.props.record.update({ [this.props.name]: value || false });
    }

    dayNumber(day) {
        return Number((day.date || "").split("-")[2] || 0);
    }

    dayMonth(day) {
        return (day.label || "").split(" ").slice(-1)[0] || "";
    }
}

registry.category("fields").add("hiba_martin_slots", {
    component: HibaMartinSlotsField,
    supportedTypes: ["char"],
});
