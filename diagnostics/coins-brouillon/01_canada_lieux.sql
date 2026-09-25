-- Enquête « lieux qui repassent en brouillon » — LECTURE SEULE.
-- Lancer sur intellix-canada avec une transaction en lecture seule :
--   PGOPTIONS='-c default_transaction_read_only=on' sudo -u postgres psql -d intellixcrm -f 01_canada_lieux.sql
-- Aucune instruction d'écriture dans ce fichier.

\pset pager off
\timing off


\echo '=== 1. Lieux ciblés + lieux témoins (y compris archivés) ==='
SELECT p.id, p.name, p.active, p.state, p.onboarding_status,
       p.write_date, wu.login AS write_user, p.create_date, cu.login AS create_user,
       (p.portal_token IS NOT NULL)         AS a_token_partenaire,
       (p.portal_preview_token IS NOT NULL) AS a_token_apercu
FROM coins_property p
LEFT JOIN res_users wu ON wu.id = p.write_uid
LEFT JOIN res_users cu ON cu.id = p.create_uid
WHERE lower(translate(p.name, 'ÂÀÄÉÈÊËÎÏÔÖÛÙÜÇâàäéèêëîïôöûùüç', 'AAAEEEEIIOOUUUCaaaeeeeiioouuuc'))
      ~ '(asrari|ysabella|nougat|casa alma|villa michelle)'
ORDER BY p.name, p.id;

\echo '=== 2. Doublons potentiels (même nom normalisé, ou nom proche) ==='
SELECT lower(regexp_replace(translate(name, 'ÂÀÄÉÈÊËÎÏÔÖÛÙÜÇâàäéèêëîïôöûùüç', 'AAAEEEEIIOOUUUCaaaeeeeiioouuuc'),
                            '^(riad|villa|la|le|chateau|casa|dar)\s+', '', 'i')) AS cle,
       array_agg(id ORDER BY id) AS ids, array_agg(name ORDER BY id) AS noms,
       array_agg(active ORDER BY id) AS actifs, array_agg(state ORDER BY id) AS etats
FROM coins_property
GROUP BY 1
HAVING count(*) > 1
ORDER BY 1;

\echo '=== 3. Historique de tracking (champs suivis : state, name, ...) sur les lieux ciblés ==='
SELECT m.res_id AS lieu_id, m.date, f.name AS champ,
       v.old_value_char AS ancien, v.new_value_char AS nouveau,
       u.login AS utilisateur, rp.name AS auteur, m.message_type
FROM mail_tracking_value v
JOIN mail_message m      ON m.id = v.mail_message_id
JOIN ir_model_fields f   ON f.id = v.field_id
LEFT JOIN res_users u    ON u.id = m.create_uid
LEFT JOIN res_partner rp ON rp.id = m.author_id
WHERE m.model = 'coins.property'
  AND m.res_id IN (SELECT id FROM coins_property
                   WHERE lower(translate(name, 'ÂÀÄÉÈÊËÎÏÔÖÛÙÜÇâàäéèêëîïôöûùüç', 'AAAEEEEIIOOUUUCaaaeeeeiioouuuc'))
                         ~ '(asrari|ysabella|nougat)')
ORDER BY m.res_id, m.date DESC
LIMIT 200;

\echo '=== 4. Messages chatter (onboarding_status n''est PAS suivi : on cherche les traces texte) ==='
SELECT m.res_id AS lieu_id, m.date, u.login AS utilisateur, rp.name AS auteur, m.message_type,
       left(regexp_replace(coalesce(m.body::text, ''), '<[^>]+>', '', 'g'), 160) AS extrait
FROM mail_message m
LEFT JOIN res_users u    ON u.id = m.create_uid
LEFT JOIN res_partner rp ON rp.id = m.author_id
WHERE m.model = 'coins.property'
  AND m.res_id IN (SELECT id FROM coins_property
                   WHERE lower(translate(name, 'ÂÀÄÉÈÊËÎÏÔÖÛÙÜÇâàäéèêëîïôöûùüç', 'AAAEEEEIIOOUUUCaaaeeeeiioouuuc'))
                         ~ '(asrari|ysabella|nougat)')
  AND m.date > now() - interval '45 days'
ORDER BY m.res_id, m.date DESC
LIMIT 300;

\echo '=== 5. Mails de notification « soumission partenaire » envoyés à Karine (trace du portail) ==='
SELECT mm.id, mm.create_date, mm.state, left(mm.subject, 140) AS sujet
FROM mail_mail mm
WHERE mm.create_date > now() - interval '45 days'
  AND (mm.subject ILIKE '%asrari%' OR mm.subject ILIKE '%ysabella%' OR mm.subject ILIKE '%nougat%')
