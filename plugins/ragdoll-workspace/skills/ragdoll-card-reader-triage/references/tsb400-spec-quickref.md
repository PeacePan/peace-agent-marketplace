# 台新 400B ECR 規格速查

來源：《TSB 收銀機與刷卡機連線規格(400B)_標準公版 v1.32_20240705》。repo 內較舊的 v1.20 在
`OldEnglish/POSAgent/spec/`。以下是本 SOP 診斷會用到的部分，**欄位位置已用真實的 out.dat 與 ECR log 對照驗證過**；
有疑義時以原廠 PDF 為準（可用 `pdf` skill 轉文字後搜尋 `ECR_Response_Code`、`ECR_Error_Code`）。

## 通訊參數與流程

- 非同步、None parity、**115200**、8 bits、1 stop bit。
- 控制字元：STX `0x02`、ETX `0x03`、ACK `0x06`、NAK `0x15`、空白 `0x20`。
- 一個封包＝`<STX>` ＋ **400 bytes 資料** ＋ `<ETX>` ＋ `<LRC>`，共 **403 bytes**。
  LRC＝「資料與 ETX 的 XOR（STX 不含）」。log 裡看到 `[400]` 是資料、`[403]` 是整個封包。
- ACK 要回**兩次**（`0606`）。所以「ACK」＝連續兩個 `0x06`；單獨一個 `0x06` 可能只是雜訊。

```
POS(ECR.exe) ──<STX>[請求 400B]<ETX><LRC>──────────▶ 刷卡機
POS(ECR.exe) ◀──<ACK><ACK> (0606)───────────────────── 刷卡機   ← 刷卡機已收下請求
              （客人刷卡、授權；規格書標準等待 60 秒）
POS(ECR.exe) ◀──<STX>[結果 400B]<ETX><LRC>──────────── 刷卡機
POS(ECR.exe) ──<ACK><ACK>──▶ 刷卡機      → 寫出 out.dat，結束
```

- **電子簽名等多段流程（§1.3）**：刷卡機會送兩個結果框。第一框 `Transaction finished=N`、`Timer block reset=0250`
  （ECR 把逾時延長到 250 秒並先寫一次 out.dat），第二框才是最終結果 `Y`／`0000`。
  **同一個 ECR 區塊裡出現兩個 403 bytes 結果框、只差這幾個欄位，是正常的簽名交易，不是重送**。

## 檔案與 log 位置

