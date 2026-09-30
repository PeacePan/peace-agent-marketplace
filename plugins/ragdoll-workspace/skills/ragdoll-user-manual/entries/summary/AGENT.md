# 結帳摘要／付款確認（`/summary`）Agent 指引

> 依據 `origin/release/ragdoll` @ `5f4ad0f579`（2026-09-29 合併 PR #25983 之後）的原始碼撰寫，
> 並於 2026-09-30 在 Ragdoll dev 視窗（v1.2.0，門市「長安總部測試」機台 00301，程式碼與上述
> commit 逐檔比對一致）做過 runtime 驗證。
>
> **已 runtime 驗證**：付款頁佈局、購買明細與折扣區、現金鍵盤（含 Esc／送出 0／足額後改金額）、
> 信用卡鍵盤預設值（未送出）、信用卡（離線）、PandaGo、外送付款方式面板（一般通路全停用）、
> One 碼／宜睿票券對話框開啟與關閉、標記外送單必填檢查、發票方式載具輸入與漏印攔截、
> 「請先選擇付款方式並完成付款」攔截、現金完成結帳（含進度彈窗與完成畫面）、返回按鈕。
>
> **僅依原始碼（⚠️ 未驗證）**：刷卡機實際刷卡與遮罩、One 碼實際付款與延遲回應、宜睿票券查詢與
> 核銷、消費券（本店未開放顯示）、外送平台訂單編號對話框、標記外送單的其餘欄位檢查、
> 各種失敗／逾時分支、離線提示、二顯同步畫面。這些需要實體設備、外部服務或特殊門市設定。

## 入口資訊

- 網址：`/summary`；畫面上的子標題是「付款確認」（頁首品牌列仍是「寵物公園」）。
- 主元件：`next/app/summary/page.tsx`（`SummaryPage`）；付款元件在
  `next/app/summary/components/`，**美容付款頁 `/salon-summary` 重用其中大部分元件**
  （見 `entries/salon-summary/AGENT.md`）。
- 唯一正常進入方式：`/checkout`（商品模式）點「小計」→ 促銷結算對話框 →「確認結帳」
  （`promotion-summary-confirm-btn`）→ 通過一連串守門後導頁。守門清單見
  `references/01-enter-and-review.md`。
- 首頁的「訂單查詢」按鈕也連到 `/summary`，但購物車為空會立刻被導回 `/checkout`，
  並不是訂單查詢頁（見 `entries/home/AGENT.md`）。
- 空車守門：進入後若購物車品項數為 0 且不在結帳流程中，會 `router.replace('/checkout')`。
  重新整理付款頁（購物車 store 不持久化）也會因此被導回結帳頁。
- 進入時會自動關閉前一頁殘留的 toast，付款頁是乾淨畫面。
- 頁首的銷售員區塊沒有「登出」按鈕（`SalerLogin disableLogout`），付款流程中不能登出。

---

## 介面佈局

| 區域 | 內容 |
|------|------|
| 頁首品牌列 | 「寵物公園」logo、連線狀態指示、銷售員資訊（無登出） |
| 資訊列 | 門市、機台、銷售人員、通路（`data-testid="checkout-channel"`）、帳務日、銷售時間、資料同步時間；**付款頁不顯示「立即同步」按鈕**（要同步請回結帳頁） |
| 子標題列 | 返回箭頭（`summary-back-btn`）+「付款確認」 |
| 左上：購買明細 | 依序：一般商品（含促銷標籤）、加購商品、贈品、點＋金商品；換購時多一列「原訂單金額 – 單號」；最下方「折扣明細」（整單折扣／折扣碼／點數折抵／會員優惠券） |
| 左中：折扣與應付 | 商品小計、商品促銷、優惠券、點數折抵、折扣碼、整單折扣、（換購）原訂單抵扣／換購找零／換購差額、**應付金額**、「共 N 件商品」 |
| 左下：付款方式 | 4 欄格線的付款按鈕（見下表） |
| 右側上半 | 「標記外送單」按鈕、「發票方式」卡、「發票明細列印」開關、（離線時）離線提示 |
| 右側固定底部 | 付款摘要清單（已選付款方式、找零、尚欠…）+ 「完成結帳」按鈕（`checkout-btn`） |

離線時（`isOnline` 為假）右側會出現黃色提示「⚠️ 目前為離線模式，結帳後發票將於連線後補印」。

---

## 付款按鈕一覽（左下，4 欄格線，由左至右、由上而下）

