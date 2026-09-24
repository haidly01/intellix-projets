/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { charField, CharField } from "@web/views/fields/char/char_field";
import { onMounted, onWillUnmount } from "@odoo/owl";

patch(CharField.prototype, {
    setup() {
        super.setup();
        this._timeout = null;
        this._box = null;
        this._acInput = null;
        this._acInputHandler = null;
        this._onDocumentClick = () => this._removeBox();

        onMounted(() => {
            // Activate on any "street" char field.
            if (this.props?.name !== "street") {
                return;
            }
            const input = this.input?.el;
            if (!input) {
                return;
            }
            this._acInput = input;
            this._acInput.setAttribute("autocomplete", "off");
            this._acInputHandler = (ev) => {
                clearTimeout(this._timeout);
                this._timeout = setTimeout(() => this._search(ev?.target?.value || ""), 500);
            };
            this._acInput.addEventListener("input", this._acInputHandler);
            document.addEventListener("click", this._onDocumentClick);
        });

        onWillUnmount(() => {
            clearTimeout(this._timeout);
            this._removeBox();
            if (this._acInput && this._acInputHandler) {
                this._acInput.removeEventListener("input", this._acInputHandler);
            }
            this._acInputHandler = null;
            document.removeEventListener("click", this._onDocumentClick);
        });
    },

    async _search(query) {
        if (!query || query.length < 3) {
            this._removeBox();
            return;
        }

        try {
            const res = await fetch(
                "https://nominatim.openstreetmap.org/search?q=" + encodeURIComponent(query) + "&format=json&addressdetails=1&limit=5&countrycodes=ca,fr",
                { headers: { "Accept-Language": "fr" } }
            );
            this._showBox(await res.json());
        } catch (e) {
            console.error("Nominatim:", e);
        }
    },

    _showBox(results) {
        this._removeBox();
        if (!results.length || !this._acInput) return;
        const rect = this._acInput.getBoundingClientRect();
        const box = document.createElement("ul");
        box.style.cssText = "position:fixed;top:" + rect.bottom + "px;left:" + rect.left + "px;width:" + rect.width + "px;z-index:99999;background:white;border:1px solid #ddd;border-radius:6px;list-style:none;margin:2px 0 0;padding:0;box-shadow:0 4px 12px rgba(0,0,0,0.15);max-height:200px;overflow-y:auto;";

        results.forEach(r => {
            const li = document.createElement("li");
            li.textContent = r.display_name;
            li.style.cssText = "padding:8px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid #f0f0f0;";
            li.addEventListener("mouseenter", () => li.style.background = "#f5f5f5");
            li.addEventListener("mouseleave", () => li.style.background = "white");
            li.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                this._select(r);
            });
            box.appendChild(li);
        });

        document.body.appendChild(box);
        this._box = box;
    },

    _removeBox() {
        if (this._box) { this._box.remove(); this._box = null; }
    },

    _select(result) {
        const a = result.address || {};
        this.props.record.update({
            street: [a.house_number, a.road].filter(Boolean).join(" ") || this.props.record.data.street,
            city: a.city || a.town || a.village || a.municipality || "",
            zip: a.postcode || "",
        });
        this._removeBox();
    },
});

// Keep compatibility with any view still using widget="address_autocomplete".
registry.category("fields").add("address_autocomplete", {
    ...charField,
    component: CharField,
});