ORDER BY mm.create_date DESC
LIMIT 100;

\echo '=== 6. Crons actifs (tous modèles) ==='
SELECT c.id, c.cron_name, im.model, c.interval_number, c.interval_type,
       c.nextcall, c.lastcall, u.login AS user_exec,
       left(regexp_replace(coalesce(s.code, ''), '\s+', ' ', 'g'), 180) AS code
FROM ir_cron c
JOIN ir_act_server s ON s.id = c.ir_actions_server_id
LEFT JOIN ir_model im ON im.id = s.model_id
LEFT JOIN res_users u ON u.id = c.user_id
WHERE c.active
ORDER BY c.nextcall;

\echo '=== 7. Actions automatisées (base.automation) et actions serveur touchant coins.property ==='
SELECT s.id, s.name, s.state, im.model,
       left(regexp_replace(coalesce(s.code, ''), '\s+', ' ', 'g'), 240) AS code
FROM ir_act_server s
LEFT JOIN ir_model im ON im.id = s.model_id
WHERE im.model = 'coins.property'
   OR s.code ILIKE '%coins.property%'
   OR s.code ILIKE '%onboarding_status%';
-- base.automation peut ne pas être installé : l'erreur éventuelle est sans conséquence.
SELECT a.id, a.name, a.active, a.trigger, im.model
FROM base_automation a LEFT JOIN ir_model im ON im.id = a.model_id
WHERE a.active;

\echo '=== 8. Leads CRM liés aux lieux ciblés (bouton « envoyer le lien » → lien_envoye) ==='
SELECT l.id, l.name, l.active, l.coins_property_id, l.write_date, u.login AS write_user
FROM crm_lead l LEFT JOIN res_users u ON u.id = l.write_uid
WHERE l.coins_property_id IN (SELECT id FROM coins_property
                              WHERE lower(translate(name, 'ÂÀÄÉÈÊËÎÏÔÖÛÙÜÇâàäéèêëîïôöûùüç', 'AAAEEEEIIOOUUUCaaaeeeeiioouuuc'))
                                    ~ '(asrari|ysabella|nougat)')
ORDER BY l.coins_property_id, l.write_date DESC;

\echo '=== 9. Utilisateurs API / techniques récents (write sur coins_property sur 7 jours) ==='
SELECT u.login, count(*) AS nb_lieux, max(p.write_date) AS dernier_write
FROM coins_property p JOIN res_users u ON u.id = p.write_uid
WHERE p.write_date > now() - interval '7 days'
GROUP BY u.login ORDER BY dernier_write DESC;

\echo '=== 10. Comparaison des champs : 3 lieux ciblés vs Casa Alma / Villa Michelle ==='
SELECT p.id, p.name, p.state, p.onboarding_status, p.onboarding_kind, p.niveau_visibilite,
       p.category_codes, p.map_zone, p.map_pillar,
       (p.latitude <> 0 AND p.longitude <> 0)                   AS gps,
       (SELECT count(*) FROM coins_property_photo ph WHERE ph.property_id = p.id) AS nb_photos,
       (SELECT count(*) FROM ir_attachment a WHERE a.res_model = 'coins.property'
               AND a.res_id = p.id AND a.res_field = 'image_1920') AS photo_principale,
       (SELECT count(*) FROM coins_fiche_video v WHERE v.fiche_id = p.id) AS nb_videos,
       (SELECT count(*) FROM coins_property_room r WHERE r.property_id = p.id AND r.active) AS nb_chambres,
       (p.owner_id IS NOT NULL)                                 AS partenaire_lie,
       (p.portal_token IS NOT NULL)                             AS token_portail,
       (SELECT count(*) FROM intellix_riad_establishment e WHERE e.property_id = p.id) AS etablissement_riad,
       (SELECT count(*) FROM coins_channex_mapping cm WHERE cm.property_id = p.id)     AS mappings_channex,
       length(coalesce(p.description::text, ''))               AS len_description,
       length(coalesce(p.narrative::text, ''))                 AS len_narrative
FROM coins_property p
WHERE lower(translate(p.name, 'ÂÀÄÉÈÊËÎÏÔÖÛÙÜÇâàäéèêëîïôöûùüç', 'AAAEEEEIIOOUUUCaaaeeeeiioouuuc'))
      ~ '(asrari|ysabella|nougat|casa alma|villa michelle)'
ORDER BY p.name;
