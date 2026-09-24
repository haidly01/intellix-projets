const sp = $input.first().json.sheet_payload || $input.first().json;
if (!sp || !sp.telefono) {
  const engine = $('Sofía Engine').first().json;
  return [{ json: engine }];
}
const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/sofia-es-demo/sheets',
  body: {
    ...sp,
    sheet_name: sp.sheet_name || $env.GOOGLE_SHEETS_TAB_DEMO || 'Leads_Sofia_Demo_Abdallah',
  },
  json: true,
});
const engine = $('Sofía Engine').first().json;
return [{ json: engine }];
