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
// 「集計用」シート（承認済みデータ）から、拠点×カテゴリの実績表と
// エリア別ランキングを計算し、「集計表」シートに書き込む。
// このスクリプトを集計用スプレッドシートに開いてから
// 拡張機能＞Apps Scriptで開いた場合は、スプレッドシートのメニューバーに
// 「📊 キャンペーン集計」→「集計を更新」が追加される（onOpen）。
// メニューが出ない場合は、Apps Scriptエディタの関数選択で
// updateCampaignSummary を選んで手動実行するか、
// createCampaignSummaryTrigger を一度だけ実行して自動更新（1時間毎）を設定する。
// ==========================================

var CAMPAIGN_RAW_SHEET_NAME = "集計用";
var CAMPAIGN_SUMMARY_SHEET_NAME = "集計表";
var CAMPAIGN_BRANCHES = ["大阪中央店", "大阪北店", "神戸中央店", "京都中央店"];
var CAMPAIGN_CATEGORIES = ["きれいBOX", "セリング", "増加・切替", "ケアサービス"];

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
  if (!rawSheet) {
    SpreadsheetApp.getUi().alert("シート「" + CAMPAIGN_RAW_SHEET_NAME + "」が見つかりません。");
    return;
  }

  var data = rawSheet.getDataRange().getValues();
  var rows = data.slice(1); // 見出し行を除く

  var byBranchCategory = {};
  CAMPAIGN_BRANCHES.forEach(function (b) {
    byBranchCategory[b] = {};
    CAMPAIGN_CATEGORIES.forEach(function (c) {
      byBranchCategory[b][c] = { count: 0, amount: 0 };
    });
  });

  var byArea = {}; // area -> {staff:{name:true}, amount, byCategory:{...}}

  rows.forEach(function (row) {
    if (String(row[COL_STATUS]).trim() !== "承認済み") return;

    var branch = String(row[COL_BRANCH]).trim();
    var area = String(row[COL_AREA]).trim();
    var applicant = String(row[COL_APPLICANT]).trim();
    var category = String(row[COL_CATEGORY]).trim();
    var totals = computeCampaignRowTotals(row);

    if (byBranchCategory[branch] && byBranchCategory[branch][category]) {
      byBranchCategory[branch][category].count += totals.count;
      byBranchCategory[branch][category].amount += totals.amount;
    }

    if (area) {
      if (!byArea[area]) {
        byArea[area] = { staff: {}, amount: 0, byCategory: {} };
        CAMPAIGN_CATEGORIES.forEach(function (c) { byArea[area].byCategory[c] = 0; });
      }
      if (applicant) byArea[area].staff[applicant] = true;
      byArea[area].amount += totals.amount;
      if (byArea[area].byCategory[category] !== undefined) {
        byArea[area].byCategory[category] += totals.amount;
      }
    }
  });

  var summarySheet = ss.getSheetByName(CAMPAIGN_SUMMARY_SHEET_NAME);
  var isNewSheet = false;
  if (!summarySheet) {
    summarySheet = ss.insertSheet(CAMPAIGN_SUMMARY_SHEET_NAME);
    isNewSheet = true;
  }

  writeCampaignBranchTable_(summarySheet, byBranchCategory, isNewSheet);
  writeCampaignAreaRanking_(summarySheet, byArea);

  var ui;
  try { ui = SpreadsheetApp.getUi(); } catch (e) { ui = null; }
  if (ui) ui.alert("集計表を更新しました（" + new Date().toLocaleString() + "）");
}

