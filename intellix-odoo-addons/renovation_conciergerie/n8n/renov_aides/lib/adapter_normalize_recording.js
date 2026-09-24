const b = $input.first().json.body || $input.first().json;
const dur = parseInt(b.RecordingDuration || 0, 10) || 0;
const ev = {
  event_type: dur > 25 ? 'call_ended' : 'recording_ready',
  call_sid: b.CallSid || '',
  from: b.From || '',
  to: b.To || '',
  recording_url: b.RecordingUrl || '',
  amd_result: 'unknown',
  duration_sec: dur,
  provider: 'twilio',
  raw: b,
};
return [{ json: ev }];
