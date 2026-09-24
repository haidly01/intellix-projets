const b = $input.first().json.body || $input.first().json;
const recUrlRaw = b.RecordingUrl || '';
const recUrl = recUrlRaw && !recUrlRaw.endsWith('.mp3') ? recUrlRaw + '.mp3' : recUrlRaw;
const ev = {
  event_type: 'recording_ready',
  call_sid: b.CallSid || '',
  recording_url: recUrlRaw,
  duration_sec: parseInt(b.RecordingDuration || 0, 10) || 0,
  provider: 'twilio',
  to: b.To || '',
  from: b.From || '',
  raw: b,
};
const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
const recTimeout = parseInt($env.SOFIA_RECORD_TIMEOUT || '5', 10) || 5;
const recMax = parseInt($env.SOFIA_RECORD_MAXLENGTH || '10', 10) || 10;
let recording_b64 = '';
const twSid = ($env.TWILIO_ACCOUNT_SID || '').trim();
const twToken = ($env.TWILIO_AUTH_TOKEN || '').trim();
const mp3Url = recUrl || (recUrlRaw ? (recUrlRaw.endsWith('.mp3') ? recUrlRaw : recUrlRaw + '.mp3') : '');
if (mp3Url && twSid && twToken) {
  try {
    const audioBuf = await this.helpers.httpRequest({
      method: 'GET',
      url: mp3Url,
      headers: {
        Authorization: 'Basic ' + Buffer.from(twSid + ':' + twToken).toString('base64'),
      },
      encoding: 'arraybuffer',
    });
    recording_b64 = Buffer.from(audioBuf).toString('base64');
  } catch (e) {
    recording_b64 = '';
  }
}
if (recording_b64) ev.recording_b64 = recording_b64;
const res = await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/renov/conversation',
  body: ev,
  json: true,
  timeout: 30000,
});
const audio = res.audio_url || '';
const action = res.action || 'play_audio';
let twiml = '<?xml version="1.0" encoding="UTF-8"?><Response>';
if (audio) {
  twiml += '<Play>' + audio + '</Play>';
}
const pauseSec = parseInt($env.SOFIA_RECORD_PAUSE_SEC || '2', 10) || 2;
if (action === 'hangup' || res.qualified) {
  twiml += '<Hangup/>';
} else if (audio) {
  twiml += '<Pause length="' + pauseSec + '"/><Record action="' + base + '/telephony/twilio/transcribe" maxLength="' + recMax + '" timeout="' + recTimeout + '" playBeep="false" trim="trim-silence"/>';
} else {
  twiml += '<Hangup/>';
}
twiml += '</Response>';
return [{ json: { twiml, normalized: ev, engine: res } }];
