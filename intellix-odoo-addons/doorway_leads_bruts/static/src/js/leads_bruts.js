/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

const POLL_MS = 4000;

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this._leadsPollTimer = null;
        if (this.props.resModel === "doorway.campagne.extraction") {
            onMounted(() => this._startCampagnePolling());
            onWillUnmount(() => this._stopCampagnePolling());
        }
    },

    _startCampagnePolling() {
        this._stopCampagnePolling();
        const poll = async () => {
            const record = this.model?.root;
            if (!record || !record.resId) {
                return;
            }
            const state = record.data.state;
            if (state !== "running") {
                this._stopCampagnePolling();
                return;
            }
            try {
                const progress = await this.orm.call(
                    "doorway.campagne.extraction",
                    "get_progress",
                    [record.resId]
                );
                if (progress.state && progress.state !== record.data.state) {
                    await this.model.load({ resId: record.resId });
                } else if (progress.progress_pct !== record.data.progress_pct) {
                    await record.update({
                        progress_pct: progress.progress_pct,
                        leads_count: progress.leads_count,
                        state: progress.state,
                    });
                }
                if (progress.state === "done" || progress.state === "error") {
                    this._stopCampagnePolling();
                    await this.model.load({ resId: record.resId });
                }
            } catch (_e) {
                /* ignore transient RPC errors */
            }
        };
        this._leadsPollTimer = setInterval(poll, POLL_MS);
        poll();
    },

    _stopCampagnePolling() {
        if (this._leadsPollTimer) {
            clearInterval(this._leadsPollTimer);
            this._leadsPollTimer = null;
        }
    },
});
