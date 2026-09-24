/**
 * Telephony Abstraction Layer — renov-aides.fr outbound v2
 * Coller dans les nodes Code n8n ou require via $getWorkflowStaticData.
 * Événements et actions normalisés — indépendants du provider.
 */

const PROVIDERS = ['twilio', 'telnyx', 'vicidial'];

/** @typedef {'call_connected'|'digit_received'|'recording_ready'|'call_ended'|'amd_result'} NormalizedEventType */
/** @typedef {'play_audio'|'hangup'|'record'|'transfer'} NormalizedAction */

/**
 * @returns {object} événement normalisé
 */
function emptyEvent(provider) {
  return {
    event_type: 'call_ended',
    call_sid: '',
    from: '',
    to: '',
    recording_url: '',
    amd_result: 'unknown',
    duration_sec: 0,
    provider: provider || 'twilio',
    raw: {},
  };
}

function normalizePhoneES(phone) {
  if (!phone) return '';
  const d = String(phone).replace(/\D/g, '');
  if (d.length === 9) return '+34' + d;
  if (d.length === 11 && d.startsWith('34')) return '+' + d;
  if (String(phone).trim().startsWith('+')) return '+' + d;
  return d ? '+34' + d : '';
}

// ─── TWILIO ───────────────────────────────────────────────

function normalizeTwilioInbound(body) {
  const b = body || {};
  const callSid = b.CallSid || b.call_sid || '';
  const from = normalizePhoneES(b.From || b.from || '');
  const to = normalizePhoneES(b.To || b.to || '');
  const answeredBy = (b.AnsweredBy || b.answered_by || '').toLowerCase();
  const callStatus = (b.CallStatus || b.call_status || '').toLowerCase();
  const recordingUrl = b.RecordingUrl || b.recording_url || '';
  const digits = b.Digits || b.digits || '';

  if (answeredBy && answeredBy !== 'unknown') {
    const amd = ['machine', 'machine_start', 'machine_end_beep', 'fax'].some((x) =>
      answeredBy.includes(x)
    )
      ? answeredBy.includes('fax')
        ? 'fax'
        : 'machine'
      : 'human';
    return {
      event_type: 'amd_result',
      call_sid: callSid,
      from,
      to,
      recording_url: recordingUrl,
      amd_result: amd,
      duration_sec: parseInt(b.CallDuration || b.duration_sec || 0, 10) || 0,
      provider: 'twilio',
      raw: b,
    };
  }
  if (recordingUrl) {
    return {
      event_type: 'recording_ready',
      call_sid: callSid,
      from,
      to,
      recording_url: recordingUrl,
      amd_result: 'unknown',
      duration_sec: parseInt(b.RecordingDuration || 0, 10) || 0,
      provider: 'twilio',
      raw: b,
    };
  }
  if (digits) {
    return {
      event_type: 'digit_received',
      call_sid: callSid,
      from,
      to,
      recording_url: '',
      amd_result: 'unknown',
      duration_sec: 0,
      provider: 'twilio',
      digits,
      raw: b,
    };
  }
  if (callStatus === 'in-progress' || callStatus === 'answered') {
    return {
      event_type: 'call_connected',
      call_sid: callSid,
      from,
      to,
      recording_url: '',
      amd_result: 'unknown',
      duration_sec: 0,
      provider: 'twilio',
      raw: b,
    };
  }
  if (['completed', 'busy', 'failed', 'no-answer', 'canceled'].includes(callStatus)) {
    return {
      event_type: 'call_ended',
      call_sid: callSid,
      from,
      to,
      recording_url: recordingUrl,
      amd_result: 'unknown',
      duration_sec: parseInt(b.CallDuration || 0, 10) || 0,
      provider: 'twilio',
      raw: b,
    };
  }
  const ev = emptyEvent('twilio');
  ev.call_sid = callSid;
  ev.from = from;
  ev.to = to;
  ev.raw = b;
  return ev;
}

function buildTwilioTwiml(action) {
  const a = action || {};
  if (a.action === 'hangup') {
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>';
  }
  if (a.action === 'play_audio' && a.audio_url) {
    const record = a.record !== false;
    let xml =
      '<?xml version="1.0" encoding="UTF-8"?><Response><Play>' +
      escapeXml(a.audio_url) +
      '</Play>';
    if (record) {
      const actionUrl = escapeXml(a.record_callback_url || '');
      xml +=
        '<Record action="' +
        actionUrl +
        '" maxLength="15" timeout="3" playBeep="false"/>';
    }
    xml += '</Response>';
    return xml;
  }
  if (a.action === 'record' && a.record_callback_url) {
    return (
      '<?xml version="1.0" encoding="UTF-8"?><Response><Record action="' +
      escapeXml(a.record_callback_url) +
      '" maxLength="15" timeout="3" playBeep="false"/></Response>'
    );
  }
  return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>';
}

