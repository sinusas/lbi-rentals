/**
 * Votes + comments backend for the LBI rentals page.
 * Paste this into Extensions → Apps Script of a Google Sheet, then
 * Deploy → New deployment → Web app (Execute as: Me, Who has access: Anyone).
 *
 * Creates two tabs on first use:
 *   votes:    timestamp | item | name
 *   comments: timestamp | item | name | text
 * Delete rows in the Sheet to remove a vote or comment.
 */

const MAX_NAME = 40;
const MAX_TEXT = 1000;
const MAX_ITEM = 40;

function sheet_(name, headers) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(headers);
    sh.setFrozenRows(1);
  }
  return sh;
}
const votes_ = () => sheet_("votes", ["timestamp", "item", "name"]);
const comments_ = () => sheet_("comments", ["timestamp", "item", "name", "text"]);

function rows_(sh) {
  const n = sh.getLastRow();
  return n < 2 ? [] : sh.getRange(2, 1, n - 1, sh.getLastColumn()).getValues();
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function list_() {
  return {
    ok: true,
    votes: rows_(votes_()).map(r => ({ item: String(r[1]), name: String(r[2]) })),
    comments: rows_(comments_()).map(r => ({ ts: new Date(r[0]).getTime(), item: String(r[1]), name: String(r[2]), text: String(r[3]) })),
  };
}

const clean_ = (s, max) => String(s == null ? "" : s).replace(/\s+/g, " ").trim().slice(0, max);
// Stop spreadsheet formula injection: values starting with = + - @ are stored as text
const safe_ = s => (/^[=+\-@]/.test(s) ? "'" + s : s);

function doGet() {
  return json_(list_());
}

function doPost(e) {
  let body;
  try { body = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false, error: "bad json" }); }
  const item = clean_(body.item, MAX_ITEM), name = clean_(body.name, MAX_NAME);
  if (!item || !name) return json_({ ok: false, error: "item and name required" });

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    if (body.action === "vote") {
      const sh = votes_(), rows = rows_(sh), key = name.toLowerCase();
      const idx = rows.findIndex(r => String(r[1]) === item && String(r[2]).toLowerCase() === key);
      if (body.on && idx < 0) sh.appendRow([new Date(), safe_(item), safe_(name)]);
      if (!body.on && idx >= 0) sh.deleteRow(idx + 2);
    } else if (body.action === "comment") {
      const text = String(body.text == null ? "" : body.text).trim().slice(0, MAX_TEXT);
      if (!text) return json_({ ok: false, error: "empty comment" });
      comments_().appendRow([new Date(), safe_(item), safe_(name), safe_(text)]);
    } else {
      return json_({ ok: false, error: "unknown action" });
    }
  } finally {
    lock.releaseLock();
  }
  return json_(list_());
}

/**
 * ONE-TIME SETUP: creates the "Suggest a house" Google Form and links its
 * responses to a new tab in this Sheet. In the Apps Script editor pick
 * createSuggestionForm in the function dropdown and click Run. The form's
 * share link is printed in the Execution log.
 */
function createSuggestionForm() {
  const form = FormApp.create("Suggest an LBI rental (Aug 7–14, 2027)");
  form.setDescription(
    "Found a house, or a set of houses within walking distance of each other, that we should consider? " +
    "Only the address is required; fill in whatever else you know. Kevin will add it to the map.");
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage("Thanks! It'll show up on the map once it's been checked.");

  form.addTextItem().setTitle("Your name").setRequired(false);
  form.addParagraphTextItem().setTitle("Address(es)")
    .setHelpText("One per line if you're suggesting a set of houses. Include the town (Beach Haven, Holgate, …).")
    .setRequired(true);
  form.addParagraphTextItem().setTitle("Listing link(s)")
    .setHelpText("VRBO, agency site, etc. One per line.").setRequired(false);
  form.addTextItem().setTitle("Bedrooms / sleeps").setHelpText("e.g. 5 bedrooms, sleeps 12").setRequired(false);
  form.addTextItem().setTitle("Weekly price").setHelpText("e.g. $15,000").setRequired(false);
  form.addMultipleChoiceItem().setTitle("Available Aug 7–14, 2027?")
    .setChoiceValues(["Yes, it shows as available", "No, it's booked", "Not sure"])
    .setRequired(false);
  form.addParagraphTextItem().setTitle("Notes").setHelpText("Pool, how close to the beach, anything else worth knowing.")
    .setRequired(false);

  form.setDestination(FormApp.DestinationType.SPREADSHEET, SpreadsheetApp.getActiveSpreadsheet().getId());
  const url = form.shortenFormUrl(form.getPublishedUrl());
  Logger.log("Share link: " + url);
  Logger.log("Edit link: " + form.getEditUrl());
  return url;
}
