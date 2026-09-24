/** @odoo-module **/

import { Component, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MAX_BYTES = 8 * 1024 * 1024;

const EMPTY_FIELDS = {
    full_name: "",
    first_name: "",
    last_name: "",
    company: "",
    job_title: "",
    email: "",
    phone: "",
    mobile: "",
    website: "",
    street: "",
    city: "",
    zip: "",
    country_code: "",
};

export class DoorwayBusinessCardScan extends Component {
    static template = "doorway_crm.BusinessCardScan";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.cameraInput = useRef("cameraInput");
        this.galleryInput = useRef("galleryInput");
        const params = (this.props.action && this.props.action.params) || {};
        this.targetModel = params.targetModel || "crm.lead";
        this.recordId = params.recordId || null;
        this.teamId = params.teamId || null;
        this.state = useState({
            step: "capture",
            previewUrl: "",
            datas: "",
            mimetype: "image/jpeg",
            fields: { ...EMPTY_FIELDS },
            saving: false,
        });
    }

    get confirmLabel() {
        if (this.recordId) {
            return this.targetModel === "res.partner"
                ? "Mettre à jour le contact"
                : "Mettre à jour l'opportunité";
        }
        return this.targetModel === "res.partner"
            ? "Créer le contact"
            : "Créer l'opportunité";
    }

    openCamera() {
        if (this.cameraInput.el) {
            this.cameraInput.el.click();
        }
    }

    openGallery() {
        if (this.galleryInput.el) {
            this.galleryInput.el.click();
        }
    }

    onFileSelected(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (!file.type.startsWith("image/")) {
            this.notification.add("Choisissez une image (JPEG, PNG…).", { type: "warning" });
            return;
        }
        if (file.size > MAX_BYTES) {
            this.notification.add("Image trop lourde (max 8 Mo).", { type: "warning" });
            return;
        }
        const reader = new FileReader();
        reader.onload = async () => {
            const dataUrl = String(reader.result || "");
            this.state.previewUrl = dataUrl;
            this.state.datas = dataUrl.split(",")[1] || "";
            this.state.mimetype = file.type || "image/jpeg";
            await this.analyzeImage();
        };
        reader.readAsDataURL(file);
    }

    async analyzeImage() {
        this.state.step = "processing";
        try {
            const result = await this.orm.call(
                "doorway.business.card",
                "parse_business_card",
                [],
                {
                    datas: this.state.datas,
                    mimetype: this.state.mimetype,
                }
            );
            if (!result.ok) {
                this.notification.add(result.error || "Analyse impossible.", { type: "danger" });
                this.state.step = "capture";
                return;
            }
            this.state.fields = { ...EMPTY_FIELDS, ...(result.fields || {}) };
            this.state.step = "review";
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
            this.state.step = "capture";
        }
    }

    setField(key, value) {
        this.state.fields[key] = value;
    }

    retake() {
        this.state.step = "capture";
        this.state.previewUrl = "";
        this.state.datas = "";
        this.state.fields = { ...EMPTY_FIELDS };
    }

    async confirmCreate() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "doorway.business.card",
                "create_from_business_card",
                [],
                {
                    datas: this.state.datas,
                    mimetype: this.state.mimetype,
                    target_model: this.targetModel,
                    record_id: this.recordId,
                    fields_data: this.state.fields,
                    team_id: this.teamId,
                }
            );
            const msg = result.updated
                ? `Contact existant mis à jour : ${result.name}`
                : `Enregistrement créé : ${result.name}`;
            this.notification.add(msg, { type: "success" });
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: result.model,
                res_id: result.record_id,
                views: [[false, "form"]],
                target: "current",
            });
        } catch (e) {
            this.notification.add(String(e.message || e), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

DoorwayBusinessCardScan.props = {
    action: { type: Object, optional: true },
    actionId: { type: Number, optional: true },
    className: { type: String, optional: true },
    globalState: { type: Object, optional: true },
};

registry.category("actions").add("doorway_business_card_scan", DoorwayBusinessCardScan);
