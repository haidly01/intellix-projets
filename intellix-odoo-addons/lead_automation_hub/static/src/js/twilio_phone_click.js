/** @odoo-module **/

function getCurrentLeadId() {
    const hash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
    const model = hash.get("model");
    const id = hash.get("id");
    if (model !== "crm.lead" || !id) {
        return null;
    }
    return Number(id);
}

async function callLeadWithTwilio(recordId) {
    const response = await fetch("/web/dataset/call_kw/crm.lead/action_make_twilio_call", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "crm.lead",
                method: "action_make_twilio_call",
                args: [[recordId]],
                kwargs: {},
            },
            id: Date.now(),
        }),
    });
    const payload = await response.json();
    if (payload.error) {
        throw new Error(payload.error.data?.message || payload.error.message || "Twilio call failed");
    }
    return payload.result;
}

document.addEventListener("click", async (event) => {
    const phoneLink = event.target.closest("a[href^='tel:']");
    if (!phoneLink) {
        return;
    }

    const recordId = getCurrentLeadId();
    if (!recordId) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    const originalText = phoneLink.title;
    phoneLink.style.pointerEvents = "none";
    phoneLink.title = "Calling with Twilio...";

    try {
        await callLeadWithTwilio(recordId);
        window.alert("Twilio call started successfully.");
    } catch (error) {
        window.alert(error.message || "Twilio call failed.");
    } finally {
        phoneLink.style.pointerEvents = "";
        phoneLink.title = originalText;
    }
}, true);
