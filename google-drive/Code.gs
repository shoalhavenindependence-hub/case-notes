/**
 * Shift Case Notes -> Google Drive
 *
 * Receives notes from the Case Notes app and files them in a "Shift Case Notes"
 * folder in your Google Drive:
 *   - one spreadsheet per client ("Case notes - <name>") with Date, Time and
 *     Case note columns, oldest note at the top
 *   - an "All case notes" spreadsheet listing every note (the app uses it to
 *     keep edits and deletes in step)
 *
 * Setup: change SECRET below to a word only you know, save, then run `setup`
 * once from the toolbar to give the script permission. Then
 * Deploy > New deployment > Web app (Execute as: Me, Who has access: Anyone).
 * Put the same secret word into the app.
 */
const SECRET = 'pinkus';

const FOLDER_NAME = 'Shift Case Notes';
const MAIN_BOOK_NAME = 'All case notes';
const TIME_ZONE = 'Australia/Sydney';
const SHEET_NAME = 'Notes';
const HEADERS = ['Note ID', 'Date', 'Time', 'Client', 'Case note', 'Last edited', 'Sent to Drive', 'Timestamp'];
const CLIENT_HEADERS = ['Date', 'Time', 'Case note', 'Last edited'];

/** Run this once from the editor (select "setup" then click Run) to grant access and file existing notes. */
function setup() {
  getFolder_();
  getSheet_();
  rebuildAll();
  Logger.log('Your notes are in: ' + getFolder_().getUrl());
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.secret !== SECRET) return reply_({ ok: false, error: 'wrong_secret' });
    if (body.action === 'ping') return reply_({ ok: true, folder: getFolder_().getUrl(), account: account_() });

    const sheet = getSheet_();
    const lock = LockService.getScriptLock();
    lock.waitLock(25000);
    try {
      const done = [];
      const touched = new Set();
      (body.notes || []).forEach(n => {
        const before = upsert_(sheet, n);
        if (before) touched.add(before);
        touched.add(String(n.client));
        done.push(n.id);
      });
      (body.deleted || []).forEach(id => {
        const before = remove_(sheet, id);
        if (before) touched.add(before);
        done.push(id);
      });
      touched.forEach(name => rebuildClient_(name));
      return reply_({ ok: true, done: done });
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return reply_({ ok: false, error: String(err) });
  }
}

/** The Google account the notes are backed up to, shown in the app. */
function account_() {
  try {
    const owner = getFolder_().getOwner();
    return owner ? { name: owner.getName(), email: owner.getEmail() } : null;
  } catch (err) {
    return null;
  }
}

function doGet() {
  return reply_({ ok: true, message: 'Shift Case Notes sync is running.' });
}

/** Rebuilds every client's spreadsheet from the All case notes list. */
function rebuildAll() {
  const rows = allRows_();
  const names = new Set(rows.map(r => String(r[3])));
  names.forEach(name => rebuildClient_(name, rows));
  const old = getBook_().getSheetByName('By client');
  if (old) getBook_().deleteSheet(old);
  const notes = getSheet_();
  if (notes.isSheetHidden()) notes.showSheet();
}

/* ---------- the All case notes list ---------- */

function upsert_(sheet, n) {
  const row = [n.id, n.date, n.time, n.client, n.text, n.edited || '', new Date(), n.ts || ''];
  const at = findRow_(sheet, n.id);
  let before = '';
  if (at) {
    before = String(sheet.getRange(at, 4).getValue());
    sheet.getRange(at, 1, 1, row.length).setValues([row]);
  } else {
    sheet.appendRow(row);
  }
  return before;
}

function remove_(sheet, id) {
  const at = findRow_(sheet, id);
  if (!at) return '';
  const before = String(sheet.getRange(at, 4).getValue());
  sheet.deleteRow(at);
  return before;
}

