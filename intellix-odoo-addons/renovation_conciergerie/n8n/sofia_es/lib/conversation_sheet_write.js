const sp = $input.first().json.sheet_payload || $input.first().json;
if (!sp || !sp.telefono) {
  const engine = $('Sofía Engine').first().json;
  return [{ json: engine }];
}
const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/sofia-es/sheets',
  body: sp,
  json: true,
});
const engine = $('Sofía Engine').first().json;
return [{ json: engine }];
