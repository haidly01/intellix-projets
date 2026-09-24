/** @odoo-module **/



import { registry } from "@web/core/registry";

import { useService } from "@web/core/utils/hooks";

import { FormController } from "@web/views/form/form_controller";

import { patch } from "@web/core/utils/patch";



patch(FormController.prototype, {

    setup() {

        super.setup(...arguments);

        this.orm = useService("orm");

    },



    async onWillRender() {

        await super.onWillRender?.(...arguments);

        if (this.props.resModel !== "doorway.extraction.wizard") {

            return;

        }

        const root = document.querySelector(".o_leads_bruts_wizard");

        if (!root || root.dataset.leadsWizardInit) {

            return;

        }

        root.dataset.leadsWizardInit = "1";

        this._initVolumeSlider(root);

        this._bindSourceRecalc(root);

    },



    _getVolumeMax(record) {

        const possible = Number(record?.data?.volume_possible || 0);

        return possible > 0 ? possible : 1000;

    },



    _syncSliderBounds(slider, record) {

        const max = this._getVolumeMax(record);

        slider.max = String(max);

        slider.min = "1";

        const qty = Number(record?.data?.volume_cible || max);

        slider.value = String(Math.min(Math.max(qty, 1), max));

    },



    _initVolumeSlider(root) {

        const volField = root.querySelector('[name="volume_cible"] input');

        if (!volField || volField.type === "range") {

            return;

        }

        const wrap = volField.closest(".o_field_widget");

        if (!wrap || wrap.querySelector(".o_leads_range")) {

            return;

        }

        const slider = document.createElement("input");

        slider.type = "range";

        slider.step = "1";

        slider.className = "o_leads_range";

        this._syncSliderBounds(slider, this.model?.root);

        slider.addEventListener("input", () => {

            volField.value = slider.value;

            volField.dispatchEvent(new Event("input", { bubbles: true }));

            volField.dispatchEvent(new Event("change", { bubbles: true }));

            this._recalcCost(root);

        });

        wrap.prepend(slider);

    },



    _bindSourceRecalc(root) {

        root.addEventListener("change", (ev) => {

            if (ev.target.matches('input[type="checkbox"]')) {

                this._recalcCost(root);

            }

        });

    },



    async _recalcCost(root) {

        const record = this.model?.root;

        if (!record) {

            return;

        }

        const data = record.data;

        const sourceIds = (data.sources_ids?.records || []).map((r) => r.resId);

        try {

            const result = await this.orm.call(

                "doorway.extraction.wizard",

                "wizard_compute_cost",

                [{

                    zone_geographique: data.zone_geographique,

                    source_ids: sourceIds,

                    volume_cible: data.volume_cible,

                    marge_pct: data.marge_pct || 40,

                }]

            );

            const updates = {

                volume_possible: result.volume_possible,

            };

            if (!data.volume_cible || data.volume_cible > result.volume_possible) {

                updates.volume_cible = result.volume_possible;

            }

            if (data.etape_courante >= 2) {

                updates.leads_estime_min = result.leads_estime_min;

                updates.leads_estime_max = result.leads_estime_max;

            }

            await record.update(updates);



            const slider = root.querySelector(".o_leads_range");

            if (slider) {

                this._syncSliderBounds(slider, record);

            }

        } catch (_e) {

            /* silencieux — recalcul optionnel étape 2 */

        }

    },

});

