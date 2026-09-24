# RénoFacile FR (DW_FRB2C) — téléphonie Africa-Con

## CLI France (obligatoire)

| Campagne | Destination | Trunk SIP | CLI affiché (From) |
|----------|-------------|-----------|---------------------|
| **DW_FRB2C** / **DW_FRB2B** | +33 | `Door_App0_FR` | **33424436337** (+33 4 24 43 63 37) |
| **DW_QCB2C** (Léa Québec) | +1 | `Door_App0` | **15817058118** (+1 581 705 8118) |

Africa-Con (Imad) **rejette en SIP 403** les appels vers la France si le From/CLI est canadien.

## Fichiers

- Dialplan : `/etc/asterisk/extensions_renofacile_fr.conf` — `CALLERID` + `Dial(SIP/Door_App0_FR/…)`
- Peers : `/etc/asterisk/sip-vicidial.conf` — `[Door_App0]` (QC) et `[Door_App0_FR]` (`fromuser=33424436337`)
- VICIdial : `vicidial_campaigns.campaign_cid = 33424436337` pour `DW_FRB2C` / `DW_FRB2B`
- Hotfix : `/opt/doorway/campaign_hotfix.sh` → `ensure_fr_campaign_cid()`
- Odoo : `VicidialService.ensure_france_outbound_dialing()` / `ensure_fr_campaign_cid()`

## Test opérateur

```bash
asterisk -rx "sip set debug peer Door_App0_FR"
# puis un appel test +33 — vérifier INVITE From: <sip:33424436337@…>
tail -f /var/log/asterisk/messages
```

## Si 403 persiste

1. Confirmer avec Imad que **33424436337** est bien provisionné pour sortants France sur le trunk IP `168.119.144.57`.
2. Capturer l’INVITE (From / P-Asserted-Identity) et lui renvoyer.
3. ICP Odoo : `doorway_vicidial_campaigns.door_app0_fr_caller_id` si Africa-Con change le numéro.
