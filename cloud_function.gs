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

var BACKEND_URL = 'https://zenofest-backend.onrender.com/webhook';
var WEBHOOK_TOKEN = 'K7x9mZ2pQ5vR8nL4';
var SEND_EMAILS = 'true';

/** Create/install the onFormSubmit trigger. Run this once. Idempotent:
 *  removes any existing onFormSubmit triggers before installing a fresh one. */
function configureTrigger() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'onFormSubmit') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger('onFormSubmit')
    .forSpreadsheet(ss)
    .onFormSubmit()
    .create();
  Logger.log('Trigger reinstalled (old ones removed).');
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
    var respText = resp.getContentText();
    Logger.log('Backend response ' + resp.getResponseCode() + ': ' + respText);
    if (resp.getResponseCode() === 200 && SEND_EMAILS === 'true') {
      var parsed = JSON.parse(respText);
      if (parsed && parsed.rows && parsed.rows.length > 0) {
        for (var i = 0; i < parsed.rows.length; i++) {
          sendConfirmationEmail(parsed.rows[i]);
        }
      } else {
        Logger.log('No rows returned by backend; skipping email.');
      }
    }
  } catch (err) {
    Logger.log('Error contacting backend: ' + err);
    throw err;
  }
}

function sendConfirmationEmail(row) {
  var toEmail = row.email;
  if (!toEmail) {
    Logger.log('No email found in row; skipping email.');
    return;
  }

  var teamId = row.team_id || 'N/A';
  var teamName = row.team_name || 'N/A';
  var college = row.college || 'N/A';
  var leaderName = row.leader_name || 'N/A';
  var teamSize = row.team_size || 'N/A';
  var techEvent = row.tech_event || 'N/A';
  var nonTechEvent = row.non_tech_event || 'N/A';
  var foodPref = row.food_preference || 'N/A';

  var subject = 'You are registered for ZenoFest 2026 - ' + teamName + ' (' + teamId + ')';

  // Gather team members (leader first, then the rest).
  var members = [];
  members.push({ role: 'TEAM LEADER', name: leaderName, contact: row.leader_contact || '', food: row.leader_food || row.food_preference || foodPref });
  if (row.members && row.members.length) {
    for (var mi = 0; mi < row.members.length; mi++) {
      var m = row.members[mi];
      if (m && m.name) {
        members.push({ role: 'MEMBER ' + (mi + 2), name: m.name, contact: m.contact || '', food: m.food || foodPref });
      }
    }
  }

  // Build summary rows for the HTML table.
  var fields = [
    ['TEAM ID', teamId],
    ['TEAM NAME', teamName],
    ['COLLEGE', college],
    ['TEAM SIZE', teamSize + ' members'],
    ['TECH EVENT', techEvent],
    ['NON-TECH EVENT', nonTechEvent]
  ];
  var rowsHtml = '';
  for (var i = 0; i < fields.length; i++) {
    var bg = (i % 2 === 0) ? '#ffffff' : '#f6f5ff';
    rowsHtml += ''
      + '<tr style="background:' + bg + ';">'
      + '<td style="padding:13px 16px;color:#7c3aed;font-size:12px;font-weight:700;letter-spacing:1px;width:38%;border-bottom:1px solid #eef0f6;text-transform:uppercase;">' + fields[i][0] + '</td>'
      + '<td style="padding:13px 16px;color:#1e293b;font-size:15px;font-weight:600;border-bottom:1px solid #eef0f6;">' + fields[i][1] + '</td>'
      + '</tr>';
  }

  // Team members section.
  var membersHtml = '';
  if (members.length) {
    for (var k = 0; k < members.length; k++) {
      var mbg = (k % 2 === 0) ? '#ffffff' : '#f6f5ff';
      var contactHtml = members[k].contact ? members[k].contact : '';
      var memberFood = members[k].food || foodPref;
      var memberFoodColor = (memberFood.toLowerCase().indexOf('non') !== -1) ? '#ef4444' : '#22c55e';
      var foodIcon = '<span style="display:inline-block;width:14px;height:14px;border:2px solid ' + memberFoodColor + ';border-radius:3px;vertical-align:middle;text-align:center;line-height:10px;font-size:0;"><span style="display:inline-block;width:6px;height:6px;background:' + memberFoodColor + ';border-radius:50%;vertical-align:middle;"></span></span>';
      membersHtml += ''
        + '<tr style="background:' + mbg + ';">'
        + '<td style="padding:11px 16px;color:#7c3aed;font-size:12px;font-weight:700;letter-spacing:1px;width:38%;border-bottom:1px solid #eef0f6;text-transform:uppercase;">' + members[k].role + '</td>'
        + '<td style="padding:11px 16px;color:#1e293b;font-size:14px;font-weight:600;border-bottom:1px solid #eef0f6;"><table cellpadding="0" cellspacing="0" border="0" style="width:100%;"><tr><td style="padding:0;color:#1e293b;font-size:14px;font-weight:600;">' + members[k].name + (contactHtml ? ' &nbsp;&middot;&nbsp; ' + contactHtml : '') + '</td><td style="padding:0;text-align:right;white-space:nowrap;">' + foodIcon + '</td></tr></table></td>'
        + '</tr>';
    }
  }

  var htmlBody = ''
    + '<div style="background:#eef1f8;padding:26px 12px;font-family:Arial,Helvetica,sans-serif;">'
    + '<div style="max-width:560px;margin:0 auto;">'
    // Header banner with gradient + badge
    + '<div style="background:linear-gradient(135deg,#4f46e5 0%,#9333ea 55%,#db2777 100%);border-radius:18px;padding:34px 20px;text-align:center;">'
    + '<div style="font-size:32px;font-weight:800;color:#ffffff;letter-spacing:5px;">ZENOFEST</div>'
    + '<div style="font-size:17px;color:#dbeafe;letter-spacing:10px;margin-top:4px;">2026</div>'
    + '<div style="display:inline-block;margin-top:18px;background:rgba(255,255,255,0.16);border:1px solid rgba(255,255,255,0.4);border-radius:24px;padding:8px 22px;color:#ffffff;font-size:13px;font-weight:600;letter-spacing:2px;">&#10003; REGISTRATION CONFIRMED</div>'
    + '</div>'
    // Body card
    + '<div style="background:#ffffff;border-radius:16px;margin-top:-8px;padding:26px 24px;box-shadow:0 8px 24px rgba(79,70,229,0.10);">'
    + '<p style="margin:0 0 6px 0;color:#111827;font-size:19px;font-weight:700;">Hi ' + leaderName + ',</p>'
    + '<p style="margin:0;color:#6b7280;font-size:14px;line-height:1.7;">Your team registration for <b style="color:#4f46e5;">ZenoFest 2026</b> is officially confirmed. Here is your registration summary:</p>'
    + '<table style="width:100%;border-collapse:collapse;margin:20px 0 6px;">' + rowsHtml + '</table>'
    + (membersHtml ? '<p style="margin:18px 0 6px;color:#4c1d95;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Team Members</p><table style="width:100%;border-collapse:collapse;">' + membersHtml + '</table>' : '')
    + '<div style="margin-top:18px;background:#f6f5ff;border-left:4px solid #7c3aed;border-radius:8px;padding:12px 16px;color:#4c1d95;font-size:13px;line-height:1.6;">'
    + 'Your Team ID is <b>' + teamId + '</b>. Registration PDF is attached to this mail. Please keep it safe and show it at the fest if required.'
    + '</div>'
    + '</div>'
    // Footer
    + '<div style="text-align:center;padding:18px 0 6px;color:#94a3b8;font-size:12px;">'
    + 'Questions? Reply to this email &middot; ZenoFest 2026'
    + '</div>'
    + '</div>'
    + '</div>';

  try {
    var pdf = buildRegistrationPdf({
      teamId: teamId,
      teamName: teamName,
      college: college,
      leaderName: leaderName,
      teamSize: teamSize,
      techEvent: techEvent,
      nonTechEvent: nonTechEvent,
      foodPref: foodPref,
      members: members
    });
    GmailApp.sendEmail(toEmail, subject, '', {
      htmlBody: htmlBody,
      attachments: [pdf]
    });
    Logger.log('Confirmation email with PDF sent to ' + toEmail + ' (team ' + teamId + ')');
  } catch (err) {
    Logger.log('Error sending email to ' + toEmail + ': ' + err);
  }
}