function findRow_(sheet, id) {
  const last = sheet.getLastRow();
  if (last < 2) return 0;
  const ids = sheet.getRange(2, 1, last - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) if (String(ids[i][0]) === String(id)) return i + 2;
  return 0;
}

function allRows_() {
  const sheet = getSheet_();
  const last = sheet.getLastRow();
  return last < 2 ? [] : sheet.getRange(2, 1, last - 1, 8).getValues();
}

/* ---------- one spreadsheet per client ---------- */

function rebuildClient_(name, rows) {
  if (!name) return;
  const data = clientRows_(rows || allRows_(), name);
  const book = getClientBook_(name);
  const sheet = book.getSheets()[0];
  sheet.clear();
  sheet.getRange(1, 1, 1, CLIENT_HEADERS.length).setValues([CLIENT_HEADERS])
    .setFontWeight('bold').setBackground('#d6ebe8');
  sheet.setFrozenRows(1);
  if (data.length) {
    sheet.getRange(2, 1, data.length, CLIENT_HEADERS.length).setValues(data).setVerticalAlignment('top');
    sheet.getRange(2, 1, data.length, 1).setNumberFormat('ddd d mmm yyyy');
    sheet.getRange(2, 2, data.length, 1).setNumberFormat('h:mm am/pm');
  }
  sheet.setColumnWidth(1, 130);
  sheet.setColumnWidth(2, 80);
  sheet.setColumnWidth(3, 600);
  sheet.setColumnWidth(4, 160);
  sheet.getRange('C:C').setWrap(true);
}

/**
 * rows: [id, date, time, client, text, edited, sentAt, ts]
 * -> [[date, time, text, edited]] for one client, oldest first.
 * Date and time are real date values when the note has a timestamp, so the sheet can sort and filter them.
 */
function clientRows_(rows, name) {
  return rows
    .map((r, i) => ({ r: r, i: i, ts: Number(r[7]) || 0 }))
    .filter(x => String(x.r[3]) === String(name))
    .sort((a, b) => (a.ts && b.ts) ? a.ts - b.ts : a.i - b.i)
    .map(x => {
      const when = x.ts ? new Date(x.ts) : null;
      return [when || x.r[1], when || x.r[2], x.r[4], x.r[5] || ''];
    });
}

function getClientBook_(name) {
  const props = PropertiesService.getScriptProperties();
  const key = 'CLIENT_' + name;
  const id = props.getProperty(key);
  if (id) { try { return SpreadsheetApp.openById(id); } catch (e) {} }
  const book = SpreadsheetApp.create('Case notes - ' + name);
  book.setSpreadsheetTimeZone(TIME_ZONE);
  book.getSheets()[0].setName('Case notes');
  DriveApp.getFileById(book.getId()).moveTo(getFolder_());
  props.setProperty(key, book.getId());
  return book;
}

/* ---------- folder and main spreadsheet ---------- */

function getFolder_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('FOLDER_ID');
  if (id) { try { return DriveApp.getFolderById(id); } catch (e) {} }
  const folder = DriveApp.createFolder(FOLDER_NAME);
  props.setProperty('FOLDER_ID', folder.getId());
  const main = props.getProperty('SHEET_ID');
  if (main) { try { DriveApp.getFileById(main).moveTo(folder); } catch (e) {} }
  return folder;
}

function getBook_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('SHEET_ID');
  if (id) {
    try {
      const book = SpreadsheetApp.openById(id);
      if (book.getName() === 'Shift Case Notes') book.rename(MAIN_BOOK_NAME);
      return book;
    } catch (e) {}
  }
  const book = SpreadsheetApp.create(MAIN_BOOK_NAME);
  book.setSpreadsheetTimeZone(TIME_ZONE);
  props.setProperty('SHEET_ID', book.getId());
  DriveApp.getFileById(book.getId()).moveTo(getFolder_());
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
  if (sheet.getRange(1, 8).getValue() === '') sheet.getRange(1, 8).setValue('Timestamp').setFontWeight('bold');
  return sheet;
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
