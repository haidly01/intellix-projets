/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";

const PE_RH_CLASS = "pe-rh-theme";

function isPeModel(resModel) {
    return Boolean(resModel && resModel.startsWith("pe."));
}

function appendPeRhClass(className) {
    const base = className || "";
    return base.includes(PE_RH_CLASS) ? base : `${base} ${PE_RH_CLASS}`.trim();
}

patch(FormController.prototype, {
    get className() {
        const result = super.className;
        if (isPeModel(this.props.resModel)) {
            result[PE_RH_CLASS] = true;
        }
        return result;
    },
});

patch(ListController.prototype, {
    get className() {
        const base = this.props.className;
        return isPeModel(this.props.resModel) ? appendPeRhClass(base) : base;
    },
});

patch(KanbanController.prototype, {
    get className() {
        const base = this.props.className;
        return isPeModel(this.props.resModel) ? appendPeRhClass(base) : base;
    },
});
