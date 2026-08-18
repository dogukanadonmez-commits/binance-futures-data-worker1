
# Binance Futures Data Worker

Amaç: ChatGPT ortamının doğrudan parametrik Kline API çağrılarında yaşadığı ACCESS-BLOCK sorununu GitHub Actions üzerinde aşmak.

## Çıktılar
- `public/health.json`: EVREN / BATCH / OHLCV / GREEN kapıları
- `public/scan.json`: ön seçilen coinler, BTC rejim verisi ve 1D/4H/1H/15m indikatörleri

## Veri akışı
1. Binance USDⓈ-M `exchangeInfo` ile aktif USDT perpetual evreni.
2. Binance batch ticker; başarısızsa Bybit V5 linear ticker fallback.
3. En güçlü 8 aday.
4. Her adayda Binance, başarısızsa Bybit üzerinden 120 mum:
   1d / 4h / 1h / 15m.
5. MA99, EMA20/50, RSI, MACD, ADX, ATR, Bollinger, OBV, VWAP ve yapı yardımcıları hesaplanır.
6. JSON repo içine yazılır.

## Kurulum
1. Yeni bir **public GitHub repository** oluşturun.
2. Bu paketin içeriğini repository root'una yükleyin.
3. Actions sekmesinden `Futures Data Worker` workflow'unu `Run workflow` ile bir kez elle çalıştırın.
4. `public/health.json` içinde `"green": true` görülürse veri katmanı hazırdır.
5. Sonrasında workflow 5 dakikada bir çalışır.

Public API'ler için API anahtarı gerekmez. Arkham/Nansen/LunarCrush gibi Alpha kaynakları daha sonra GitHub Actions Secrets ile eklenebilir.

## ChatGPT veri URL'leri
Public repo için:
`https://raw.githubusercontent.com/OWNER/REPO/main/public/health.json`
`https://raw.githubusercontent.com/OWNER/REPO/main/public/scan.json`

Bu iki URL ana alarm görevine veri adaptörü olarak verildiğinde ChatGPT artık borsa Kline endpoint'lerini doğrudan çağırmaz.
