/**
 * Shift Case Notes -> Google Drive
 *
 * Receives notes from the Case Notes app and keeps them in a Google Sheet
 * called "Shift Case Notes" in your Google Drive (created the first time).
 *
 * Setup: change SECRET below to a word only you know, then
 * Deploy > New deployment > Web app (Execute as: Me, Who has access: Anyone).
 * Put the same secret word into the app.
 */
const SECRET = 'change-me';

const SHEET_NAME = 'Notes';
const HEADERS = ['Note ID', 'Date', 'Time', 'Client', 'Case note', 'Last edited', 'Sent to Drive'];

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SECRET) return reply_({ ok: false, error: 'wrong_secret' });
    if (body.action === 'ping') return reply_({ ok: true, sheet: getBook_().getUrl() });

    const sheet = getSheet_();
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try {
      const done = [];
      (body.notes || []).forEach(n => { upsert_(sheet, n); done.push(n.id); });
      (body.deleted || []).forEach(id => { remove_(sheet, id); done.push(id); });
      return reply_({ ok: true, done: done });
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return reply_({ ok: false, error: String(err) });
  }
}

function doGet() {
  return reply_({ ok: true, message: 'Shift Case Notes sync is running.' });
}

function upsert_(sheet, n) {
  const row = [n.id, n.date, n.time, n.client, n.text, n.edited || '', new Date()];
  const at = findRow_(sheet, n.id);
  if (at) sheet.getRange(at, 1, 1, row.length).setValues([row]);
  else sheet.appendRow(row);
}

function remove_(sheet, id) {
  const at = findRow_(sheet, id);
  if (at) sheet.deleteRow(at);
}

function findRow_(sheet, id) {
  const last = sheet.getLastRow();
  if (last < 2) return 0;
  const ids = sheet.getRange(2, 1, last - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) if (String(ids[i][0]) === String(id)) return i + 2;
  return 0;
}

function getBook_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('SHEET_ID');
  if (id) { try { return SpreadsheetApp.openById(id); } catch (e) {} }
  const book = SpreadsheetApp.create('Shift Case Notes');
  props.setProperty('SHEET_ID', book.getId());
  return book;
}

function getSheet_() {
  const book = getBook_();
  let sheet = book.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = book.getSheets()[0];
    sheet.setName(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
    sheet.setColumnWidth(5, 500);
    sheet.getRange('E:E').setWrap(true);
    sheet.hideColumns(1);
  }
  return sheet;
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
