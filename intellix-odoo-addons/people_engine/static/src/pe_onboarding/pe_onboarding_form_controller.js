/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { useEffect } from "@odoo/owl";
import { launchPeConfetti } from "./pe_onboarding_confetti";

export class PeOnboardingFormController extends FormController {
    setup() {
        super.setup();
        useEffect(
            () => {
                const step = this.model.root.data.step;
                if (step === "celebrate") {
                    const el =
                        this.rootRef?.el?.querySelector?.(".o_pe_onboarding_wizard") ||
                        document.querySelector(".o_pe_onboarding_wizard");
                    if (el) {
                        launchPeConfetti(el);
                        el.classList.add("pe-celebrate-active");
                    }
                }
            },
            () => [this.model.root.data.step]
        );
    }
}

export const peOnboardingFormView = {
    ...formView,
    Controller: PeOnboardingFormController,
};

registry.category("views").add("pe_onboarding_form", peOnboardingFormView);
