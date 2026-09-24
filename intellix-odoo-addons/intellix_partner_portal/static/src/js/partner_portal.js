/** IntelliX Partner Portal */
(function () {
    "use strict";

    function initToggle() {
        document.querySelectorAll("[data-ipp-toggle]").forEach(function (wrap) {
            var input = wrap.querySelector('input[type="checkbox"]');
            var visual = wrap.querySelector(".ipp-toggle");
            if (!input || !visual) return;
            function sync() { visual.classList.toggle("on", input.checked); }
            visual.addEventListener("click", function () {
                input.checked = !input.checked;
                sync();
            });
            sync();
        });
    }

    function showZone(mode) {
        document.querySelectorAll("[data-zone-panel]").forEach(function (panel) {
            panel.classList.toggle("active", panel.getAttribute("data-zone-panel") === mode);
        });
    }

    function initZoneType() {
        document.querySelectorAll("[data-zone-type]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var form = btn.closest("form");
                if (!form) return;
                form.querySelectorAll("[data-zone-type]").forEach(function (b) {
                    b.classList.remove("active");
                });
                btn.classList.add("active");
                var hidden = form.querySelector('input[name="coverage_mode"]');
                var mode = btn.getAttribute("data-zone-type");
                if (hidden) hidden.value = mode;
                showZone(mode);
            });
        });
        var current = document.getElementById("ipp-coverage-mode");
        if (current && current.value) showZone(current.value);
    }

    function initInvoicePortal() {
        if (!document.querySelector(".o_portal_invoice_sidebar")) {
            return;
        }
        document.body.classList.add("ix-invoice-portal");
        if (document.querySelector(".ix-invoice-bar")) {
            return;
        }
        var amount = "";
        var h2 = document.querySelector(".o_portal_sidebar_content h2, #sidebar_content h2");
        if (h2) {
            amount = h2.textContent || "";
        }
        var isMaroc = /DH|MAD|Dirham/i.test(amount);
        var bar = document.createElement("div");
        bar.className = "ix-invoice-bar";
        bar.innerHTML = isMaroc
            ? "Digital Doorway SARL<small>Casablanca · facture partenaire</small>"
            : "Agence Doorway Inc.<small>Montréal · facture partenaire</small>";
        var wrap = document.getElementById("wrapwrap");
        if (wrap) {
            wrap.insertBefore(bar, wrap.firstChild);
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initToggle();
        initZoneType();
        initInvoicePortal();
    });
})();
