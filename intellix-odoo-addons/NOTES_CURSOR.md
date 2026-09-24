# NOTES CURSOR — Doorway (intellixcrm)

## Ordre

- **Partie A** (`doorway_agents_dashboard`) avant **Partie B** (`doorway_vicidial_campaigns`).
- Partie B dépend de `doorway_agents_dashboard` dans `__manifest__.py`.

## Code

- Chaque modèle = fichier Python séparé + import dans `models/__init__.py`.
- Tester chaque `services/*.py` indépendamment avant intégration dans les vues.
- Dashboard OWL : déclarer JS/CSS dans `__manifest__.py` → `assets` → `web.assets_backend`.

## Infra VPS

- RAM minimum recommandée : **8 GB** (Odoo + VICIdial + Asterisk + agents IA).
- MySQL VICIdial : user `vicidial` → droits **SELECT/INSERT** (et UPDATE) sur DB `asterisk`, port **3307**.

## Webhooks

- ElevenLabs / Retell : configurer dans leurs consoles **après** déploiement HTTPS.
- VICIdial → Odoo : après mise en prod, URL + token webhook.

## Commandes utiles

```bash
curl -sS "http://127.0.0.1:8080/vicidial/non_agent_api.php?function=version&user=doorway&pass=...&source=test"
sudo systemctl stop odoo-server
sudo -u odoo python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf -d intellixcrm -u doorway_agents_dashboard --stop-after-init --http-port=8070
sudo systemctl start odoo-server
```

Règle Cursor synchronisée : `/root/.cursor/rules/doorway-intellixcrm.mdc`
