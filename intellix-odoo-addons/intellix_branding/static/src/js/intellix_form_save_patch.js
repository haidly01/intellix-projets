/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

/**
 * Évite le crash JS quand la sauvegarde échoue sans structure RPC
 * (ex. serveur redémarré, coupure réseau) en quittant un formulaire.
 */
patch(FormController.prototype, {
    async onSaveError(error, options, leaving) {
        if (leaving && !error?.data?.message) {
            const fallback = _t(
                "Impossible d'enregistrer les modifications. Réessayez ou quittez sans sauvegarder."
            );
            const normalized = Object.assign(
                Object.create(Object.getPrototypeOf(error) || Error.prototype),
                error,
                {
                    data: {
                        ...(error?.data || {}),
                        message: error?.message || fallback,
                    },
                }
            );
            return super.onSaveError(normalized, options, leaving);
        }
        return super.onSaveError(error, options, leaving);
    },
});
