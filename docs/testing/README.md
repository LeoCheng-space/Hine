<a id="testing"></a>
# 測試文件

單元、整合、端對端、負載、安全、迴歸與驗收測試文件。
課程負載基線與協定／真實瀏覽器 E2E 分類見[負載測試](../../tests/load/README.md)；跨語言契約使用介面文件、Schema／測試樣例。

## BA 失效分析

[BA 專用失效分析](backend-a-failure-analysis.md)整理原因、影響、偵測、降級、復原、責任與驗收門檻；[本地故障演練工具](../../tests/faults/README.md)只操作自行啟動的 BA／Redis 程序與隔離 BB 測試端點。
本地元件證據與真實 BB／PostgreSQL／Web／VM 驗收分開，不以測試數、設定時限或單次恢復時間宣稱可靠度、RPN 或正式 SLO。
