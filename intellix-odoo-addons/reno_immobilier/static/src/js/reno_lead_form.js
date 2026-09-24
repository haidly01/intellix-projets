/** @odoo-module **/

const PRIMARY = [
    "appeler (agent ia)",
    "appeler",
    "email",
    "gagné",
    "gagne",
    "won",
    "perdu",
    "lost",
];

const PLUS_LABELS = [
    "email + pj",
    "email+pj",
    "email rapide",
    "sms",
    "sms rapide",
    "whatsapp",
    "ticket support",
    "carte de visite",
    "nouveau devis",
];

const KEEP_VISIBLE = [
    "préc",
    "prec",
    "suiv",
    "plus",
    "restore",
    "convert",
];

function norm(text) {
    return (text || "")
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim();
}

function isRenoForm() {
    return Boolean(document.querySelector(".o_reno_lead_form"));
}

function headerButtons() {
    const header = document.querySelector(".o_form_view header, .o_form_statusbar, .o_statusbar_buttons");
    if (!header) {
        return [];
    }
    return [...header.querySelectorAll("button, a.btn")].filter((el) => {
        if (el.closest(".o_reno_plus_menu")) {
            return false;
        }
        const t = norm(el.innerText || el.getAttribute("aria-label") || "");
        return Boolean(t) && el.offsetParent !== null;
    });
}

function ensurePlusMenu(host) {
    let wrap = host.querySelector(":scope > .o_reno_plus_menu");
    if (wrap) {
        return wrap;
    }
    wrap = document.createElement("div");
    wrap.className = "o_reno_plus_menu";
    wrap.innerHTML = '<button type="button" class="btn o_reno_plus_btn">Plus</button><div class="o_reno_plus_list"></div>';
    host.appendChild(wrap);
    return wrap;
}

function primaryKey(label) {
    return PRIMARY.find((p) => label === p || label.startsWith(p) || label.includes(p));
}

function hideDuplicatePrimaries(buttons) {
    const kept = new Map();
    for (const btn of buttons) {
        const label = norm(btn.innerText || btn.getAttribute("aria-label") || "");
        const key = primaryKey(label);
        if (!key) {
            continue;
        }
        const prev = kept.get(key);
        if (!prev) {
            kept.set(key, btn);
            continue;
        }
        const preferNew = btn.classList.contains("o_reno_btn_primary");
        const prevPreferred = prev.classList.contains("o_reno_btn_primary");
        if (preferNew && !prevPreferred) {
            prev.style.display = "none";
            kept.set(key, btn);
        } else {
            btn.style.display = "none";
        }
    }
}

function regroupActions() {
    if (!isRenoForm()) {
        const leftover = document.querySelector(".o_reno_plus_menu");
        if (leftover) {
            leftover.remove();
        }
        return;
    }
    const buttons = headerButtons();
    if (!buttons.length) {
        return;
    }
    hideDuplicatePrimaries(buttons);
    const host = buttons[0].parentElement;
    if (!host) {
        return;
    }
    const plus = ensurePlusMenu(host);
    const list = plus.querySelector(".o_reno_plus_list");
    if (!list) {
        return;
    }
    list.innerHTML = "";
    let moved = 0;
    for (const btn of buttons) {
        if (btn.style.display === "none") {
            continue;
        }
        if (btn.classList.contains("o_reno_btn_primary") || btn.classList.contains("o_reno_plus_btn")) {
            continue;
        }
        const label = norm(btn.innerText || btn.getAttribute("aria-label") || "");
        if (KEEP_VISIBLE.some((p) => label.includes(p))) {
            continue;
        }
        if (primaryKey(label)) {
            continue;
        }
        const isPlus = PLUS_LABELS.some((p) => label === p || label.includes(p));
        if (!isPlus && !label.includes("email") && !label.includes("sms") && !label.includes("whatsapp") && !label.includes("devis") && !label.includes("ticket") && !label.includes("carte")) {
            continue;
        }
        const clone = document.createElement("button");
        clone.type = "button";
        clone.textContent = (btn.innerText || "").trim() || btn.getAttribute("aria-label");
        clone.addEventListener("click", (ev) => {
            ev.preventDefault();
            btn.click();
        });
        list.appendChild(clone);
        btn.style.display = "none";
        moved += 1;
    }
    plus.style.display = moved ? "" : "none";
}

function focusPartnerCard() {
    const el = document.querySelector(
        "#o_reno_partner_anchor, .o_reno_partner_stack, .o_reno_partner_card, .o_reno_partner_empty"
    );
    if (!el) {
        return;
    }
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("o_reno_partner_focus");
    setTimeout(() => el.classList.remove("o_reno_partner_focus"), 1600);
    const input = el.querySelector("input, .o_input");
    if (input) {
        input.focus();
    }
}

function hideLegacyAssignBlocks() {
    if (!isRenoForm()) {
        return;
    }
    document.querySelectorAll(".o_horizontal_separator, .o_group_title, legend, .o_form_label").forEach((el) => {
        const t = norm(el.textContent);
        const hideAssign = t.includes("attribution rénovation") || t === "détail par service";
        const hideContact = (
            t === "contact information"
            || t === "informations de contact"
            || t === "company information"
            || t === "informations de la société"
            || t === "informations société"
        );
        if (!hideAssign && !hideContact) {
            return;
        }
        const group = el.closest(".o_group, .o_inner_group");
        if (group && !group.closest(".o_reno_partner_stack") && !group.closest(".o_reno_contact_card")) {
            group.style.display = "none";
        }
    });
    document.querySelectorAll('.o_field_widget[name="service_assignment_ids"]').forEach((el) => {
        if (!el.closest(".o_reno_partner_stack")) {
            const group = el.closest(".o_group, .o_inner_group") || el;
            group.style.display = "none";
        }
    });
}

function bindPartnerHelpers() {
    document.querySelectorAll(".o_reno_focus_partner_btn").forEach((btn) => {
        if (btn.dataset.renoBound) {
            return;
        }
        btn.dataset.renoBound = "1";
        btn.addEventListener("click", () => setTimeout(focusPartnerCard, 50));
    });
    document.querySelectorAll(".o_reno_change_partner").forEach((el) => {
        if (el.dataset.renoBound) {
            return;
        }
        el.dataset.renoBound = "1";
        el.addEventListener("click", () => {
            const card = el.closest(".o_reno_partner_card") || document.querySelector(".o_reno_partner_card");
            const input = card && card.querySelector("input, .o_input, a");
            if (input) {
                input.click();
                if (input.focus) {
                    input.focus();
                }
            }
        });
    });
}

function start() {
    if (!document.body) {
        return;
    }
    let timer = null;
    const run = () => {
        if (!isRenoForm() && !document.querySelector(".o_reno_plus_menu")) {
            return;
        }
        clearTimeout(timer);
        timer = setTimeout(() => {
            try {
                regroupActions();
                hideLegacyAssignBlocks();
                bindPartnerHelpers();
            } catch (e) {
                // visual only — never break the webclient
            }
        }, 200);
    };
    run();
    new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}
