# IntelliX — projets (code seul)

Copie du code de production au 2026-09-24, sans secrets, sauvegardes ni médias.

| Dossier | Origine | Contenu |
|---|---|---|
| `intellix-odoo-addons/` | serveur intellix-canada, `/odoo/custom/addons` | modules Odoo 19 (doorway_*, coins_marocain*, intellix_*, jason_thomas_assurance, …) |
| `coinsmarocain-site/` | serveur intellix-france, `/var/www/coinsmarocain` | site statique coinsmarocain.com (HTML/CSS/JS/JSON ; images et vidéos exclues) |
| `maisonrecherchee-site/` | serveur intellix-france, `/var/www/sites/maisonrecherchee.com/public` | site statique maisonrecherchee.com (images exclues) |

Règles : ne jamais committer de jeton, mot de passe ou fichier `.env`. Les serveurs restent la source de vérité pour la production.