| 項目 | 位置 | 備註 |
|---|---|---|
| ECR 工作目錄（走代理程式） | `C:\OMO\assets\ecr\` | POSAgentDotNet `Tsb.EcrFolder` 預設；**問題回報包的 `ecr/` 抓的就是這裡** |
| ECR 工作目錄（Ragdoll 直連） | `resources/tsb/ecr` | 與上面不同；回報包不收這個 |
| `ECR.exe` | 工作目錄 | 台新提供；版本見 ECR log 檔頭 `CS_ECR 20190925` |
| `CS_ecr.dat` | 工作目錄 | **ECR 的設定檔**：COM 埠、速率、Time Out、ACKWaitSecond…。**每次交易都會被改寫，修改時間不能拿來判斷設定有沒有變** |
| `config.ini`（回報包根目錄） | Ragdoll 的設定 | 內含 `TSB_COM`、`TSB_BAUDRATE=9600`…是 Ragdoll 直連與開機探測用，**不是 ECR 的設定** |
| `CS_ErrorCode.dat` | 工作目錄 | **細項碼**（ECR_Error_Code）表，不是回應碼表 |
| `log/NNN_YYYYMMDD.log` | 工作目錄 | ECR.exe 自己的 log，Big5＋hex |
| `transmitted/YYYYMM/YYYYMMDD/HHMMSS_in.dat`、`_out.dat` | 工作目錄 | 歸檔，各 400 bytes；成功的 out.dat 含（中段遮罩的）卡號，不要輸出 |
| 代理程式 log | `C:\ProgramData\POSAgentDotNet\logs` | `posagentdotnet-*.log`、`printer-serialdata-*.log`（發票機 COM3） |

### ECR log 區塊的關鍵行

```
<時間> ============START===========
<時間> Send AllData    [403]: <hex>        ← 送給刷卡機的請求
<時間> Send Message    [400]: 11  …000000012300…   ← 請求的文字內容（交易別、金額）
<時間> 2 seconds Timeout! / Send request again!    ← 2 秒沒收到 ACK 就重送一次
<時間> Receive Data    [008]: <hex>        ← 逐段收到的原始位元組（損壞時看這裡）
<時間> Receive AllData [403]: <hex>        ← ECR 組好的完整封包
<時間> Send Message    [002]: <Nak><Nak>   ← ECR 收到損壞的結果，要求刷卡機重送（正常幾乎為 0；發病後才出現是佐證）
<時間> 已產生out.dat檔案
<時間> 中介程式執行錯誤 [16]: 超過傳送的錯誤次數      ← ECR.exe 自己記錄的錯誤
<時間> ============END=============
```

| ECR 錯誤 | 意思 | 對應 out.dat（以時間對齊推得，非文件定義） |
|---|---|---|
| `[16]` 超過傳送的錯誤次數 | 送出後沒收到 ACK（重送一次仍沒有） | 空白＋`0001` |
| `[17]` 超過接收的錯誤次數 | 收到資料但損壞／不完整 | 空白＋`0001` |
| `[14]` 等待逾時 | 等結果逾時（本機設定約 30 秒） | 空白＋`0003` |
| 其他（如 `[10]`） | 原文照錄 | 視情況 |

`ErrRec Message [NN]: …` 那一行的 `[NN]` 是「損壞資料的長度」，**不是錯誤碼**。

## 資料欄位位置（回應與請求共用；0-based 切片＝資料 400 bytes，不含 STX／ETX／LRC）

| 欄位 | 規格書位置（1-based） | 0-based 切片 | 說明 |
|---|---|---|---|
| Trans_Type 交易別 | 1–2 | `[0:2]` | `11` 一般交易；`12` 取消等 |
| Host_ID 銀行別 | 3–4 | `[2:4]` | |
| Receipt_No 端末機簽單序號（**調閱編號**） | 5–10 | `[4:10]` | 與本機 `offline_sale_lines_payments.receipt_no` 相同，可對帳 |
| Card_No 卡號 | 11–29 | `[10:29]` | 中段已遮罩；**不要輸出** |
| ECR_Error_Code 細項錯誤碼 | 30–33 | `[29:33]` | 回應碼為 `0001` 時才有具體原因；**空白＝不是刷卡機回報的具體錯誤** |
| Trans_Amount 金額 | 34–45 | `[33:45]` | 兩位小數，`000000001500`＝15 元 |
| Trans_Date／Trans_Time | 46–51／52–57 | `[45:51]`／`[51:57]` | yyMMdd／hhmmss |
| Approval_No 授權碼 | 58–66 | `[57:66]` | |
| **ECR_Response_Code 通訊回應碼** | **79–82** | **`[78:82]`** | `0000` 核准；見下表 |
| EDC_Terminal_ID 端末機代號 | 83–90 | `[82:90]` | 成功時緊接在回應碼後，如 `0000`＋`64605875` |
| Store_Id／RRN | 115–132 | `[114:132]` | 請求端放機台＋時間戳 |
| Card_type 卡別 | 135–136 | `[134:136]` | |
| Entry Mode 過卡方式 | 139 | `[138]` | M 人工、C 晶片、S 磁條、W 感應… |
| Batch_No 批次號 | 145–152 | `[144:152]` | |
| Transaction finished | 260 | `[259]` | `Y` 結束／`N` 還有下一段 |
| Timer block reset | 261–264（實測） | `[260:264]` | 多段流程的延長逾時值，如 `0250` |

若是從含 STX 的 403 bytes 封包切，位置要再 +1。

## ECR_Response_Code 通訊回應碼（規格書 §2.10-G）

| 碼 | 意思 |
|---|---|
| `0000` | Approved |
| `0001` | **Error**（細項看位置 30–33） |
| `0002` | Call Bank |
| `0003` | **Timeout** |
| `0004` | Fall Back（晶片讀卡錯誤，請改刷） |
| `0006` | Authorization Failed |
| `0007` | Amount Error |
| `0008` | CONTACTLESS Error（感應設備異常） |
| `0051`／`0052`／`0053` | 無檢核用聯名卡 Card Bin／非聯名卡／查無交易記錄 |

Ragdoll 直連路徑的 `tsb-ecr.ts` 內建對照表與規格書**不一致**（例如把 `0003` 顯示成「卡片過期」）；
判讀時以本表為準，不要照 Ragdoll 畫面上的文字推論。

## ECR_Error_Code 細項碼（規格書 §2.10-J；只在回應碼 `0001` 且位置 30–33 非空白時才有）

| 前兩碼 | 類別 | 例 |
|---|---|---|
| `01XX` | 使用者操作／卡片異常 | `0101` 不支援此卡、`0102`～`0104` 讀卡錯誤、`0105` 卡片過期、`0106` 檢查碼錯誤、`0107` 卡號錯誤、`0108` 請用銀聯選單、`0112` 請先全部結帳、`0113` 請先結帳 |
| `02XX` | **主機授權失敗**；`02`＋銀行回應碼 2 碼 | `0251`＝銀行回應 51（餘額不足）、`0205`＝05（不予承兌） |
| `03XX` | 使用者操作逾時 | `0301` 等待過卡逾時、`0309` 持卡人輸入密碼逾時 |
| `04XX` | 使用者按取消中止交易 | |
| `05XX` | 信用卡授權通訊異常 | |
| `06XX` | ECR 電文通訊的所有異常 | |
| `07XX` | 外接設備異常 | |

**判讀要點**：有細項碼的 `0001`＝刷卡機自己回報的具體原因（客戶端、銀行端、操作），**不是線路問題**；
整份空白只剩 `0001`／`0003`、細項碼為空＝中介程式沒收到完整回覆時寫的固定範本，才是通訊層。

## 卡別碼

`01` CUP、`03` JCB、`04` Visa、`05` Mastercard、`06` AE、`07` Discover／Diners、`08` U Card、`09` SmartPay、
`10` 悠遊卡、`11` iPass。