function getFirstMatching(header, values, keyword) {
  for (var c = 0; c < header.length; c++) {
    if (String(header[c]).toLowerCase().indexOf(keyword) !== -1) {
      var v = String(values[c] || '').trim();
      if (v) return v;
    }
  }
  return '';
}

function buildRegistrationPdf(details) {
  var doc = DocumentApp.create('ZenoFest2026_Registration_Confirmation');
  var body = doc.getBody();
  body.setMarginTop(46).setMarginBottom(56).setMarginLeft(54).setMarginRight(54);

  // Header
  var title = body.appendParagraph('ZENOFEST 2026');
  title.setAttributes({
    BOLD: true,
    FONT_SIZE: 30,
    FOREGROUND_COLOR: '#4F46E5',
    FONT_FAMILY: 'Arial',
    HORIZONTAL_ALIGNMENT: DocumentApp.HorizontalAlignment.CENTER
  });

  var subtitle = body.appendParagraph('REGISTRATION CONFIRMATION');
  subtitle.setAttributes({
    FONT_SIZE: 12,
    FOREGROUND_COLOR: '#8B5CF6',
    FONT_FAMILY: 'Arial',
    HORIZONTAL_ALIGNMENT: DocumentApp.HorizontalAlignment.CENTER
  });

  var divider = body.appendParagraph('\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014');
  divider.setAttributes({ FOREGROUND_COLOR: '#C7B9FF', FONT_SIZE: 8 });
  divider.setAlignment(DocumentApp.HorizontalAlignment.CENTER);

  body.appendParagraph('Dear ' + details.leaderName + ',')
    .setAttributes({ FONT_SIZE: 11, FONT_FAMILY: 'Arial' });
  body.appendParagraph('Your registration for ZenoFest 2026 has been confirmed. Here is your summary:')
    .setAttributes({ FONT_SIZE: 10, FOREGROUND_COLOR: '#555555', FONT_FAMILY: 'Arial' });
  body.appendParagraph('');

  // Summary table
  var table = body.appendTable();
  var hr = table.appendTableRow();
  var hc1 = hr.appendTableCell('DETAIL');
  var hc2 = hr.appendTableCell('VALUE');
  hc1.setBackgroundColor('#4F46E5');
  hc2.setBackgroundColor('#4F46E5');
  hc1.getChild(0).asParagraph().setBold(true);
  hc2.getChild(0).asParagraph().setBold(true);

  var rows = [
    ['Team ID', details.teamId],
    ['Team Name', details.teamName],
    ['College', details.college],
    ['Team Size', details.teamSize + ' members'],
    ['Technical Event', details.techEvent],
    ['Non-Technical Event', details.nonTechEvent]
  ];
  for (var i = 0; i < rows.length; i++) {
    var tr = table.appendTableRow();
    var c1 = tr.appendTableCell(rows[i][0]);
    var c2 = tr.appendTableCell(rows[i][1]);
    var bg = (i % 2 === 0) ? '#F6F5FF' : '#FFFFFF';
    c1.setBackgroundColor(bg);
    c2.setBackgroundColor(bg);
    c1.getChild(0).asParagraph().setForegroundColor('#7C3AED').setBold(true);
    c1.getChild(0).asParagraph().setFontSize(10);
    c2.getChild(0).asParagraph().setFontSize(10.5);
  }

  if (details.members && details.members.length) {
    body.appendParagraph('');
    body.appendParagraph('TEAM MEMBERS')
      .setAttributes({ FONT_SIZE: 11, BOLD: true, FOREGROUND_COLOR: '#4F46E5', FONT_FAMILY: 'Arial' });

    var mtable = body.appendTable();
    var mhr = mtable.appendTableRow();
    var mHC1 = mhr.appendTableCell('ROLE');
    var mHC2 = mhr.appendTableCell('NAME');
    var mHC3 = mhr.appendTableCell('CONTACT');
    var mHC4 = mhr.appendTableCell('');
    mHC1.setBackgroundColor('#4F46E5');
    mHC2.setBackgroundColor('#4F46E5');
    mHC3.setBackgroundColor('#4F46E5');
    mHC4.setBackgroundColor('#4F46E5');
    mHC1.getChild(0).asParagraph().setForegroundColor('#FFFFFF').setBold(true).setFontSize(10);
    mHC2.getChild(0).asParagraph().setForegroundColor('#FFFFFF').setBold(true).setFontSize(10);
    mHC3.getChild(0).asParagraph().setForegroundColor('#FFFFFF').setBold(true).setFontSize(10);
    mHC4.getChild(0).asParagraph().setFontSize(1);

    var foodSymbol = '\u25CF';
    for (var mi = 0; mi < details.members.length; mi++) {
      var cm = details.members[mi];
      var mrow = mtable.appendTableRow();
      var mC1 = mrow.appendTableCell(cm.role || '');
      var mC2 = mrow.appendTableCell(cm.name || '');
      var mC3 = mrow.appendTableCell(cm.contact || '');
      var memberFood = cm.food || details.foodPref;
      var memberFoodColor = (memberFood.toLowerCase().indexOf('non') !== -1) ? '#EF4444' : '#22C55E';
      var mC4 = mrow.appendTableCell('');
      var mbg = (mi % 2 === 0) ? '#F6F5FF' : '#FFFFFF';
      mC1.setBackgroundColor(mbg);
      mC2.setBackgroundColor(mbg);
      mC3.setBackgroundColor(mbg);
      mC4.setBackgroundColor(mbg);
      mC1.getChild(0).asParagraph().setFontSize(10);
      mC2.getChild(0).asParagraph().setFontSize(10);
      mC3.getChild(0).asParagraph().setFontSize(10);
      var nestedTable = mC4.appendTable().setBorderColor(memberFoodColor);
      var nRow = nestedTable.appendTableRow();
      var nCell = nRow.appendTableCell(foodSymbol);
      nCell.getChild(0).asParagraph().setForegroundColor(memberFoodColor).setFontSize(10).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    }
  }

  body.appendParagraph('');
  body.appendParagraph('This is an official registration confirmation for ZenoFest 2026. Please carry this document (or a copy) when attending the fest.')
    .setAttributes({ FONT_SIZE: 8.5, FOREGROUND_COLOR: '#888888', FONT_FAMILY: 'Arial', ITALIC: true })
    .setAlignment(DocumentApp.HorizontalAlignment.CENTER);

  body.appendParagraph('');
  body.appendParagraph('Best regards,')
    .setAttributes({ FONT_SIZE: 10, FONT_FAMILY: 'Arial' });
  body.appendParagraph('ZenoFest 2026 Team')
    .setAttributes({ FONT_SIZE: 10, FONT_FAMILY: 'Arial' });

  doc.saveAndClose();
  var pdf = DriveApp.getFileById(doc.getId()).getAs('application/pdf');
  DriveApp.getFileById(doc.getId()).setTrashed(true);
  return pdf;
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
