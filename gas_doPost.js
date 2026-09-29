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