// 拠点×カテゴリの実績表を書き込む。
// 目標金額（B,E,H,K列）は手入力を想定しているため、シートを新規作成した
// 最初の1回だけ0を書き込み、以後の実行では触らない（実績・達成率だけ更新する）。
function writeCampaignBranchTable_(sheet, byBranchCategory, isNewSheet) {
  sheet.getRange("A1").setValue("キャンペーン集計表（最終更新: " + new Date().toLocaleString() + "）");

  var branchStartCols = { "大阪中央店": 2, "大阪北店": 5, "神戸中央店": 8, "京都中央店": 11 };
  var zenkokuStartCol = 14;
  var firstCatRow = 5, lastCatRow = 8, totalRow = 9;

  if (isNewSheet) {
    CAMPAIGN_BRANCHES.forEach(function (b) {
      sheet.getRange(3, branchStartCols[b]).setValue(b);
    });
    sheet.getRange(3, zenkokuStartCol).setValue("全体");

    var subHeaders = ["目標金額", "実績金額", "達成率"];
    [2, 5, 8, 11, 14].forEach(function (col) {
      sheet.getRange(4, col, 1, 3).setValues([subHeaders]);
    });
    sheet.getRange("A4").setValue("カテゴリ");

    for (var r = 0; r < CAMPAIGN_CATEGORIES.length; r++) {
      sheet.getRange(firstCatRow + r, 1).setValue(CAMPAIGN_CATEGORIES[r]);
      [2, 5, 8, 11].forEach(function (col) {
        sheet.getRange(firstCatRow + r, col).setValue(0); // 目標金額の初期値（手入力で書き換える）
      });
    }
    sheet.getRange(totalRow, 1).setValue("合計");
    sheet.getRange(3, 1, 1, 15).setFontWeight("bold");
    sheet.getRange(4, 1, 1, 15).setFontWeight("bold");
  }

  CAMPAIGN_BRANCHES.forEach(function (b) {
    var startCol = branchStartCols[b];
    for (var i = 0; i < CAMPAIGN_CATEGORIES.length; i++) {
      var cat = CAMPAIGN_CATEGORIES[i];
      var rowNum = firstCatRow + i;
      var amount = byBranchCategory[b][cat].amount;
      var target = Number(sheet.getRange(rowNum, startCol).getValue()) || 0;
      sheet.getRange(rowNum, startCol + 1).setValue(amount);
      sheet.getRange(rowNum, startCol + 2).setValue(target ? (amount / target) : "");
    }
  });

  // 合計行（目標は各カテゴリ目標のSUM、実績・達成率も再計算）
  [2, 5, 8, 11].forEach(function (startCol) {
    var targetSum = 0, actualSum = 0;
    for (var r2 = firstCatRow; r2 <= lastCatRow; r2++) {
      targetSum += Number(sheet.getRange(r2, startCol).getValue()) || 0;
      actualSum += Number(sheet.getRange(r2, startCol + 1).getValue()) || 0;
    }
    sheet.getRange(totalRow, startCol).setValue(targetSum);
    sheet.getRange(totalRow, startCol + 1).setValue(actualSum);
    sheet.getRange(totalRow, startCol + 2).setValue(targetSum ? (actualSum / targetSum) : "");
  });

  // 全体列（拠点4つの合算）
  for (var r3 = firstCatRow; r3 <= totalRow; r3++) {
    var targetTotal = 0, actualTotal = 0;
    [2, 5, 8, 11].forEach(function (startCol) {
      targetTotal += Number(sheet.getRange(r3, startCol).getValue()) || 0;
      actualTotal += Number(sheet.getRange(r3, startCol + 1).getValue()) || 0;
    });
    sheet.getRange(r3, zenkokuStartCol).setValue(targetTotal);
    sheet.getRange(r3, zenkokuStartCol + 1).setValue(actualTotal);
    sheet.getRange(r3, zenkokuStartCol + 2).setValue(targetTotal ? (actualTotal / targetTotal) : "");
  }
}

// エリア別ランキングを書き込む（承認済み実績・1人あたり平均金額の降順）。
// こちらは目標のような手入力項目が無いため、毎回まるごと書き直す。
function writeCampaignAreaRanking_(sheet, byArea) {
  var titleRow = 12, headerRow = 13, firstDataRow = 14;
  sheet.getRange(titleRow, 1).setValue("エリア別ランキング（承認済み実績・1人あたり平均金額の降順）");
  sheet.getRange(titleRow, 1).setFontWeight("bold");

  var headers = ["エリア", "人数", "きれいBOX金額", "セリング金額", "増加金額", "ケア金額", "合計金額", "1人あたり平均", "順位"];
  sheet.getRange(headerRow, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(headerRow, 1, 1, headers.length).setFontWeight("bold");

  var areaList = Object.keys(byArea).map(function (area) {
    var info = byArea[area];
    var staffCount = Object.keys(info.staff).length;
    var avg = staffCount ? info.amount / staffCount : 0;
    return {
      area: area,
      staffCount: staffCount,
      kirei: info.byCategory["きれいBOX"] || 0,
      selling: info.byCategory["セリング"] || 0,
      increase: info.byCategory["増加・切替"] || 0,
      care: info.byCategory["ケアサービス"] || 0,
      total: info.amount,
      avg: avg
    };
  });

  areaList.sort(function (a, b) { return b.avg - a.avg; });

  // 既存の古いランキング行をクリアしてから書き直す（最大50エリア分の余裕）
  var clearRows = 50;
  sheet.getRange(firstDataRow, 1, clearRows, headers.length).clearContent();

  var output = areaList.map(function (a, idx) {
    return [a.area, a.staffCount, a.kirei, a.selling, a.increase, a.care, a.total, a.avg, idx + 1];
  });

  if (output.length > 0) {
    sheet.getRange(firstDataRow, 1, output.length, headers.length).setValues(output);
  }
}

// メニューが表示されない（スクリプトがスプレッドシートに紐付いていない）場合はこれを
// Apps Scriptエディタから一度だけ手動実行すると、1時間ごとに自動更新されるようになる。
function createCampaignSummaryTrigger() {
  ScriptApp.newTrigger("updateCampaignSummary")
    .timeBased()
    .everyHours(1)
    .create();
}
