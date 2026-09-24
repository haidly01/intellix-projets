/** @odoo-module **/

/**
 * Dictée vocale sur fiche crm.lead.
 * Micro par champ + note vocale qui peut créer des activités.
 */

const FIELD_ALIASES = {
  prenom: ["contact_name", "partner_name"],
  nom: ["partner_name", "contact_name"],
  phone: ["phone", "mobile"],
  email: ["email_from", "email"],
  adresse: ["street", "street2"],
  nom_centre: ["partner_name", "partner_company_name"],
  description: ["description"],
};

const ACTIVITY_RE =
  /\b(activit[eé]s?|rappeler|relancer|appeler|todo|t[aâ]che|\u00e0\s+faire|a\s+faire|rendez[-\s]?vous|\brdv\b|planifier|suivi)\b/i;

function normalizeSpokenPhone(text) {
  let t = (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  const digits = {
    zero: "0",
    un: "1",
    une: "1",
    deux: "2",
    trois: "3",
    quatre: "4",
    cinq: "5",
    six: "6",
    sept: "7",
    huit: "8",
    neuf: "9",
  };
  Object.keys(digits).forEach((w) => {
    t = t.replace(new RegExp("\\b" + w + "\\b", "g"), digits[w]);
  });
  const nums = t.replace(/[^\d+]/g, "");
  return nums || (text || "").trim();
}

function fold(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseVoiceCommand(transcript) {
  const raw = (transcript || "").trim();
  if (!raw) return { field: null, value: "" };
  const folded = fold(raw);

  const rules = [
    { field: "nom_centre", re: /^(?:nom du centre|centre|entreprise|compagnie|soci[eé]t[eé])\s*[:\-]?\s*(.+)$/i },
    { field: "adresse", re: /^(?:adresses?|addresses?)\s*[:\-]?\s*(.+)$/i },
    { field: "phone", re: /^(?:t[eé]l[eé]phones?|tels?|mobiles?|cellulaires?|num[eé]ros?)\s*[:\-]?\s*(.+)$/i },
    { field: "email", re: /^(?:e-?mails?|courriels?|mails?)\s*[:\-]?\s*(.+)$/i },
    { field: "prenom", re: /^(?:pr[eé]noms?)\s*[:\-]?\s*(.+)$/i },
    { field: "nom", re: /^(?:noms? de famille|noms?)\s*[:\-]?\s*(.+)$/i },
    { field: "description", re: /^(?:notes?|descriptions?|commentaires?)\s*[:\-]?\s*(.+)$/i },
  ];

  for (let i = 0; i < rules.length; i++) {
    const mRaw = raw.match(rules[i].re);
    const m = mRaw || folded.match(rules[i].re);
    if (m) {
      let value = (m[1] || "").trim();
      if (rules[i].field === "phone") value = normalizeSpokenPhone(value);
      if (rules[i].field === "email") {
        value = value.replace(/\s+/g, "").replace(/arobase/gi, "@").replace(/point/gi, ".");
      }
      return { field: rules[i].field, value };
    }
  }
  return { field: null, value: raw };
}

function SpeechCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function findFieldInput(form, names) {
  for (let i = 0; i < names.length; i++) {
    const n = names[i];
    const wrap =
      form.querySelector(`.o_field_widget[name="${n}"]`) ||
      form.querySelector(`[name="${n}"]`);
    if (!wrap) continue;
    const input =
      wrap.matches("input, textarea")
        ? wrap
        : wrap.querySelector("input:not([type=hidden]), textarea");
    if (input) return input;
  }
  return null;
}

function setInputValue(input, value) {
  if (!input) return;
  const proto = input.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  if (desc && desc.set) desc.set.call(input, value);
  else input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function getLeadId(form) {
  const root = form.closest(".o_form_view") || form;
  const dataId = root.dataset && (root.dataset.resId || root.dataset.id);
  if (dataId && /^\d+$/.test(dataId)) return parseInt(dataId, 10);
  const path = window.location.pathname || "";
  const m =
    path.match(/crm\.lead\/(\d+)/) ||
    path.match(/\/(?:opportunit(?:y|ies)|leads?)\/(\d+)/) ||
    path.match(/\/(\d+)(?:\?|$)/);
  if (m) return parseInt(m[1], 10);
  const hash = window.location.hash || "";
  const hm = hash.match(/(?:^|[?&#])id=(\d+)/);
  if (hm) return parseInt(hm[1], 10);
  return null;
}

async function callVoiceNote(leadId, transcript, source) {
  const res = await fetch("/web/dataset/call_kw/crm.lead/action_voice_note", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      jsonrpc: "2.0",
      method: "call",
      params: {
        model: "crm.lead",
        method: "action_voice_note",
        args: [leadId, transcript],
        kwargs: { source: source || "note" },
      },
      id: Date.now(),
    }),
  });
  const data = await res.json();
  if (data.error) {
    const msg =
      (data.error.data && (data.error.data.message || data.error.data.debug)) ||
      data.error.message ||
      "Erreur serveur";
    throw new Error(msg);
  }
  return data.result || {};
}

function createRecognition(onResult, onEnd, onError) {
  const Ctor = SpeechCtor();
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = "fr-CA";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.onresult = (ev) => {
    const text = (ev.results[0] && ev.results[0][0] && ev.results[0][0].transcript) || "";
    onResult(text);
  };
  rec.onend = () => onEnd && onEnd();
  rec.onerror = (e) => onError && onError(e);
  return rec;
}

function enhanceForm(form) {
  if (!form || form.dataset.ixVoice === "1") return;
  form.dataset.ixVoice = "1";

  const bar = document.createElement("div");
  bar.className = "ix-voice-bar";
  const globalBtn = document.createElement("button");
  globalBtn.type = "button";
  globalBtn.textContent = "🎙 Remplir au vocal";
  const noteBtn = document.createElement("button");
  noteBtn.type = "button";
  noteBtn.className = "ix-voice-note-btn";
  noteBtn.textContent = "🎙 Note + activité";
  const status = document.createElement("span");
  status.className = "ix-voice-status";
  if (!SpeechCtor()) {
    status.classList.add("error");
    status.textContent = "Dictée non supportée sur ce navigateur (Chrome/Edge recommandé).";
    bar.appendChild(status);
  } else {
    status.textContent =
      "Note : dictez le suivi. « Rappeler demain à 10 h » crée une activité.";
    bar.appendChild(globalBtn);
    bar.appendChild(noteBtn);
    bar.appendChild(status);
  }

  const sheet =
    form.querySelector(".o_form_sheet") ||
    form.querySelector(".o_lead_opportunity_form") ||
    form;
  sheet.insertBefore(bar, sheet.firstChild);

  let activeRec = null;
  let activeBtn = null;

  function stopRec() {
    if (activeRec) {
      try {
        activeRec.stop();
      } catch (_e) {
        /* ignore */
      }
    }
    if (activeBtn) activeBtn.classList.remove("listening");
    activeRec = null;
    activeBtn = null;
  }

  async function handleNoteTranscript(text, forceActivity) {
    const leadId = getLeadId(form);
    if (!leadId) {
      status.classList.add("error");
      status.textContent = "Enregistrez la fiche avant la note vocale.";
      return;
    }
    status.classList.remove("error");
    status.textContent = "Enregistrement de la note…";
    const source = forceActivity || ACTIVITY_RE.test(text) ? "activity" : "note";
    try {
      const result = await callVoiceNote(leadId, text, source);
      status.textContent = result.message || "Note enregistrée.";
      if (result.reload) {
        setTimeout(() => window.location.reload(), 700);
      }
    } catch (err) {
      status.classList.add("error");
      status.textContent = err.message || "Erreur note vocale.";
    }
  }

  function startListen(btn, mode, targetInput) {
    if (!SpeechCtor()) return;
    if (activeRec) {
      stopRec();
      return;
    }
    const rec = createRecognition(
      (text) => {
        if (mode === "note" || mode === "activity") {
          handleNoteTranscript(text, mode === "activity");
          return;
        }
        if (mode === "field" && targetInput) {
          const parsed = parseVoiceCommand(text);
          const val = parsed.value;
          if (targetInput.dataset && targetInput.dataset.ixNoteField === "1") {
            handleNoteTranscript(val, ACTIVITY_RE.test(val));
            return;
          }
          setInputValue(targetInput, val);
          status.textContent = "Champ rempli.";
          return;
        }
        const parsed = parseVoiceCommand(text);
        if (parsed.field === "description" || ACTIVITY_RE.test(text)) {
          handleNoteTranscript(parsed.field === "description" ? parsed.value : text, ACTIVITY_RE.test(text));
          return;
        }
        if (parsed.field && FIELD_ALIASES[parsed.field]) {
          const input = findFieldInput(form, FIELD_ALIASES[parsed.field]);
          if (input) {
            setInputValue(input, parsed.value);
            status.textContent = `Rempli : ${parsed.field}`;
          } else {
            status.textContent = `Champ « ${parsed.field} » introuvable sur cette fiche.`;
          }
        } else {
          const focused = form.querySelector("input:focus, textarea:focus");
          if (focused) {
            setInputValue(focused, parsed.value);
            status.textContent = "Dictée dans le champ focus.";
          } else {
            status.textContent = "Précisez le champ, ou utilisez « Note + activité ».";
          }
        }
      },
      () => {
        if (btn) btn.classList.remove("listening");
        if (activeRec === rec) {
          activeRec = null;
          activeBtn = null;
        }
      },
      () => {
        status.classList.add("error");
        status.textContent = "Erreur micro — autorisez le micro dans le navigateur.";
        stopRec();
      }
    );
    if (!rec) return;
    activeRec = rec;
    activeBtn = btn;
    btn.classList.add("listening");
    status.classList.remove("error");
    status.textContent = "Écoute…";
    try {
      rec.start();
    } catch (_e) {
      stopRec();
    }
  }

  globalBtn.addEventListener("click", (e) => {
    e.preventDefault();
    startListen(globalBtn, "global", null);
  });
  noteBtn.addEventListener("click", (e) => {
    e.preventDefault();
    startListen(noteBtn, "activity", null);
  });

  const micTargets = [
    ["contact_name", "prenom"],
    ["partner_name", "nom"],
    ["phone", "phone"],
    ["mobile", "phone"],
    ["email_from", "email"],
    ["street", "adresse"],
    ["description", "description"],
  ];

  function attachMic(wrap, odooName) {
    if (!wrap || wrap.dataset.ixMic === "1") return;
    wrap.dataset.ixMic = "1";
    const input = wrap.querySelector("input:not([type=hidden]), textarea");
    const parent = wrap.parentElement;
    if (!parent) return;
    const mic = document.createElement("button");
    mic.type = "button";
    mic.className = "ix-voice-mic";
    mic.title =
      odooName === "description"
        ? "Dicter une note — « rappeler demain » crée une activité"
        : "Dicter dans ce champ";
    mic.textContent = "🎙";
    const mode = odooName === "description" ? "note" : "field";
    if (input && odooName === "description") input.dataset.ixNoteField = "1";
    mic.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      startListen(mic, mode, input);
    });
    if (wrap.nextSibling) parent.insertBefore(mic, wrap.nextSibling);
    else parent.appendChild(mic);
  }

  micTargets.forEach(([odooName]) => {
    const wrap = form.querySelector(`.o_field_widget[name="${odooName}"]`);
    attachMic(wrap, odooName);
  });

  // Notes HTML / widget collaboratif : micro même sans textarea
  form.querySelectorAll('.o_field_widget[name="description"]').forEach((wrap) => {
    attachMic(wrap, "description");
  });
}

function scan() {
  document
    .querySelectorAll(
      ".o_form_view .o_lead_opportunity_form, .o_form_view form, .o_form_view .o_form_sheet_bg"
    )
    .forEach((el) => {
      const root =
        el.closest(".o_form_view") ||
        el.closest(".o_lead_opportunity_form") ||
        el;
      if (
        root.querySelector('.o_field_widget[name="phone"], .o_field_widget[name="email_from"]') &&
        (root.querySelector('.o_field_widget[name="partner_name"], .o_field_widget[name="contact_name"]') ||
          root.querySelector('.o_field_widget[name="name"]'))
      ) {
        enhanceForm(root);
      }
    });
}

const obs = new MutationObserver(() => scan());
obs.observe(document.documentElement, { childList: true, subtree: true });
scan();
