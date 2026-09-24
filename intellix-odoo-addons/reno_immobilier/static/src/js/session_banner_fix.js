/** @odoo-module **/
// Disabled: this file used to run on every backend screen, hide OWL
// notifications, and POST /web/webclient/version_info every 8s. That
// flooded the single odoo-server worker and could white-screen the
// webclient (OWL insertBefore / hung asset + session requests).
