/** @odoo-module **/
/**
 * Clic sur une organisation = uniquement celle-là.
 * Odoo 19, en multi-sociétés sœurs (Digital Doorway + Agence Doorway),
 * ne vide pas la sélection : Digital Doorway reste cochée.
 * Les cases restent disponibles pour travailler sur plusieurs orgs.
 */
import { CompanySelector } from "@web/webclient/switch_company_menu/switch_company_menu";

const originalSwitch = CompanySelector.prototype.switchCompany;

CompanySelector.prototype.switchCompany = function (mode, companyId) {
    if (mode === "loginto") {
        this.selectedCompaniesIds.splice(0, this.selectedCompaniesIds.length);
        this._selectCompany(companyId, true);
        this.apply();
        this.dropdownState.close?.();
        return;
    }
    return originalSwitch.call(this, mode, companyId);
};
