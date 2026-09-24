# Léa-QC — Procédure de déploiement scellée

> **Règle d'or** : un seul chemin de déploiement. Pas de patch SQLite manuel, pas de demi-déploiement.

## Pourquoi ce document existe

La stabilité de Léa fluctue quand plusieurs composants (n8n, AGI, dialplan, TTS) divergent ou quand un restore écrase des correctifs récents. Ce checklist **scelle les actifs positifs** et impose une gate de non-régression avant tout dialer.

---

## Composants synchronisés

| Composant | Source de vérité (git) | Runtime |
|-----------|-------------------------|---------|
| Moteur conversation | `lib/conversation_sofia_process.js` + `lea_qc_config.js` | n8n SQLite (workflow `03 Conversation Engine`) |
| Workflows n8n | `workflows/*.json` (générés par sync) | n8n SQLite |
| AGI Asterisk | `sealed/n8n_lea_qc.agi` (copie de référence) | `/usr/share/asterisk/agi-bin/n8n_lea_qc.agi` |
| Clips TTS | `sealed/tts_manifest.sha256` | `/var/www/lea-qc-tts/` (nginx `/lea-qc-tts/`) |
 | Dialplan | `/etc/asterisk/extensions_qc_ia.conf` | `SOFIA_LISTEN_DELAY_SEC=0.8`, `SOFIA_LISTEN_DELAY_SHORT_SEC=0.5`, `SOFIA_LISTEN_DELAY_LONG_SEC=1.0`, contexte `86013` |

**Ne jamais** modifier le runtime n8n directement — toujours passer par `lib/` puis deploy.

---

## Déploiement standard (UNE commande)

```bash
/root/lea_deploy.sh
```

Ce script fait **dans l'ordre** :
1. Backup n8n SQLite → `/var/backups/lea_qc/n8n_YYYYMMDD_HHMMSS.sqlite`
2. `sync_workflow_code.py` (lib → workflows JSON)
3. `patch_n8n_sqlite.py` (workflows → n8n DB, atomique via fichier temp)
4. Vérification des marqueurs clés dans le code déployé
5. `/root/lea_regression.sh` (intents + marqueurs n8n)
6. Restart n8n — **rollback auto** si régression échoue

### Dry-run (sync lib seulement, sans toucher n8n)

```bash
/root/lea_deploy.sh --dry-run
```

### Rollback one-command

```bash
/root/lea_deploy.sh --rollback              # dernier backup
/root/lea_deploy.sh --rollback 20260613_182800  # backup précis
```

---

## Non-régression (obligatoire avant dialer > 0)

```bash
/root/lea_regression.sh
```

Tests couverts :
- **Intents** : greeting `oui`, `vendre ma maison`, `cuisine`, `sous-sol` (`tests/intent_regression_standalone.py`)
- **Golden transcripts** : scénarios Martin (`tests/golden_transcripts.json`)
- **Marqueurs n8n** : `normTranscript`, `gVendre`, `recording_b64`, etc.

### Bibliothèque objections

Référence structurée des 26 nœuds brief + statut d'implémentation :

```
/odoo/custom/addons/renovation_conciergerie/n8n/lea_qc/objections_library.yaml
```

Roadmap Phase 2 (Claude INCONNU only) : `OBJECTIONS_ROADMAP.md`

Optionnels :
```bash
LEA_REGRESSION_WEBHOOK=1 /root/lea_regression.sh   # smoke webhook n8n
LEA_REGRESSION_AGI=1 /root/lea_regression.sh       # perl -c AGI
```

**Gate prod** : `auto_dial_level` reste à **0** tant que `/root/lea_regression.sh` n'est pas GREEN + au moins 1 appel test manuel OK.

---

## Actifs scellés (`sealed/`)

| Fichier | Rôle |
|---------|------|
| `MANIFEST.json` | SHA256 des fichiers connus-bons au moment du scellement |
| `conversation_sofia_process.js` | Copie de référence |
| `lea_qc_config.js` | Config clips / variantes A/B |
| `n8n_lea_qc.agi` | AGI de référence |
| `tts_manifest.sha256` | Checksums des MP3 (ne pas régénérer sans intention) |

### Régénérer les TTS (intentionnel uniquement)

```bash
python3 generate_lea_qc_tts.py all   # ElevenLabs — coût API
cd /var/www/lea-qc-tts && sha256sum lea_*.mp3 | sort > ../sealed/tts_manifest.sha256
# Mettre à jour sealed/MANIFEST.json après validation
```

---

## Déploiement AGI (hors lea_deploy.sh)

L'AGI n'est **pas** patché par `lea_deploy.sh`. Procédure séparée :

```bash
cp /odoo/custom/addons/renovation_conciergerie/n8n/lea_qc/sealed/n8n_lea_qc.agi \
   /usr/share/asterisk/agi-bin/n8n_lea_qc.agi
chown asterisk:asterisk /usr/share/asterisk/agi-bin/n8n_lea_qc.agi
perl -c /usr/share/asterisk/agi-bin/n8n_lea_qc.agi
LEA_REGRESSION_AGI=1 /root/lea_regression.sh
```

Comparer avant déploiement :
```bash
sha256sum /usr/share/asterisk/agi-bin/n8n_lea_qc.agi \
  /odoo/custom/addons/renovation_conciergerie/n8n/lea_qc/sealed/n8n_lea_qc.agi
```

---

## Import API (alternative, si token valide)

Si `N8N_API_TOKEN` est à jour :
```bash
python3 import_lea_qc_workflows.py
/root/lea_regression.sh
```

Sinon, utiliser **uniquement** `patch_n8n_sqlite.py` via `lea_deploy.sh`.

---

## Ce qu'il ne faut PLUS faire

- ❌ Patch SQLite à la main sans backup préalable
- ❌ Restore backup n8n du 12 juin (ou autre) sans re-déployer `lib/` ensuite
- ❌ Plusieurs subagents qui touchent n8n/AGI/dialplan en parallèle
- ❌ Monter `auto_dial_level` sans régression GREEN
- ❌ Régénérer les clips TTS « pour tester » (écrase les actifs validés)

---

## Appel test contrôlé (post-deploy)

```bash
asterisk -rx "channel originate Local/14389929200@lea-qc-testcall extension 86013@lea-qc-bridge"
```

Vérifier transcript dans Odoo **Léa-QC Mesure** avant GO dialer.

---

## Tags / versions

- Scellement actuel : `lea-qc-sealed-20260613` (voir `sealed/MANIFEST.json`)
- Backups n8n : `/var/backups/lea_qc/n8n_*.sqlite`
- Runbook opérateur : `/root/LEA_QC_OPERATOR_RUNBOOK.md`
