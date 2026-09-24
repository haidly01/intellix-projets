/** @odoo-module **/

export function rpcErrorMessage(err) {
    return (
        err?.data?.message ||
        err?.data?.arguments?.[0] ||
        err?.message ||
        "Erreur inconnue."
    );
}
