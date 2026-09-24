(function () {
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function byId(menus, id) {
    return (menus || []).find(function (menu) { return menu.id === id; }) || null;
  }

  function itemsList(items) {
    return "<ul>" + (items || []).map(function (item) {
      return "<li>" + esc(item) + "</li>";
    }).join("") + "</ul>";
  }

  function groupesHtml(groupes) {
    var count = (groupes || []).length;
    var cols = count >= 3 ? "cm-groupes--3" : count === 2 ? "cm-groupes--2" : "";
    return '<div class="cm-groupes ' + cols + '">' + (groupes || []).map(function (groupe) {
      return "<div><h5>" + esc(groupe.nom) + "</h5>" + itemsList(groupe.items) + "</div>";
    }).join("") + "</div>";
  }

  function platsHtml(plats) {
    return '<ul class="cm-plats">' + (plats || []).map(function (plat) {
      var details = plat.details
        ? '<span class="cm-plat-details">' + esc(plat.details) + "</span>"
        : "";
      return '<li><span class="cm-plat-nom">' + esc(plat.nom) + "</span>" + details + "</li>";
    }).join("") + "</ul>";
  }

  function etapeHtml(etape) {
    var featured = etape.miseEnAvant ? " cm-etape--featured" : "";
    var body = etape.groupes ? groupesHtml(etape.groupes) : platsHtml(etape.plats);
    return (
      '<section class="cm-etape' + featured + '">' +
        '<span class="cm-etape-label" aria-hidden="true">◆</span>' +
        "<h4>" + esc(etape.titre) + "</h4>" +
        (etape.sousTitre ? '<p class="cm-etape-sub">' + esc(etape.sousTitre) + "</p>" : "") +
        body +
      "</section>"
    );
  }

  function traditionnelHtml(menu) {
    return (
      '<header class="cm-menu-card-head">' +
        '<p class="cm-menu-card-kicker">' + esc(menu.sousTitre) + "</p>" +
        "<h3>" + esc(menu.titre) + "</h3>" +
        '<p class="cm-menu-card-desc">' + esc(menu.description) + "</p>" +
      "</header>" +
      (menu.etapes || []).map(etapeHtml).join("")
    );
  }

  function formuleValue(formule, key) {
    if (key === "prixParPersonne") return formule.prixAffiche || "";
    return formule[key] || "";
  }

  function mixTableHtml(menu, ui) {
    var labels = (ui && ui.rowLabels) || {};
    var formules = menu.formules || [];
    var colonnes = menu.colonnes || [];
    var head = "<tr><th scope=\"col\"></th>" + formules.map(function (formule) {
      var featured = formule.miseEnAvant ? ' class="is-featured"' : "";
      var badge = formule.miseEnAvant && ui.populaire
        ? '<span class="cm-mix-badge">' + esc(ui.populaire) + "</span>"
        : "";
      return "<th scope=\"col\"" + featured + ">" + esc(formule.nom) + badge + "</th>";
    }).join("") + "</tr>";

    var body = colonnes.map(function (key) {
      var price = key === "prixParPersonne";
      return "<tr><th scope=\"row\">" + esc(labels[key] || key) + "</th>" + formules.map(function (formule) {
        var featured = formule.miseEnAvant ? ' class="is-featured"' : "";
        var value = esc(formuleValue(formule, key));
        if (price) value = '<span class="cm-mix-price">' + value + "</span>";
        return "<td" + featured + ">" + value + "</td>";
      }).join("") + "</tr>";
    }).join("");

    return '<div class="cm-mix-table-wrap"><table class="cm-mix-table"><thead>' +
      head + "</thead><tbody>" + body + "</tbody></table></div>";
  }

  function mixCardsHtml(menu, ui) {
    var labels = (ui && ui.rowLabels) || {};
    var colonnes = menu.colonnes || [];
    return '<div class="cm-mix-cards">' + (menu.formules || []).map(function (formule) {
      var featured = formule.miseEnAvant ? " is-featured" : "";
      var badge = formule.miseEnAvant && ui.populaire
        ? '<span class="cm-mix-badge">' + esc(ui.populaire) + "</span>"
        : "";
      var rows = colonnes.filter(function (key) { return key !== "prixParPersonne"; }).map(function (key) {
        return "<dt>" + esc(labels[key] || key) + "</dt><dd>" + esc(formuleValue(formule, key)) + "</dd>";
      }).join("");
      return (
        '<article class="cm-mix-card' + featured + '">' +
          "<h4>" + esc(formule.nom) + " " + badge + "</h4>" +
          '<p class="cm-mix-card-price">' + esc(formule.prixAffiche) + "</p>" +
          "<dl>" + rows + "</dl>" +
        "</article>"
      );
    }).join("") + "</div>";
  }

  function mixHtml(menu, ui) {
    var note = menu.noteDistinction || {};
    return (
      '<header class="cm-menu-card-head">' +
        '<p class="cm-menu-card-kicker">' + esc(menu.sousTitre) + "</p>" +
        "<h3>" + esc(menu.titre) + "</h3>" +
        '<p class="cm-menu-card-desc">' + esc(menu.description) + "</p>" +
      "</header>" +
      mixTableHtml(menu, ui) +
      mixCardsHtml(menu, ui) +
      '<aside class="cm-mix-note">' +
        "<h4>" + esc(note.titre || "") + "</h4>" +
        "<p>" + esc(note.texte || "") + "</p>" +
      "</aside>"
    );
  }

  function render(root, data) {
    var section = data.section || {};
    var ui = data.ui || {};
    var traditionnel = byId(data.menus, "menu-traditionnel");
    var mix = byId(data.menus, "menu-mix-3-formules");
    var ctaHref = root.getAttribute("data-cta-href") || "/contact";

    root.innerHTML =
      '<p class="cm-menus-brand">' + esc(section.marque) + "</p>" +
      '<header class="cm-menus-head">' +
        "<h2>" + esc(section.titre) + "</h2>" +
        '<p class="cm-menus-subtitle">' + esc(section.sousTitre) + "</p>" +
        '<div class="cm-menus-sep" aria-hidden="true">◆</div>' +
        '<p class="cm-menus-intro">' + esc(section.intro) + "</p>" +
        (ui.exemples ? '<p class="cm-menus-examples">' + esc(ui.exemples) + "</p>" : "") +
      "</header>" +
      '<div class="cm-menus-tabs" role="tablist" aria-label="' + esc(section.titre) + '">' +
        '<button class="cm-menus-tab" type="button" role="tab" id="tab-menu-traditionnel" aria-controls="panel-menu-traditionnel" aria-selected="true">' +
          esc(ui.tabTraditionnel || traditionnel.titre) +
        "</button>" +
        '<button class="cm-menus-tab" type="button" role="tab" id="tab-menu-mix" aria-controls="panel-menu-mix" aria-selected="false">' +
          esc(ui.tabMix || mix.titre) +
        "</button>" +
      "</div>" +
      '<div class="cm-menus-panel" id="panel-menu-traditionnel" role="tabpanel" aria-labelledby="tab-menu-traditionnel">' +
        traditionnelHtml(traditionnel) +
      "</div>" +
      '<div class="cm-menus-panel" id="panel-menu-mix" role="tabpanel" aria-labelledby="tab-menu-mix" hidden>' +
        mixHtml(mix, ui) +
      "</div>" +
      '<div class="cm-menus-cta">' +
        '<a class="btn" href="' + esc(ctaHref) + '">' + esc(ui.cta) + "</a>" +
        '<p class="cm-menus-cta-note">' + esc(ui.ctaNote) + "</p>" +
        '<p class="cm-menus-price-note">' + esc(ui.prixIndicatif) + "</p>" +
        '<p class="cm-menus-foot">' + esc(section.lieu) + "</p>" +
      "</div>";

    bindTabs(root);
    selectFromHash(root);
    window.addEventListener("hashchange", function () { selectFromHash(root); });
  }

  function selectTab(root, panelId) {
    var tabs = root.querySelectorAll(".cm-menus-tab");
    var panels = root.querySelectorAll(".cm-menus-panel");
    tabs.forEach(function (tab) {
      var on = tab.getAttribute("aria-controls") === panelId;
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.id !== panelId;
    });
  }

  function bindTabs(root) {
    root.querySelectorAll(".cm-menus-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        var panelId = tab.getAttribute("aria-controls");
        selectTab(root, panelId);
        if (panelId === "panel-menu-mix") {
          history.replaceState(null, "", "#menu-mix");
        } else {
          history.replaceState(null, "", "#menu");
        }
      });
    });
  }

  function selectFromHash(root) {
    if (location.hash === "#menu-mix") selectTab(root, "panel-menu-mix");
  }

  function init(root) {
    var src = root.getAttribute("data-menus-src");
    if (!src) return;
    fetch(src, { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("menus " + res.status);
        return res.json();
      })
      .then(function (data) { render(root, data); })
      .catch(function () {
        root.innerHTML = "";
      });
  }

  document.querySelectorAll("[data-menus-src]").forEach(init);
})();
