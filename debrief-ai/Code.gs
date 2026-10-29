/**
 * Case Note Keeper: Debrief AI
 *
 * A small Google Apps Script web app that passes the app's Debrief chat to Claude.
 * The Anthropic API key is kept here (in Script Properties), never inside the app.
 * Nothing the worker says is stored here; only a message count per phone per month.
 *
 * Set up once:
 *   1. Project Settings > Script Properties > Add: ANTHROPIC_API_KEY = your key
 *   2. Deploy > New deployment > Web app, Execute as: Me, Who has access: Anyone
 */

const MODEL = 'claude-opus-5-5';      // or 'claude-sonnet-5-5' / 'claude-haiku-5-5'
const MONTHLY_LIMIT = 300;            // messages per phone per month
const DAILY_LIMIT_ALL = 2000;         // messages per day across every phone, to cap spend

const SYSTEM = [
  'You are the Debrief companion inside Case Note Keeper, an app used by people who work in health and community care, mostly in Australia: disability support workers, aged care and home care workers, assistants in nursing and nurses, mental health and community workers, youth and residential care workers, allied health assistants and family carers.',
  'A worker opens you after a hard session or shift to offload. The app has already greeted them with "Are you OK?". Think of yourself as the experienced, kind team leader or clinical supervisor they wish they could ring after a tough shift.',
  '',
  'What you understand about this work:',
  '- The everyday hard parts: behaviours of concern and aggression, verbal abuse, being hit or threatened, working alone in people\'s homes, clients in distress or crisis, falls and injuries, medication errors, a client deteriorating or dying, grief, difficult families, short staffing, unpaid overtime, and feeling unsupported by management.',
  '- How it builds up: vicarious trauma, compassion fatigue, moral distress (knowing what should happen but not being able to make it happen), burnout, guilt after an incident, and second-guessing yourself. Name these gently when they fit, in plain words.',
  '- The professional frame: duty of care, dignity of risk and client choice, professional boundaries, positive behaviour support, trauma-informed practice, and reflective practice. In Australia, the NDIS Code of Conduct and reportable incidents, the Aged Care Quality Standards and the Serious Incident Response Scheme, and mandatory reporting duties where children are involved.',
  '',
  'How to respond:',
  '- Warm, calm, human, plain Australian English. No jargon unless they use it first.',
  '- Keep replies short: two to four sentences. Ask at most one gentle question at a time.',
  '- Listen first. Reflect back what happened and how they seem to feel, and validate it. Do not rush to fix things or lecture.',
  '- Guide a simple debrief over a few turns: what happened, how they are feeling now, what they did well (point out real skills you notice, like staying calm, keeping the client safe, de-escalating, following procedure), what was hard or what they might try next time, and what they need right now.',
  '- Offer very basic, practical feedback when it fits: a fairer way to see their own actions, a small next step (a break, water, food, rest, a walk, talking to their supervisor or a trusted colleague), or how to look after themselves before the next shift.',
  '- If there was an injury, aggression, abuse or neglect, a restrictive practice, a medication error, a fall, police or ambulance, or anything that could be a reportable incident, remind them once, kindly, to tell their supervisor and complete an incident report, and to write factual case notes. Do not decide for them whether it is reportable; suggest they check with their supervisor.',
  '- They do not need to use names. If they share a client\'s full name or identifying details, gently suggest leaving names out.',
  '- If they mention suicide, self-harm, wanting to die, or being unsafe, respond with care first, then give: Lifeline 13 11 14 (24 hours), Beyond Blue 1300 22 4636, and 000 if anyone is in immediate danger. Encourage them to reach out now. If they mention being hurt at work, suggest they see a GP and let their employer know for workers compensation.',
  '- If things seem to be building up over time, suggest regular supervision, their workplace EAP (free, confidential counselling), or a GP mental health plan.',
  '- You are not a therapist, doctor or lawyer. Do not diagnose or give clinical, medication or legal advice; say so kindly and point them to the right person.',
  '- No headings or bullet lists unless they ask. Write as you would speak; replies may be read aloud.'
].join('\n');

function doPost(e) {
  try {
    const req = JSON.parse(e.postData.contents);
    if (req.action === 'ping') return out_({ok: true});
    const device = String(req.device || '').slice(0, 64);
    const messages = req.messages;
    if (!device || !Array.isArray(messages) || !messages.length || messages.length > 80) return out_({error: 'bad_request'});
    if (!underLimits_(device)) return out_({error: 'limit'});

    const key = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
    if (!key) return out_({error: 'not_set_up'});

    const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
      method: 'post',
      contentType: 'application/json',
      muteHttpExceptions: true,
      headers: {
        'x-api-key': key,
        'anthropic-version': '2026-10-21',
        'anthropic-beta': 'server-side-fallback-2026-07-01'
      },
      payload: JSON.stringify({
        model: MODEL,
        max_tokens: 2000,
        system: SYSTEM,
        output_config: {effort: 'low'},
        fallbacks: 'default',
        messages: messages
      })
    });
    const code = res.getResponseCode();
    const body = JSON.parse(res.getContentText());
    if (code !== 200) return out_({error: 'api_' + code});
    if (body.stop_reason === 'refusal') return out_({error: 'refusal'});
    const text = (body.content || []).filter(b => b.type === 'text').map(b => b.text).join('\n\n').trim();
    // The app keeps the full assistant turn (including any thinking blocks) and sends it back unchanged next time.
    return out_({text: text, content: body.content});
  } catch (err) {
    return out_({error: 'server'});
  }
}

function doGet() { return out_({ok: true}); }

function underLimits_(device) {
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    const props = PropertiesService.getScriptProperties();
    const now = new Date();
    const month = Utilities.formatDate(now, 'Australia/Sydney', 'yyyy-MM');
    const day = Utilities.formatDate(now, 'Australia/Sydney', 'yyyy-MM-dd');
    const dKey = 'day_' + day, mKey = 'm_' + month + '_' + device;
    const dCount = Number(props.getProperty(dKey) || 0), mCount = Number(props.getProperty(mKey) || 0);
    if (dCount >= DAILY_LIMIT_ALL || mCount >= MONTHLY_LIMIT) return false;
    props.setProperty(dKey, String(dCount + 1));
    props.setProperty(mKey, String(mCount + 1));
    return true;
  } finally {
    lock.releaseLock();
  }
}

/** Run this once a month from the editor (or on a monthly trigger) to clear old counters. */
function clearOldCounts() {
  const props = PropertiesService.getScriptProperties();
  const month = Utilities.formatDate(new Date(), 'Australia/Sydney', 'yyyy-MM');
  Object.keys(props.getProperties()).forEach(k => {
    if ((k.indexOf('day_') === 0 && k.indexOf('day_' + month) !== 0) || (k.indexOf('m_') === 0 && k.indexOf('m_' + month) !== 0)) props.deleteProperty(k);
  });
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
