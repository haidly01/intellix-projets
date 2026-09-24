-- France DW_FRB2C : 10h-20h Paris, pause déjeuner 13h-14h.
-- HHMM serveur Toronto = heure Paris - 6h (gmt_offset lead 0).

INSERT INTO vicidial_call_times (
  call_time_id, call_time_name, call_time_comments,
  ct_default_start, ct_default_stop,
  ct_sunday_start, ct_sunday_stop,
  ct_monday_start, ct_monday_stop,
  ct_tuesday_start, ct_tuesday_stop,
  ct_wednesday_start, ct_wednesday_stop,
  ct_thursday_start, ct_thursday_stop,
  ct_friday_start, ct_friday_stop,
  ct_saturday_start, ct_saturday_stop,
  user_group
) VALUES (
  'FR9AM1PM', 'France 10h-13h Paris', 'Matin légal FR — srv 400-700',
  400, 700,
  900, 900,
  400, 700, 400, 700, 400, 700, 400, 700, 400, 700,
  400, 700,
  '---ALL---'
) ON DUPLICATE KEY UPDATE
  call_time_name=VALUES(call_time_name),
  call_time_comments=VALUES(call_time_comments),
  ct_default_start=VALUES(ct_default_start),
  ct_default_stop=VALUES(ct_default_stop),
  ct_sunday_start=VALUES(ct_sunday_start),
  ct_sunday_stop=VALUES(ct_sunday_stop),
  ct_monday_start=VALUES(ct_monday_start),
  ct_monday_stop=VALUES(ct_monday_stop),
  ct_tuesday_start=VALUES(ct_tuesday_start),
  ct_tuesday_stop=VALUES(ct_tuesday_stop),
  ct_wednesday_start=VALUES(ct_wednesday_start),
  ct_wednesday_stop=VALUES(ct_wednesday_stop),
  ct_thursday_start=VALUES(ct_thursday_start),
  ct_thursday_stop=VALUES(ct_thursday_stop),
  ct_friday_start=VALUES(ct_friday_start),
  ct_friday_stop=VALUES(ct_friday_stop),
  ct_saturday_start=VALUES(ct_saturday_start),
  ct_saturday_stop=VALUES(ct_saturday_stop);

INSERT INTO vicidial_call_times (
  call_time_id, call_time_name, call_time_comments,
  ct_default_start, ct_default_stop,
  ct_sunday_start, ct_sunday_stop,
  ct_monday_start, ct_monday_stop,
  ct_tuesday_start, ct_tuesday_stop,
  ct_wednesday_start, ct_wednesday_stop,
  ct_thursday_start, ct_thursday_stop,
  ct_friday_start, ct_friday_stop,
  ct_saturday_start, ct_saturday_stop,
  user_group
) VALUES (
  'FR2PM7PM', 'France 14h-20h Paris', 'Après-midi légal FR — srv 800-1400',
  800, 1400,
  900, 900,
  800, 1400, 800, 1400, 800, 1400, 800, 1400, 800, 1400,
  800, 1400,
  '---ALL---'
) ON DUPLICATE KEY UPDATE
  call_time_name=VALUES(call_time_name),
  call_time_comments=VALUES(call_time_comments),
  ct_default_start=VALUES(ct_default_start),
  ct_default_stop=VALUES(ct_default_stop),
  ct_sunday_start=VALUES(ct_sunday_start),
  ct_sunday_stop=VALUES(ct_sunday_stop),
  ct_monday_start=VALUES(ct_monday_start),
  ct_monday_stop=VALUES(ct_monday_stop),
  ct_tuesday_start=VALUES(ct_tuesday_start),
  ct_tuesday_stop=VALUES(ct_tuesday_stop),
  ct_wednesday_start=VALUES(ct_wednesday_start),
  ct_wednesday_stop=VALUES(ct_wednesday_stop),
  ct_thursday_start=VALUES(ct_thursday_start),
  ct_thursday_stop=VALUES(ct_thursday_stop),
  ct_friday_start=VALUES(ct_friday_start),
  ct_friday_stop=VALUES(ct_friday_stop),
  ct_saturday_start=VALUES(ct_saturday_start),
  ct_saturday_stop=VALUES(ct_saturday_stop);

INSERT INTO vicidial_call_times (
  call_time_id, call_time_name, call_time_comments,
  ct_default_start, ct_default_stop,
  ct_sunday_start, ct_sunday_stop,
  ct_monday_start, ct_monday_stop,
  ct_tuesday_start, ct_tuesday_stop,
  ct_wednesday_start, ct_wednesday_stop,
  ct_thursday_start, ct_thursday_stop,
  ct_friday_start, ct_friday_stop,
  ct_saturday_start, ct_saturday_stop,
  user_group
) VALUES (
  'FRLUNCH', 'France pause déjeuner', 'Blocage 13h-14h Paris — srv 700-700',
  700, 700,
  900, 900,
  700, 700, 700, 700, 700, 700, 700, 700, 700, 700,
  700, 700,
  '---ALL---'
) ON DUPLICATE KEY UPDATE
  call_time_name=VALUES(call_time_name),
  call_time_comments=VALUES(call_time_comments);
