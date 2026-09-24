/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Service Copilot support — interactions dans support_form_controller.js (js_class).
 */
export const intellixSupportCopilot = {
    dependencies: [],
    start() {},
};

registry.category("services").add("intellix_support.copilot", intellixSupportCopilot);
