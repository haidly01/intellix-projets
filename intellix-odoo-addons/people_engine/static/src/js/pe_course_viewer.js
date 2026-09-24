/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

const DEFAULT_URL =
    "/people_engine/static/src/html/formation_agent_ia_qualification_fr.html";

class PeCourseViewer extends Component {
    static template = "people_engine.PeCourseViewer";
    static props = ["*"];

    get iframeUrl() {
        return this.props.action?.params?.url || DEFAULT_URL;
    }
}

registry.category("actions").add("pe_course_viewer_action", PeCourseViewer);
