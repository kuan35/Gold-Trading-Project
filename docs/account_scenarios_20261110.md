# 帳戶歸零情境與持倉／歷史成交報酬

`backend/account_scenarios.py` 是純函式計算，不讀憑證、不呼叫券商或模型，也不建立、確認或提交委託。

## 持倉欄位

`enrich_position_returns(snapshot, leverage='200', now=None)` 深複製快照後，對 `account.positions[]` 新增：

| 欄位 | 型別 | 定義 |
| --- | --- | --- |
| `price_return_pct` | 十進位字串或 null | BUY 用當前 Bid、SELL 用當前 Ask，相對實際 `entry` 的方向調整價格報酬率；不扣費用 |
| `estimated_margin_roi_pct` | 十進位字串或 null | 券商當前 `net_pnl` ÷（實際進場價 × `volume_units` ÷試算槓桿）×100 |
| `margin_roi_pct` | 十進位字串或 null | 主要顯示值，優先 `net_pnl ÷ used_margin ×100`；僅券商保證金缺值且USD估計有效時才退回估計值 |
| `actual_margin_roi_pct` | 十進位字串或 null | 嚴格限券商目前占用保證金分母的報酬，無券商分母時永遠 null |
| `return_currency` | 字串或 null | 損益／保證金的共同帳戶幣別，有效損益與幣別未知時不推定USD |
| `return_basis` | 字串 | 兩種公式、費用範圍及槓桿估計限制 |
| `return_reason` | 字串或 null | 任一報酬缺值時的原因；已知另一種報酬仍保留 |
| `margin_return_source` | `BROKER_POSITION`、`LEVERAGE_ESTIMATE` 或 `UNAVAILABLE` | 主要顯示值的分母來源 |

價格報酬需明確黃金商品、有效方向／實際進場價、CURRENT 且10秒內帳戶及5秒內報價。價格報酬不需要帳戶幣別或損益已知。主要持倉報酬使用券商目前占用保證金，同帳戶幣別可非USD，要求帳戶／PnL CURRENT且10秒內、有效淨損益、`used_margin_source='BROKER_POSITION'`及正占用保證金；不依賴過期報價、進場價、試算槓桿或估計數量。

目前占用保證金不等於最初投入，會隨持倉及券商保證金調整變動。明確占用為0、負數或無效值時主要報酬保持 null，不能以1:200估計覆蓋已知無效分母。僅當券商 `used_margin` 缺值，且USD、CURRENT且10秒內PnL、有效淨損益／實際進場價／數量／1至10000試算槓桿都成立時，主要欄才退回 `LEVERAGE_ESTIMATE`；舊 `estimated_margin_roi_pct` 仍獨立保留供相容與核對，不冒稱實際保證金報酬。`net_pnl=0` 合法；缺值不是0。兩種保證金報酬均使用券商已反映成本的淨損益，沒有再次虛構扣費。官方明載 `netUnrealizedPnL` 不含潛在平倉佣金，因此仍不是平倉後最終已實現報酬。[官方未實現損益欄位](https://help.ctrader.com/open-api/model-messages/#protooapositionunrealizedpnl)。

`decode_positions` 新增 `used_margin`（十進位字串或null）及 `used_margin_source`（`BROKER_POSITION`或`UNAVAILABLE`）。使用每筆 `ProtoOAPosition.usedMargin` 與該持倉自身的 `moneyDigits` 解碼，沒有精度就保留未知，不假設兩位。金額採帳戶入金幣別。[cTrader官方模型定義](https://github.com/spotware/openapi-proto-messages/blob/main/OpenApiModelMessages.proto)。

## 淨值歸零情境

`equity_zero_scenario(snapshot, draft, preview, now=None)` 只使用同份預覽的進場價 `entry_price`、數量 `quantity_oz`、方向與 `conditional_on_fill`。限價單是假設已成交後的情境，不是宣稱它將成交。

令當前 Bid 為 B、Ask−Bid 為 S、既有 BUY 盎司減 SELL 盎司為 Q、預覽新單盎司為 q。成交後參考 Bid P0：BUY 為進場價−S，SELL 為進場價。若帳戶當前淨值為 E：

```
E0 = E + Q × (P0 − B) − S × q
Q0 = Q +（BUY 為 q，SELL 為 −q）
zero_bid_price = P0 − E0 ÷ Q0
```

`E0` 包含既有部位移至假設成交價的淨值變化及新單立即承擔的固定買賣價差。既有部位當前淨損益已在 E，不重算或重扣。`E0<=0` 拒算後續門檻。

要求 USD、CURRENT 且10秒內帳戶及 PnL、正淨值、5秒內有效 Bid/Ask、完整持倉清單，且 `all_positions_count` 必須是整數並等於清單長度。每筆都需有效方向、數量、進場價與淨損益；任何未知持倉均整體拒算，不略過。既有適配器的 `ctrader_demo_xauusd`／`ctrader_live_xauusd` 來源是已篩選黃金的依據，通用快照需明確黃金商品名稱。任何顯式非黃金商品名稱都拒算。

所有金額／價格／數量均為十進位字串或 null；`status` 為 `AVAILABLE`、`UNAVAILABLE`、`NET_HEDGED` 或 `NO_POSITIVE_ZERO_PRICE`。`direction` 為 `UP`、`DOWN` 或 null。輸出另含 `reason`、`zero_bid_price`、`reference_bid_price`、`net_quantity_oz`、`equity_at_fill_usd`、`spread_usd`、`basis`、`source='FIXED_POSITION_LINEAR_SCENARIO'` 與布林值 `conditional_on_fill`。後兩種非 AVAILABLE 狀態仍可保留已知的參考價／數量／淨值，但沒有歸零價。

這是持倉與價差固定的線性情境，忽略其他掛單後續觸發、停損停利、強平、額外佣金／隔夜費、滑價及跳空。不能稱為精確爆倉價或券商強平價；券商可能在淨值歸零前先強平。[cTrader 官方交易條件](https://help.ctrader.com/trading-with-ctrader/conditions/)。

## 券商歷史成交欄位

`scripts/ctrader_account_payloads.py:decode_deal` 新增：

- `position_entry_price`: 有效 `closePositionDetail.entryPrice` 的十進位字串，未知為 null。
- `original_side`: 平倉 `tradeSide` 的反方向（BUY／SELL）；非平倉為 null。
- `price_return_pct`: 實際出場減實際入場、依原方向調整再除以入場價乘100的十進位字串。只有 FILLED／PARTIALLY_FILLED、正實際成交量與有效正進出價可用，否則 null。佣金／隔夜費仍分欄，不混為價格報酬。

歷史資料沒有當時真實占用保證金，不新增歷史保證金 ROI。[cTrader 官方 close position model](https://help.ctrader.com/open-api/model-messages/#protooaclosepositiondetail)。`decode_order` 額外新增 `stop_price` 字串或 null，保存券商 STOP／STOP_LIMIT 觸發價供取消核對。

測試使用合成快照與 Proto 替身，涵蓋多空／損益／佣金分離、部分成交、實際進場分母、既有持倉與限價假設成交時重估、對沖、無正價解、過期／未知幣別／非黃金／缺值與原資料不變。