| 按鈕 | data-testid | 性質 | 說明索引 |
|------|-------------|------|---------|
| 現金 | `cash-payment-btn` | 主付款 | `references/02-cash-and-credit-card.md` |
| One 碼 | `taishin-pay-btn` | 主付款（全額） | `references/03-other-payment-methods.md` |
| 信用卡 | `credit-card-payment-btn` | 全額＝主付款；指定金額＝副付款 | `references/02-cash-and-credit-card.md` |
| 信用卡(離線) | `credit-card-offline-btn` | 副付款 | `references/02-cash-and-credit-card.md` |
| 消費券(不找零) | `stimulus-voucher-btn` | 副付款；**僅特定門市顯示**，否則該格留空（`stimulus-voucher-slot-placeholder`） | `references/03-other-payment-methods.md` |
| 宜睿票券 | `edenred-voucher-btn` | 副折抵 | `references/03-other-payment-methods.md` |
| PandaGo | `pandago-btn` | 主付款（全額） | `references/03-other-payment-methods.md` |
| 外送付款方式 | `delivery-payment-trigger` | 主付款（全額），展開 4 個平台 | `references/03-other-payment-methods.md` |

「主付款」同時只能有一筆，後選的會取代先選的；「副付款／副折抵」可與主付款並存。
付款方式之間的互斥規則與對應提示文字見 `references/04-payment-summary-and-restrictions.md`。

---

## 業務流程索引

| 流程 | 參考檔案 |
|------|---------|
| 進入付款頁（守門條件）與畫面核對 | `references/01-enter-and-review.md` |
| 現金、信用卡（全額／指定）、信用卡（離線） | `references/02-cash-and-credit-card.md` |
| One 碼、宜睿票券、消費券、PandaGo、外送付款 | `references/03-other-payment-methods.md` |
| 付款摘要清單、可否移除、互斥規則與提示文字 | `references/04-payment-summary-and-restrictions.md` |
| 發票方式、明細列印、標記外送單、完成結帳、返回 | `references/05-invoice-delivery-mark-and-complete.md` |

---

## 與 `ragdoll-project-knowledge` 的分工

本文件只記錄操作路徑與畫面。付款資料層（主付款／副付款三層結構）、規則表設計、
完成結帳呼叫鏈的權威來源是同專案的 `ragdoll-project-knowledge` skill
（`Ragdoll/.claude/skills/ragdoll-project-knowledge/references/modules/payment.md`、
`modules/edenred-voucher.md`、`modules/taishin-one-pay.md`、`modules/invoice.md`），
本文件不重複維護規則細節。

---

## 重要限制（依原始碼確認）

- 付款頁沒有「取消交易」按鈕，離開的唯一途徑是左上「返回」，且在下列情況會被鎖住：
  台新 One 碼已付款成功、已有任何宜睿票券核銷（或核銷／查詢進行中）、信用卡（全額）已刷成功。
- 購物車、會員、外送標記在「返回」時都會保留；只會重置付款層並回滾會員優惠券、歸還已預扣的點數折抵。
- 信用卡（真實刷卡）一筆銷售只能刷一次（全額或指定金額擇一）；信用卡（離線）另限一筆。
- One 碼、宜睿票券、消費券彼此互斥或限制搭配（見 `references/04-…`）。
- 「完成結帳」點下後除「建立銷售紀錄」外的步驟失敗都不會中斷交易，只標記錯誤；
  **建立銷售紀錄失敗才代表交易未成立**。
- 結帳完成後（清除購物車步驟）**銷售員會被登出**：按「返回購物車」回到 `/checkout` 時，頁首
  銷售員欄回到「輸入員編／登入」，並自動彈出員編鍵盤，鍵盤下方多一顆「繼續使用 {姓名}」快捷鈕
  （runtime 已驗證）。下一筆銷售需重新登入或按此快捷鈕。
- 現金已足額（含找零）時，要改成另一個非 0 的金額會被「已付清款項」擋下；須先送出 0 清除
  （或按摘要列 ×）再重新輸入（runtime 已驗證）。
- 多則 toast 同時存在時，畫面左下會多一顆「全部關閉（N）」；提示不會自動消失時可用它一次清掉。

## 待確認事項（依原始碼推得，尚未實機驗證，驗收時請特別留意）

1. **信用卡（指定金額）已刷成功後，「返回」按鈕似乎仍可按**：返回鎖定條件只檢查
   「信用卡（全額）成功」，未檢查指定金額（`partialCreditPayment`）；按返回會重置付款層，
   已扣的指定信用卡紀錄就從畫面與付款資料消失。美容付款頁有針對此情況鎖返回，商品頁沒有。
2. **信用卡刷卡失敗後按「重試」一律以「未付金額全額」重刷**，不會沿用原本輸入的指定金額。
   若原本刷的是指定金額，失敗後想重刷同一金額應按「取消」再重新點「信用卡」輸入。
