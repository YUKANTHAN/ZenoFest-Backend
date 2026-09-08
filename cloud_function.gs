/**
 * ZenoFest Registration - Google Apps Script trigger
 * ---------------------------------------------------
 * Binds to the RAW responses Google Sheet (or the Form itself).
 * Sends every new form submission to the Python backend as a webhook, so
 * the backend can reorganize it and append it to the organized drive sheet.
 *
 * SETUP
 *  1. Paste this into Tools > Script editor on the raw responses sheet.
 *  2. Set BACKEND_URL and WEBHOOK_TOKEN below (or as Script Properties).
 *  3. Run once:  enable triggers -> onFormSubmit -> configureTrigger()
 *  4. Done. Each new submission will POST to your backend.
 */

var BACKEND_URL = ScriptApp.getScriptProperties().getProperty('BACKEND_URL') ||
  'https://zenofest-backend.onrender.com/webhook';
var WEBHOOK_TOKEN = ScriptApp.getScriptProperties().getProperty('WEBHOOK_TOKEN') ||
  'K7x9mZ2pQ5vR8nL4';

/** Create/install the onFormSubmit trigger. Run this once. */
function configureTrigger() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ScriptApp.newTrigger('onFormSubmit')
    .forSpreadsheet(ss)
    .onFormSubmit()
    .create();
  Logger.log('Trigger installed.');
}

/**
 * Called automatically on each form submission.
 * Sends the newly-added row to the Python backend.
 */
function onFormSubmit(e) {
  if (!e || !e.range) {
    Logger.log('No event data; skipping.');
    return;
  }

  var sheet = e.range.getSheet();
  var rowIndex = e.range.getRow();

  // Read the header (row 1) and the new values.
  var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var values = sheet.getRange(rowIndex, 1, 1, sheet.getLastColumn()).getValues()[0];

  var record = {};
  for (var c = 0; c < header.length; c++) {
    // keep only the LAST column if headers repeat (gspread/GAS dedupe naturally)
    record[String(header[c])] = values[c];
  }

  var payload = {
    sheetId: sheet.getParent().getId(),
    row: rowIndex,
    timestamp: values[0],
    email: values[1],
    record: record,
    // Also send the raw flat row so the backend has everything.
    raw: values
  };

  var options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    headers: { 'X-Webhook-Token': WEBHOOK_TOKEN }
  };

  try {
    var resp = UrlFetchApp.fetch(BACKEND_URL, options);
    Logger.log('Backend response ' + resp.getResponseCode() + ': ' + resp.getContentText());
  } catch (err) {
    Logger.log('Error contacting backend: ' + err);
    throw err;
  }
}

/** Optional: test the webhook with the first existing data row. */
function testWebhook() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var values = sheet.getRange(2, 1, 1, sheet.getLastColumn()).getValues()[0];
  var record = {};
  for (var c = 0; c < header.length; c++) { record[String(header[c])] = values[c]; }
  onFormSubmit({ range: sheet.getRange(2, 1, 1, sheet.getLastColumn()) });
  Logger.log('Test sent.');
}
