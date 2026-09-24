/** @odoo-module **/

import { Record } from "@web/model/relational_model/record";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(Record.prototype, {
    _displayInvalidFieldNotification() {
        const labels = [...this._invalidFields].map(
            (name) => this.fields[name]?.string || name
        );
        const msg = labels.length
            ? _t("Champs manquants : %s", labels.join(", "))
            : _t("Missing required fields");
        return this.model.notification.add(msg, { type: "danger" });
    },
});
