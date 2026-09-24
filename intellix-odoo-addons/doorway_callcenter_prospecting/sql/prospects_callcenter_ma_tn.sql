-- Table Supabase (optionnelle — miroir Odoo doorway.callcenter.prospect)
CREATE TABLE IF NOT EXISTS prospects_callcenter_ma_tn (
  id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  company_name        TEXT NOT NULL,
  phone               TEXT NOT NULL,
  phone_raw           TEXT,
  whatsapp            TEXT,
  email               TEXT,
  city                TEXT,
  country             CHAR(2),
  source              TEXT,
  website             TEXT,
  contact_name        TEXT,
  estimated_agents    TEXT,
  twilio_valid        BOOLEAN,
  line_type           TEXT,
  carrier             TEXT,
  whatsapp_capable    BOOLEAN DEFAULT false,
  contacted_j0        BOOLEAN DEFAULT false,
  contacted_j0_at     TIMESTAMPTZ,
  contacted_j2        BOOLEAN DEFAULT false,
  contacted_j2_at     TIMESTAMPTZ,
  contacted_j5        BOOLEAN DEFAULT false,
  contacted_j5_at     TIMESTAMPTZ,
  last_reply          TEXT,
  last_reply_at       TIMESTAMPTZ,
  reply_intent        TEXT,
  odoo_lead_id        INTEGER,
  odoo_prospect_id    INTEGER,
  status              TEXT DEFAULT 'NEW',
  demo_scheduled_at   TIMESTAMPTZ,
  extracted_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),
  notes               TEXT,
  UNIQUE(phone)
);

CREATE INDEX IF NOT EXISTS idx_prospects_country ON prospects_callcenter_ma_tn(country);
CREATE INDEX IF NOT EXISTS idx_prospects_whatsapp ON prospects_callcenter_ma_tn(whatsapp_capable);
CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects_callcenter_ma_tn(status);
