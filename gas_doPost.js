/**
 * gidを正しく解決してシートを取得するヘルパー
 * ※ SpreadsheetApp.openByUrl() はURLの #gid=... / ?gid=... を無視するため、
 *    そのまま getSheets()[0] を使うと「一番左のシート」しか取れない。
 *    kensaku（メンテナンス依頼アプリ）のgas_doPost.jsと同じ実装。
 */
function getSheetFromUrl(url) {
  var ss = SpreadsheetApp.openByUrl(url);
  var gidMatch = url.match(/[?&#]gid=(\d+)/);
  if (gidMatch) {
    var gid = Number(gidMatch[1]);
    var sheets = ss.getSheets();
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === gid) {
        return sheets[i];
      }
    }
  }
  // gid指定が無い、または一致するシートが見つからない場合は先頭シートにフォールバック
  return ss.getSheets()[0];
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var action = data.action;

    // ==========================================
    // キャンペーン実績入力（1行追加のみ）
    // 対象: views/campaign_view.py の CAMPAIGN_SHEET_URL
    // ==========================================
    if (action === "SUBMIT_CAMPAIGN_ENTRY") {
      var targetUrl = data.target_sheet_url;
      var sheet = getSheetFromUrl(targetUrl);
      sheet.appendRow(data.full_row);
      return ContentService.createTextOutput(JSON.stringify({"status": "success"}))
        .setMimeType(ContentService.MimeType.JSON);

    // ==========================================
    // 管理職チェック（承認／差戻し）：該当行を丸ごと updated_row で上書きする
    // ==========================================
    } else if (action === "UPDATE_CAMPAIGN_STATUS") {
      var targetUrl = data.target_sheet_url;
      var sheet = getSheetFromUrl(targetUrl);
      var rowIndex = data.row_index;
      var updatedRow = data.updated_row;
      var range = sheet.getRange(rowIndex, 1, 1, updatedRow.length);
      range.setValues([updatedRow]);
      return ContentService.createTextOutput(JSON.stringify({"status": "success"}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": "未定義のアクション: " + action}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ==========================================
// キャンペーン集計表の自動更新
// 「集計用」シート（承認済みデータ）を担当者名ごとに集計し、
// 「集計表」シートに手作業で用意された担当者一覧表（A列:担当者名,
// B列:拠点, C列:エリア, D:きれいBOX販売数, E:きれいBOX金額,
// F:セリング金額, G:増加金額, H:ケア金額）のC〜H列を埋める。
// A列（担当者名）・B列（拠点）・見出し行はそのまま、C〜H列だけを
// 名前で突き合わせて上書きする。
// このスクリプトを集計用スプレッドシートに開いてから
// 拡張機能＞Apps Scriptで開いた場合は、スプレッドシートのメニューバーに
// 「📊 キャンペーン集計」→「集計を更新」が追加される（onOpen）。
// メニューが出ない場合は、Apps Scriptエディタの関数選択で
// updateCampaignSummary を選んで手動実行するか、
// createCampaignSummaryTrigger を一度だけ実行して自動更新（1時間毎）を設定する。
// ==========================================

var CAMPAIGN_RAW_SHEET_NAME = "集計用";
var CAMPAIGN_SUMMARY_SHEET_NAME = "集計表";
var CAMPAIGN_CATEGORIES = ["きれいBOX", "セリング", "増加・切替", "ケアサービス"];

// 集計表シート側（担当者一覧表）のレイアウト
var PERSON_TABLE_FIRST_ROW = 3;    // 1〜2行目が見出し、3行目から担当者データ
var PERSON_TABLE_COL_NAME = 1;     // A: 担当者名
var PERSON_TABLE_COL_AREA = 3;     // C: エリア（あとで手入力するため書き込まない）
var PERSON_TABLE_COL_KB_SALES = 4; // D: きれいBOX販売数（D〜Hの5列分を書き込む）

// 集計用シートの列（0始まり、views/campaign_view.py の full_row と対応させること）
var COL_BRANCH = 2;
var COL_AREA = 3;
var COL_APPLICANT = 1;
var COL_CATEGORY = 8;
var COL_KB_SALES = 9, COL_KB_PRICE = 10;
var COL_SELLING_START = 11;   // 5件 x (記号,販売数,単価)
var COL_INCREASE_START = 26;  // 5件 x (記号,サイクル,単価,数量)
var COL_CARE_AMOUNT = 55;
var COL_STATUS = 56;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("📊 キャンペーン集計")
    .addItem("集計を更新", "updateCampaignSummary")
    .addToUi();
}

// この申請1件分の「個数」「金額」を計算する（アプリ入力画面の計算式と同じ）
// 💡 切替には金額の計算式が無いため、増加・切替カテゴリの個数・金額は
//    増加分のみが対象（切替は集計に含まれない）。
function computeCampaignRowTotals(row) {
  var category = row[COL_CATEGORY];
  var count = 0, amount = 0;

  if (category === "きれいBOX") {
    var sales = Number(row[COL_KB_SALES]) || 0;
    var price = Number(row[COL_KB_PRICE]) || 0;
    count = sales;
    amount = sales * price;

  } else if (category === "セリング") {
    for (var i = 0; i < 5; i++) {
      var base = COL_SELLING_START + i * 3;
      var s = Number(row[base + 1]) || 0;
      var p = Number(row[base + 2]) || 0;
      count += s;
      amount += s * p;
    }

  } else if (category === "増加・切替") {
    for (var j = 0; j < 5; j++) {
      var b = COL_INCREASE_START + j * 4;
      var cycle = Number(row[b + 1]) || 0;
      var pr = Number(row[b + 2]) || 0;
      var qty = Number(row[b + 3]) || 0;
      count += qty;
      if (cycle) {
        amount += pr * (4 / cycle) * qty;
      }
    }

  } else if (category === "ケアサービス") {
    amount = Number(row[COL_CARE_AMOUNT]) || 0;
  }

  return { count: count, amount: amount };
}

function updateCampaignSummary() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var rawSheet = ss.getSheetByName(CAMPAIGN_RAW_SHEET_NAME);
  var summarySheet = ss.getSheetByName(CAMPAIGN_SUMMARY_SHEET_NAME);
  var ui;
  try { ui = SpreadsheetApp.getUi(); } catch (e) { ui = null; }

  if (!rawSheet || !summarySheet) {
    var msg = "シートが見つかりません（" + CAMPAIGN_RAW_SHEET_NAME + " / " + CAMPAIGN_SUMMARY_SHEET_NAME + "）。";
    if (ui) ui.alert(msg);
    return;
  }

  var data = rawSheet.getDataRange().getValues();
  var rows = data.slice(1); // 見出し行を除く

  // 担当者名（申請者）ごとに承認済みデータ（＝ステータスが「承認済み」の行）だけを集計する。
  // 「申請中」「破棄」は対象外（この時点で除外しているので、集計表・ランキング表どちらにも含まれない）。
  var byPerson = {}; // name -> {area, branch, kbSales, kbAmount, sellingCount, sellingAmount, increaseCount, increaseAmount, care}

  rows.forEach(function (row) {
    if (String(row[COL_STATUS]).trim() !== "承認済み") return;

    var name = String(row[COL_APPLICANT]).trim();
    if (!name) return;
    var branch = String(row[COL_BRANCH]).trim();
    var area = String(row[COL_AREA]).trim();
    var category = String(row[COL_CATEGORY]).trim();
    var totals = computeCampaignRowTotals(row);

    if (!byPerson[name]) {
      byPerson[name] = {
        area: "", branch: "", kbSales: 0, kbAmount: 0,
        sellingCount: 0, sellingAmount: 0, increaseCount: 0, increaseAmount: 0, care: 0,
      };
    }
    if (area) byPerson[name].area = area; // 最後に見つかったエリアを採用
    if (branch) byPerson[name].branch = branch; // 最後に見つかった拠点を採用

    if (category === "きれいBOX") {
      byPerson[name].kbSales += totals.count;
      byPerson[name].kbAmount += totals.amount;
    } else if (category === "セリング") {
      byPerson[name].sellingCount += totals.count;
      byPerson[name].sellingAmount += totals.amount;
    } else if (category === "増加・切替") {
      byPerson[name].increaseCount += totals.count;
      byPerson[name].increaseAmount += totals.amount;
    } else if (category === "ケアサービス") {
      byPerson[name].care += totals.amount;
    }
  });

  writeCampaignPersonTable_(summarySheet, byPerson);

  var rankingSheet = ss.getSheetByName(CAMPAIGN_RANKING_SHEET_NAME);
  if (rankingSheet) {
    writeCampaignRankingTable_(summarySheet, rankingSheet, byPerson);
  }

  if (ui) ui.alert("集計表を更新しました（" + new Date().toLocaleString() + "）");
}

// 集計表シートに手作業で用意された担当者一覧（A列:担当者名, B列:拠点）に沿って、
// D列（きれいBOX販売数）〜H列（ケア金額）を担当者名で突き合わせて書き込む。
// A列・B列・C列（エリア。あとで手入力するため触らない）・見出し行には一切触れない。
// 集計用シートに該当データが無い担当者は各カテゴリとも空欄にする
// （0円は表示しない、他画面の金額表示と同じ扱い）。
function writeCampaignPersonTable_(sheet, byPerson) {
  var lastRow = sheet.getLastRow();
  if (lastRow < PERSON_TABLE_FIRST_ROW) return; // 担当者データがまだ無い

  var numRows = lastRow - PERSON_TABLE_FIRST_ROW + 1;
  var names = sheet.getRange(PERSON_TABLE_FIRST_ROW, PERSON_TABLE_COL_NAME, numRows, 1).getValues();

  var output = names.map(function (r) {
    var name = String(r[0]).trim();
    if (!name) return ["", "", "", "", ""];
    var p = byPerson[name];
    if (!p) return ["", "", "", "", ""];
    return [
      p.kbSales || "",
      p.kbAmount || "",
      p.sellingAmount || "",
      p.increaseAmount || "",
      p.care || "",
    ];
  });

  sheet.getRange(PERSON_TABLE_FIRST_ROW, PERSON_TABLE_COL_KB_SALES, output.length, 5).setValues(output);
}

// ==========================================
// ランキング表シートの自動更新
// 「集計表」シートの担当者一覧（A列:担当者名, B列:拠点）と同じ並び順の担当者を対象に、
// きれいBOX・セリングは金額の降順、増加は数量の降順で順位を付け、「ランキング表」シートに
// 書き込む（同率は同じ順位にし、次の順位は同率の人数分スキップする＝スプレッドシートの
// RANK関数と同じ方式）。1〜3行目（タイトル・カテゴリ見出し・列見出し）は手作業で用意されて
// いるため触らず、4行目からのデータ部分だけを書き込む。
// 対象データは updateCampaignSummary() 側で既に「承認済み」だけに絞り込まれた byPerson を
// そのまま使うため、「申請中」「破棄」はここでも集計に含まれない。
// ==========================================
var CAMPAIGN_RANKING_SHEET_NAME = "ランキング表";
var RANKING_FIRST_DATA_ROW = 4;
var RANKING_BLOCK_KB_START_COL = 1;   // A列（きれいBOX：順位/担当者名/拠点/販売数/金額）
var RANKING_BLOCK_SL_START_COL = 7;   // G列（セリング：順位/担当者名/拠点/販売数/金額）
var RANKING_BLOCK_IC_START_COL = 13;  // M列（増加：順位/担当者名/拠点/数量）

function writeCampaignRankingTable_(summarySheet, rankingSheet, byPerson) {
  var lastRow = summarySheet.getLastRow();
  if (lastRow < PERSON_TABLE_FIRST_ROW) return;

  var numRows = lastRow - PERSON_TABLE_FIRST_ROW + 1;
  var roster = summarySheet.getRange(PERSON_TABLE_FIRST_ROW, PERSON_TABLE_COL_NAME, numRows, 2).getValues(); // A:担当者名, B:拠点

  var kbRows = [], slRows = [], icRows = [];
  roster.forEach(function (r) {
    var name = String(r[0]).trim();
    if (!name) return;
    var branch = String(r[1]).trim();
    var p = byPerson[name] || {};
    kbRows.push({ name: name, branch: branch, count: p.kbSales || 0, amount: p.kbAmount || 0 });
    slRows.push({ name: name, branch: branch, count: p.sellingCount || 0, amount: p.sellingAmount || 0 });
    icRows.push({ name: name, branch: branch, count: p.increaseCount || 0, amount: p.increaseAmount || 0 });
  });

  writeRankingBlock_(rankingSheet, RANKING_BLOCK_KB_START_COL, kbRows, true);
  writeRankingBlock_(rankingSheet, RANKING_BLOCK_SL_START_COL, slRows, true);
  writeRankingBlock_(rankingSheet, RANKING_BLOCK_IC_START_COL, icRows, false);
}

// withAmount: true＝金額の降順で順位付け（金額列も出力）、false＝数量の降順で順位付け（数量列のみ出力）
function writeRankingBlock_(sheet, startCol, rows, withAmount) {
  var sortKey = withAmount ? "amount" : "count";
  var sorted = rows.slice().sort(function (a, b) { return b[sortKey] - a[sortKey]; });

  var output = [];
  var lastRank = 0, lastValue = null;
  for (var i = 0; i < sorted.length; i++) {
    var r = sorted[i];
    var rank = (lastValue !== null && r[sortKey] === lastValue) ? lastRank : i + 1;
    lastRank = rank;
    lastValue = r[sortKey];
    output.push(withAmount
      ? [rank, r.name, r.branch, r.count, r.amount]
      : [rank, r.name, r.branch, r.count]);
  }

  if (output.length === 0) return;
  var numCols = withAmount ? 5 : 4;
  sheet.getRange(RANKING_FIRST_DATA_ROW, startCol, output.length, numCols).setValues(output);
}

// メニューが表示されない（スクリプトがスプレッドシートに紐付いていない）場合はこれを
// Apps Scriptエディタから一度だけ手動実行すると、1時間ごとに自動更新されるようになる。
function createCampaignSummaryTrigger() {
  ScriptApp.newTrigger("updateCampaignSummary")
    .timeBased()
    .everyHours(1)
    .create();
}
