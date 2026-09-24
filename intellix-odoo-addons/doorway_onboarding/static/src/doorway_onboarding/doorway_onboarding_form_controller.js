/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { useEffect } from "@odoo/owl";
import { launchDoorwayConfetti } from "./doorway_onboarding_confetti";

export class DoorwayOnboardingFormController extends FormController {
    setup() {
        super.setup();
        useEffect(
            () => {
                const step = this.model.root.data.current_step_key;
                if (step === "celebrate") {
                    const el =
                        this.rootRef?.el?.querySelector?.(".o_doorway_onboarding_wizard") ||
                        document.querySelector(".o_doorway_onboarding_wizard");
                    if (el) {
                        launchDoorwayConfetti(el);
                        el.classList.add("pe-celebrate-active");
                    }
                }
            },
            () => [this.model.root.data.current_step_key]
        );
    }
}

export const doorwayOnboardingFormView = {
    ...formView,
    Controller: DoorwayOnboardingFormController,
};

registry.category("views").add("doorway_onboarding_form", doorwayOnboardingFormView);
