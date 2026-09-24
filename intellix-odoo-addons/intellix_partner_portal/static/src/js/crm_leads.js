/** IntelliX Partner Portal — CRM leads (Kanban / Calendrier / Fiche / Analyse) */
(function () {
  "use strict";

  var root = document.getElementById("ipp-crm-root");
  if (!root) return;

  var IS_MANAGER = root.getAttribute("data-is-manager") === "1";
  var CURRENT_USER = parseInt(root.getAttribute("data-current-user"), 10);

  var dataEl = document.getElementById("ipp-crm-data");
  var DATA = JSON.parse(dataEl ? dataEl.textContent : "{}");
  var LEADS = DATA.leads || [];
  var ACTIVITIES = DATA.activities || [];
  var TEAM = DATA.team || [];

  var RESULT_META = {
    no_answer: { label: "Pas de réponse", dot: "no_answer" },
    callback: { label: "À rappeler", dot: "callback" },
    interested: { label: "Intéressé — à relancer", dot: "interested" },
    refused: { label: "Ne souhaite plus donner suite", dot: "refused" },
  };
  var ACTIVITY_META = {
    call: { label: "Appel", cls: "call" },
    task: { label: "Tâche", cls: "task" },
    meeting: { label: "RDV", cls: "meeting" },
  };
  var STATUS_LABELS = {
    nouveau: "Nouveau", relance: "En relance", rdv: "RDV fixé", vendu: "Vendu", perdu: "Perdu",
  };

  function teamName(id) {
    var t = TEAM.filter(function (x) { return x.id === id; })[0];
    return t ? t.name : "Non assigné";
  }
  function teamInitials(id) {
    var t = TEAM.filter(function (x) { return x.id === id; })[0];
    return t ? t.initials : "?";
  }
  function leadName(id) {
    var l = LEADS.filter(function (x) { return x.id === id; })[0];
    return l ? l.name : "?";
  }
  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function rpc(url, params) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {}, id: Date.now() }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { throw new Error(data.error.message || "Erreur serveur"); }
        return data.result;
      });
  }

  var currentView = "kanban";
  var selectedId = LEADS.length ? LEADS[0].id : null;
  var filterMember = "all";

  function visibleLeads() {
    if (!IS_MANAGER) return LEADS;
    if (filterMember === "all") return LEADS;
    if (filterMember === "unassigned") return LEADS.filter(function (l) { return !l.assignedTo; });
    return LEADS.filter(function (l) { return l.assignedTo === filterMember; });
  }
  function visibleActivities() {
    var ids = visibleLeads().map(function (l) { return l.id; });
    return ACTIVITIES.filter(function (a) { return ids.indexOf(a.leadId) !== -1; });
  }

  function statusBadge(status, attempts) {
    if (status === "nouveau") return '<span class="ipp-crm-badge new">Nouveau</span>';
    if (status === "relance") return '<span class="ipp-crm-badge warn">' + attempts.length + '/3 appels</span>';
    if (status === "rdv") return '<span class="ipp-crm-badge ok">RDV fixé</span>';
    if (status === "vendu") return '<span class="ipp-crm-badge ok">Vendu</span>';
    if (status === "perdu") return '<span class="ipp-crm-badge bad">Perdu</span>';
    return "";
  }

  function renderFilterRow() {
    var row = document.getElementById("ipp-crm-filter-row");
    if (!IS_MANAGER) {
      row.innerHTML = '<span class="ipp-crm-locked-chip">Tes leads assignés <span class="ipp-crm-count">' + LEADS.length + '</span></span>';
      return;
    }
    var chips = [
      '<button class="ipp-crm-chip ' + (filterMember === "all" ? "active" : "") + '" data-filter="all">Toute l\'équipe <span class="ipp-crm-count">' + LEADS.length + '</span></button>',
    ];
    TEAM.forEach(function (t) {
      var n = LEADS.filter(function (l) { return l.assignedTo === t.id; }).length;
      chips.push(
        '<button class="ipp-crm-chip ' + (filterMember === t.id ? "active" : "") + '" data-filter="' + t.id + '">' +
        '<span class="ipp-crm-avatar">' + esc(t.initials) + '</span>' + esc(t.name) + ' <span class="ipp-crm-count">' + n + '</span></button>'
      );
    });
    var unassigned = LEADS.filter(function (l) { return !l.assignedTo; }).length;
    if (unassigned > 0) {
      chips.push('<button class="ipp-crm-chip ' + (filterMember === "unassigned" ? "active" : "") + '" data-filter="unassigned">Non assignés <span class="ipp-crm-count">' + unassigned + '</span></button>');
    }
    row.innerHTML = chips.join("");
    row.querySelectorAll("[data-filter]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        filterMember = btn.getAttribute("data-filter");
        renderFilterRow();
        renderBoard();
      });
    });
  }

  function renderViewTabs() {
    var tabs = document.getElementById("ipp-crm-view-tabs");
    tabs.innerHTML =
      '<button class="ipp-crm-view-tab ' + (currentView === "kanban" ? "active" : "") + '" data-view="kanban">Kanban</button>' +
      '<button class="ipp-crm-view-tab ' + (currentView === "calendar" ? "active" : "") + '" data-view="calendar">Calendrier</button>';
    tabs.querySelectorAll("[data-view]").forEach(function (btn) {
      btn.addEventListener("click", function () { setView(btn.getAttribute("data-view")); });
    });
  }

  function setView(v) {
    currentView = v;
    document.getElementById("ipp-crm-board").style.display = v === "kanban" ? "grid" : "none";
    document.getElementById("ipp-crm-calendar").style.display = v === "calendar" ? "block" : "none";
    renderViewTabs();
    if (v === "calendar") renderCalendar();
  }

  function renderBoard() {
    var cols = ["nouveau", "relance", "rdv", "vendu", "perdu"];
    var vis = visibleLeads();
    cols.forEach(function (col) {
      var container = document.querySelector('[data-col="' + col + '"]');
      var items = vis.filter(function (l) { return l.status === col; });
      document.querySelector('[data-count="' + col + '"]').textContent = items.length;
      container.innerHTML = items.map(function (l) {
        var avatar = "";
        if (IS_MANAGER) {
          avatar = l.assignedTo
            ? '<span class="ipp-crm-avatar" title="' + esc(teamName(l.assignedTo)) + '">' + esc(teamInitials(l.assignedTo)) + '</span>'
            : '<span class="ipp-crm-avatar" style="background:var(--crm-surface-3);color:var(--crm-text-faint)">–</span>';
        }
        return (
          '<button class="ipp-crm-card ' + (l.id === selectedId ? "selected" : "") + '" data-lead="' + l.id + '">' +
          '<div class="ipp-crm-card-top"><div class="ipp-crm-lead-name">' + esc(l.name) + '</div>' + avatar + '</div>' +
          '<div class="ipp-crm-lead-meta">' + esc(l.service) + ' · ' + esc(l.city) + '</div>' +
          '<div class="ipp-crm-badges">' + statusBadge(l.status, l.attempts) + '</div>' +
          '</button>'
        );
      }).join("");
    });
    container_bind_cards();
  }

  function container_bind_cards() {
    document.querySelectorAll("[data-lead]").forEach(function (btn) {
      btn.addEventListener("click", function () { selectLead(parseInt(btn.getAttribute("data-lead"), 10)); });
    });
  }

  function selectLead(id) {
    selectedId = id;
    var af = document.getElementById("ipp-crm-attempt-form");
    var acf = document.getElementById("ipp-crm-activity-form");
    if (af) af.classList.remove("open");
    if (acf) acf.classList.remove("open");
    renderBoard();
    renderFiche();
  }

  function renderCalendar() {
    var cal = document.getElementById("ipp-crm-calendar");
    var now = new Date();
    var year = now.getFullYear(), month = now.getMonth();
    var first = new Date(year, month, 1);
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    var startOffset = (first.getDay() + 6) % 7;
    var dows = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
    var acts = visibleActivities();
    var todayStr = now.toISOString().slice(0, 10);

    var cells = "";
    for (var i = 0; i < startOffset; i++) cells += '<div class="ipp-crm-cal-cell empty"></div>';
    for (var day = 1; day <= daysInMonth; day++) {
      var dateStr = year + "-" + String(month + 1).padStart(2, "0") + "-" + String(day).padStart(2, "0");
      var dayActs = acts.filter(function (a) { return a.date === dateStr; }).sort(function (a, b) { return a.time.localeCompare(b.time); });
      var shown = dayActs.slice(0, 3);
      var extra = dayActs.length - shown.length;
      var chips = shown.map(function (a) {
        var meta = ACTIVITY_META[a.type];
        return '<button class="ipp-crm-cal-chip ' + meta.cls + ' ' + (a.done ? "done" : "") + '" data-cal-lead="' + a.leadId + '" title="' + esc(a.time + " — " + a.title) + '">' + esc(a.time + " " + leadName(a.leadId)) + '</button>';
      }).join("");
      cells +=
        '<div class="ipp-crm-cal-cell ' + (dateStr === todayStr ? "today" : "") + '">' +
        '<div class="ipp-crm-cal-daynum">' + day + '</div>' + chips +
        (extra > 0 ? '<div class="ipp-crm-cal-more">+' + extra + ' autre' + (extra > 1 ? "s" : "") + '</div>' : "") +
        '</div>';
    }
    var monthLabel = now.toLocaleDateString("fr-CA", { month: "long", year: "numeric" });
    cal.innerHTML =
      '<div class="ipp-crm-cal-head"><h3>' + esc(monthLabel) + '</h3>' +
      '<div class="ipp-crm-cal-legend"><span><i style="background:var(--crm-sky)"></i>Appel</span><span><i style="background:var(--crm-violet)"></i>Tâche</span><span><i style="background:var(--crm-emerald)"></i>RDV</span></div></div>' +
      '<div class="ipp-crm-cal-grid">' + dows.map(function (d) { return '<div class="ipp-crm-cal-dow">' + d + '</div>'; }).join("") + cells + '</div>';
    cal.querySelectorAll("[data-cal-lead]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setView("kanban");
        selectLead(parseInt(btn.getAttribute("data-cal-lead"), 10));
      });
    });
  }

  function renderFiche() {
    var panel = document.getElementById("ipp-crm-fiche");
    var l = LEADS.filter(function (x) { return x.id === selectedId; })[0];
    if (!l) { panel.innerHTML = "<h4>Fiche lead</h4><p class=\"ipp-crm-sub\">Sélectionne un lead dans le tableau pour voir sa fiche.</p>"; return; }

    var timeline = l.attempts.length
      ? l.attempts.slice().reverse().map(function (a) {
          var meta = RESULT_META[a.result];
          return (
            '<div class="ipp-crm-tl-item"><div class="ipp-crm-tl-dot ' + meta.dot + '"></div><div>' +
            '<div class="ipp-crm-tl-when">' + esc(a.when) + '</div>' +
            '<div class="ipp-crm-tl-result">' + esc(meta.label) + '</div>' +
            (a.note ? '<div class="ipp-crm-tl-note">' + esc(a.note) + '</div>' : "") +
            '<div class="ipp-crm-tl-by">par ' + esc(teamName(a.by)) + '</div></div></div>'
          );
        }).join("")
      : '<p class="ipp-crm-sub" style="margin:0 0 14px">Aucune tentative enregistrée pour l\'instant.</p>';

    var assignBlock;
    if (IS_MANAGER) {
      var opts = '<option value="">Non assigné</option>' + TEAM.map(function (t) {
        return '<option value="' + t.id + '" ' + (l.assignedTo === t.id ? "selected" : "") + '>' + esc(t.name) + '</option>';
      }).join("");
      assignBlock = '<div class="ipp-crm-assign-row"><div style="flex:1"><label>Assigné à</label><select id="ipp-crm-assign-select">' + opts + '</select></div></div>';
    } else {
      assignBlock = '<div class="ipp-crm-assigned-note">Ce lead t\'est assigné — tu es responsable des relances.</div>';
    }

    var canClose = l.status !== "vendu" && l.status !== "perdu";
    var statusActions = canClose
      ? '<div class="ipp-crm-status-actions"><button type="button" class="ipp-crm-status-btn win" id="ipp-crm-mark-vendu">Marquer Vendu</button><button type="button" class="ipp-crm-status-btn loss" id="ipp-crm-mark-perdu">Marquer Perdu</button></div>'
      : "";

    var leadActivities = ACTIVITIES.filter(function (a) { return a.leadId === l.id; }).sort(function (a, b) { return (a.date + a.time).localeCompare(b.date + b.time); });
    var activityRows = leadActivities.map(function (a) {
      var meta = ACTIVITY_META[a.type];
      return (
        '<div class="ipp-crm-activity-row ' + (a.done ? "done" : "") + '"><button class="ipp-crm-activity-check" data-toggle-activity="' + a.id + '"></button>' +
        '<div class="ipp-crm-activity-body"><div class="ipp-crm-activity-title"><span class="ipp-crm-type-tag">' + meta.label + '</span>' + esc(a.title) + '</div>' +
        '<div class="ipp-crm-activity-meta">' + esc(a.date + " · " + a.time) + (a.assignedTo ? " · " + esc(teamName(a.assignedTo)) : "") + '</div></div></div>'
      );
    }).join("") || '<p class="ipp-crm-sub" style="margin:0">Aucune activité prévue.</p>';

    var activityAssignField = IS_MANAGER
      ? '<div><label>Assigné à</label><select id="ipp-crm-act-assign"><option value="">Non assigné</option>' + TEAM.map(function (t) { return '<option value="' + t.id + '">' + esc(t.name) + '</option>'; }).join("") + '</select></div>'
      : "";

    panel.innerHTML =
      '<h4>' + esc(l.name) + '</h4><p class="ipp-crm-sub">' + esc(l.service) + ' · ' + esc(l.city) + '</p>' +
      statusBadge(l.status, l.attempts).replace("ipp-crm-badge", "ipp-crm-fiche-status") +
      assignBlock + statusActions +
      '<p class="ipp-crm-section-label">Notes</p>' +
      '<textarea class="ipp-crm-notes-box" id="ipp-crm-notes" placeholder="Ajoute une note sur ce lead...">' + esc(l.notes) + '</textarea>' +
      '<p class="ipp-crm-section-label">Activités</p>' +
      '<div class="ipp-crm-activity-list">' + activityRows + '</div>' +
      '<button type="button" class="ipp-crm-add-btn" id="ipp-crm-toggle-activity-form">+ Nouvelle activité</button>' +
      '<form class="ipp-crm-form" id="ipp-crm-activity-form">' +
      '<div><label>Type</label><select id="ipp-crm-act-type"><option value="call">Appel</option><option value="task">Tâche</option><option value="meeting">RDV</option></select></div>' +
      '<div><label>Titre</label><input type="text" id="ipp-crm-act-title" placeholder="Ex. Rappeler le client"/></div>' +
      '<div class="ipp-crm-form-row"><div><label>Date</label><input type="date" id="ipp-crm-act-date"/></div><div><label>Heure</label><input type="time" id="ipp-crm-act-time"/></div></div>' +
      activityAssignField +
      '<button type="button" class="ipp-crm-form-submit" id="ipp-crm-act-submit">Créer l\'activité</button></form>' +
      '<p class="ipp-crm-section-label" style="margin-top:16px">Historique des appels</p>' +
      '<div class="ipp-crm-timeline">' + timeline + '</div>' +
      '<button type="button" class="ipp-crm-add-btn" id="ipp-crm-toggle-attempt-form">+ Ajouter une tentative d\'appel</button>' +
      '<form class="ipp-crm-form" id="ipp-crm-attempt-form">' +
      '<div class="ipp-crm-form-row"><div><label>Date</label><input type="date" id="ipp-crm-af-date"/></div><div><label>Heure</label><input type="time" id="ipp-crm-af-time"/></div></div>' +
      '<div><label>Résultat</label><select id="ipp-crm-af-result"><option value="no_answer">Pas de réponse</option><option value="callback">À rappeler</option><option value="interested">Intéressé — à relancer</option><option value="refused">Ne souhaite plus donner suite</option></select></div>' +
      '<div><label>Note (optionnel)</label><textarea id="ipp-crm-af-note" placeholder="Ex. a demandé de rappeler après 17h"></textarea></div>' +
      '<button type="button" class="ipp-crm-form-submit" id="ipp-crm-af-submit">Enregistrer la tentative</button></form>';

    bindFicheEvents(l);
  }

  function nowLocalParts() {
    var d = new Date();
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return { date: d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()), time: pad(d.getHours()) + ":" + pad(d.getMinutes()) };
  }

  function bindFicheEvents(l) {
    var assignSel = document.getElementById("ipp-crm-assign-select");
    if (assignSel) {
      assignSel.addEventListener("change", function () {
        rpc("/my/leads/api/reassign", { mandate_id: l.id, user_id: assignSel.value || null }).then(function (res) {
          if (res && res.ok) { l.assignedTo = assignSel.value ? parseInt(assignSel.value, 10) : null; renderFilterRow(); renderBoard(); renderTeamPanel(); }
        });
      });
    }
    var notes = document.getElementById("ipp-crm-notes");
    if (notes) {
      notes.addEventListener("change", function () {
        rpc("/my/leads/api/notes", { mandate_id: l.id, notes: notes.value }).then(function (res) {
          if (res && res.ok) { l.notes = notes.value; }
        });
      });
    }
    var markVendu = document.getElementById("ipp-crm-mark-vendu");
    if (markVendu) markVendu.addEventListener("click", function () { setStatus(l, "vendu"); });
    var markPerdu = document.getElementById("ipp-crm-mark-perdu");
    if (markPerdu) markPerdu.addEventListener("click", function () { setStatus(l, "perdu"); });

    var toggleActBtn = document.getElementById("ipp-crm-toggle-activity-form");
    if (toggleActBtn) toggleActBtn.addEventListener("click", function () {
      var form = document.getElementById("ipp-crm-activity-form");
      form.classList.toggle("open");
      if (form.classList.contains("open")) {
        var np = nowLocalParts();
        document.getElementById("ipp-crm-act-date").value = np.date;
        document.getElementById("ipp-crm-act-time").value = np.time;
      }
    });
    var actSubmit = document.getElementById("ipp-crm-act-submit");
    if (actSubmit) actSubmit.addEventListener("click", function () {
      var type = document.getElementById("ipp-crm-act-type").value;
      var title = document.getElementById("ipp-crm-act-title").value.trim();
      var date = document.getElementById("ipp-crm-act-date").value;
      var time = document.getElementById("ipp-crm-act-time").value;
      if (!title || !date || !time) return;
      var assignSelEl = document.getElementById("ipp-crm-act-assign");
      var userId = assignSelEl ? assignSelEl.value : null;
      rpc("/my/leads/api/activity/create", { mandate_id: l.id, activity_type: type, title: title, date: date, time: time, user_id: userId || null })
        .then(function (res) {
          if (res && res.ok) { ACTIVITIES.push(res.activity); renderFiche(); if (currentView === "calendar") renderCalendar(); }
        });
    });

    document.querySelectorAll("[data-toggle-activity]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = parseInt(btn.getAttribute("data-toggle-activity"), 10);
        rpc("/my/leads/api/activity/toggle", { activity_id: id }).then(function (res) {
          if (res && res.ok) {
            var a = ACTIVITIES.filter(function (x) { return x.id === id; })[0];
            if (a) a.done = res.done;
            renderFiche();
            if (currentView === "calendar") renderCalendar();
          }
        });
      });
    });

    var toggleAttemptBtn = document.getElementById("ipp-crm-toggle-attempt-form");
    if (toggleAttemptBtn) toggleAttemptBtn.addEventListener("click", function () {
      var form = document.getElementById("ipp-crm-attempt-form");
      form.classList.toggle("open");
      if (form.classList.contains("open")) {
        var np = nowLocalParts();
        document.getElementById("ipp-crm-af-date").value = np.date;
        document.getElementById("ipp-crm-af-time").value = np.time;
      }
    });
    var afSubmit = document.getElementById("ipp-crm-af-submit");
    if (afSubmit) afSubmit.addEventListener("click", function () {
      var date = document.getElementById("ipp-crm-af-date").value;
      var time = document.getElementById("ipp-crm-af-time").value;
      var result = document.getElementById("ipp-crm-af-result").value;
      var note = document.getElementById("ipp-crm-af-note").value.trim();
      if (!date || !time) return;
      rpc("/my/leads/api/attempt/create", { mandate_id: l.id, date: date, time: time, result: result, note: note })
        .then(function (res) {
          if (res && res.ok) {
            l.attempts.push(res.attempt);
            l.status = res.status;
            renderBoard(); renderFiche(); renderFilterRow(); renderTeamPanel();
          }
        });
    });
  }

  function setStatus(l, status) {
    rpc("/my/leads/api/status", { mandate_id: l.id, status: status }).then(function (res) {
      if (res && res.ok) { l.status = res.status; renderBoard(); renderFiche(); renderTeamPanel(); }
    });
  }

  function renderTeamPanel() {
    var panel = document.getElementById("ipp-crm-team-panel");
    if (!IS_MANAGER) {
      var mine = LEADS;
      var relance = mine.filter(function (l) { return l.status === "relance"; }).length;
      var rdv = mine.filter(function (l) { return l.status === "rdv"; }).length;
      var vendu = mine.filter(function (l) { return l.status === "vendu"; }).length;
      panel.innerHTML =
        '<h4>Mes performances</h4><p class="ipp-crm-sub">Vue personnelle — visible seulement par toi.</p>' +
        '<div class="ipp-crm-team-foot" style="border-top:none;padding-top:0"><span>' + mine.length + ' leads assignés</span></div>' +
        '<div class="ipp-crm-team-foot"><span>En relance</span><b>' + relance + '</b></div>' +
        '<div class="ipp-crm-team-foot"><span>RDV fixés</span><b>' + rdv + '</b></div>' +
        '<div class="ipp-crm-team-foot"><span>Vendus</span><b>' + vendu + '</b></div>';
      return;
    }
    var rows = TEAM.map(function (t) {
      var active = LEADS.filter(function (l) { return l.assignedTo === t.id && l.status !== "vendu" && l.status !== "perdu"; });
      var pending = active.filter(function (l) { return l.status === "relance" || l.status === "nouveau"; }).length;
      return (
        '<button class="ipp-crm-team-row ' + (filterMember === t.id ? "active" : "") + '" data-team-filter="' + t.id + '">' +
        '<span class="ipp-crm-avatar">' + esc(t.initials) + '</span><span class="t-name">' + esc(t.name) + '</span>' +
        '<span class="t-stats">' + active.length + ' actifs' + (pending ? " · " + pending + " à relancer" : "") + '</span></button>'
      );
    }).join("");
    var vendus = LEADS.filter(function (l) { return l.status === "vendu"; }).length;
    panel.innerHTML =
      '<h4>Ton équipe</h4><p class="ipp-crm-sub">Répartis les leads et suis l\'avancement de chacun.</p>' +
      '<div class="ipp-crm-team-list">' + rows + '</div>' +
      '<div class="ipp-crm-team-foot"><span>' + LEADS.length + ' leads</span><span><b>' + vendus + '</b> vendu' + (vendus > 1 ? "s" : "") + '</span></div>';
    panel.querySelectorAll("[data-team-filter]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        filterMember = btn.getAttribute("data-team-filter");
        renderFilterRow(); renderBoard(); renderTeamPanel();
      });
    });
  }

  renderFilterRow();
  renderViewTabs();
  renderBoard();
  renderFiche();
  renderTeamPanel();
})();