async function twilioOutboundCall(helpers, env, telephone) {
  const sid = env.TWILIO_ACCOUNT_SID;
  const token = env.TWILIO_AUTH_TOKEN;
  const from = env.TWILIO_PHONE_NUMBER;
  const base = (env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
  const auth = Buffer.from(sid + ':' + token).toString('base64');
  return helpers.httpRequest({
    method: 'POST',
    url: `https://api.twilio.com/2010-04-01/Accounts/${sid}/Calls.json`,
    headers: {
      Authorization: 'Basic ' + auth,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: {
      To: normalizePhoneES(telephone),
      From: from,
      Url: base + '/telephony/twilio/start',
      Record: 'true',
      RecordingStatusCallback: base + '/telephony/twilio/recording',
      MachineDetection: 'DetectMessageEnd',
      AsyncAmdStatusCallback: base + '/telephony/twilio/amd',
      Timeout: '30',
    },
    json: false,
  });
}

// ─── TELNYX ───────────────────────────────────────────────

function normalizeTelnyxInbound(body) {
  const b = body || {};
  const data = b.data || b;
  const payload = data.payload || data;
  const eventType = (data.event_type || b.event_type || '').toLowerCase();
  const callSid = payload.call_control_id || payload.call_session_id || payload.id || '';
  const from = normalizePhoneES(payload.from || payload.from_number || '');
  const to = normalizePhoneES(payload.to || payload.to_number || '');

  const map = {
    'call.answered': 'call_connected',
    'call.recording.saved': 'recording_ready',
    'call.hangup': 'call_ended',
    'call.machine.detection.ended': 'amd_result',
  };
  const event_type = map[eventType] || 'call_ended';
  let amd_result = 'unknown';
  if (event_type === 'amd_result') {
    const r = (payload.result || payload.machine_detection_result || '').toLowerCase();
    amd_result = r.includes('machine') ? 'machine' : r.includes('human') ? 'human' : 'unknown';
  }
  return {
    event_type,
    call_sid: callSid,
    from,
    to,
    recording_url: payload.recording_urls?.mp3 || payload.recording_url || '',
    amd_result,
    duration_sec: parseInt(payload.duration_secs || payload.duration || 0, 10) || 0,
    provider: 'telnyx',
    raw: b,
  };
}

function buildTelnyxTexml(action) {
  return buildTwilioTwiml(action).replace(/TwiML/g, 'TeXML');
}

async function telnyxOutboundCall(helpers, env, telephone) {
  const base = (env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
  return helpers.httpRequest({
    method: 'POST',
    url: 'https://api.telnyx.com/v2/calls',
    headers: {
      Authorization: 'Bearer ' + env.TELNYX_API_KEY,
      'Content-Type': 'application/json',
    },
    body: {
      to: normalizePhoneES(telephone),
      from: env.TELNYX_PHONE_NUMBER,
      connection_id: env.TELNYX_CONNECTION_ID,
      webhook_url: base + '/telephony/telnyx/start',
      record_audio: true,
      record_format: 'mp3',
      answering_machine_detection: 'premium',
    },
    json: true,
  });
}

// ─── VICIDIAL ─────────────────────────────────────────────

function normalizeVicidialInbound(body) {
  const b = body || {};
  const event_type = b.event_type || 'call_ended';
  return {
    event_type,
    call_sid: b.call_sid || b.uniqueid || b.lead_id || '',
    from: normalizePhoneES(b.from || b.phone_number || ''),
    to: normalizePhoneES(b.to || b.outbound_cid || ''),
    recording_url: b.recording_url || b.recording_path || '',
    amd_result: (b.amd_result || b.amd_status || 'unknown').toLowerCase(),
    duration_sec: parseInt(b.duration_sec || b.length_in_sec || 0, 10) || 0,
    provider: 'vicidial',
    raw: b,
  };
}

async function vicidialOutboundCall(helpers, env, telephone) {
  const url =
    env.VICIDIAL_API_URL +
    '?source=doorway_odoo' +
    '&user=' +
    encodeURIComponent(env.VICIDIAL_USER) +
    '&pass=' +
    encodeURIComponent(env.VICIDIAL_PASS) +
    '&function=call_out_number' +
    '&campaign=' +
    encodeURIComponent(env.VICIDIAL_CAMPAIGN || 'renov_es') +
    '&phone_number=' +
    encodeURIComponent(normalizePhoneES(telephone).replace('+', '')) +
    '&phone_code=34' +
    '&outbound_cid=' +
    encodeURIComponent(env.SIP_PHONE_NUMBER || env.TWILIO_PHONE_NUMBER || '');
  const text = await helpers.httpRequest({ method: 'GET', url, json: false });
  return { ok: String(text).includes('SUCCESS') || !String(text).includes('ERROR'), raw: text };
}

// ─── DISPATCH ─────────────────────────────────────────────

function normalizeInbound(provider, body) {
  const p = (provider || 'twilio').toLowerCase();
  if (p === 'telnyx') return normalizeTelnyxInbound(body);
  if (p === 'vicidial') return normalizeVicidialInbound(body);
  return normalizeTwilioInbound(body);
}

function buildProviderResponse(provider, action) {
  const p = (provider || 'twilio').toLowerCase();
  if (p === 'telnyx') return buildTelnyxTexml(action);
  if (p === 'vicidial') {
    return buildTwilioTwiml(action);
  }
  return buildTwilioTwiml(action);
}

async function dispatchOutboundCall(helpers, env, telephone) {
  const provider = (env.TELEPHONY_PROVIDER || 'twilio').toLowerCase();
  if (provider === 'telnyx') return telnyxOutboundCall(helpers, env, telephone);
  if (provider === 'vicidial') return vicidialOutboundCall(helpers, env, telephone);
  return twilioOutboundCall(helpers, env, telephone);
}

function escapeXml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Répliques TTS fixes (cache) — renov-aides ES */
const TTS_CACHE_KEYS = [
  'ouverture',
  'q1_tipo_propiedad',
  'q2_zona',
  'q3_plazo',
  'q4_presupuesto',
  'cierre_rdv',
  'despedida',
];

module.exports = {
  PROVIDERS,
  normalizePhoneES,
  normalizeTwilioInbound,
  normalizeTelnyxInbound,
  normalizeVicidialInbound,
  normalizeInbound,
  buildTwilioTwiml,
  buildTelnyxTexml,
  buildProviderResponse,
  twilioOutboundCall,
  telnyxOutboundCall,
  vicidialOutboundCall,
  dispatchOutboundCall,
  TTS_CACHE_KEYS,
};
