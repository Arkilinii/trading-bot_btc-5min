# BTC 5m Momentum Bot — Binance + Polymarket

Bot para mercados **BTC Up or Down 5m** de Polymarket. La estrategia:

1. Espera hasta la ventana final configurable de la ronda (por defecto 120 s).
2. Mide el movimiento de BTC/USDT en Binance desde el inicio de la ronda.
3. Solo opera si el movimiento absoluto está entre **70 y 100 USD**.
4. La dirección de la operación coincide con la dirección del movimiento:
   - BTC sube -> compra `Up`
   - BTC baja -> compra `Down`
5. Solo entra si el mejor precio de compra del contrato está entre **0.80 y 0.99**.
6. Si el contrato llega a una concentración extrema (por defecto >=95%), realiza una cobertura/toma de beneficio parcial configurable (por defecto 10%).
7. El resto se mantiene hasta el cierre/resolución.

## Importante sobre la fuente de resolución

Polymarket indica que estos mercados resuelven usando el **BTC/USD TWAP de Chainlink**, no el precio de Binance. Binance se usa aquí como señal de momentum, no como fuente de settlement. Por eso el umbral de 70–100 USD debe considerarse una señal aproximada, no una garantía de resultado.

## Estructura

```text
polymarket-btc5m-bot/
├── keys/
│   ├── .env.example
│   └── .gitkeep
├── scripts/
│   ├── paper_btc5m.py
│   ├── live_btc5m.py
│   └── test_connection.py
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── binance_feed.py
│   ├── polymarket.py
│   └── strategy.py
├── logs/
├── tests/
├── .gitignore
├── requirements.txt
└── README.md
```

## 1. Instalación

Recomendado Python 3.11–3.13.

```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd polymarket-btc5m-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Credenciales

Copia:

```bash
cp keys/.env.example keys/.env
nano keys/.env
```

El bot **no necesita API key de Binance para leer BTC/USDT**: el feed de mercado de Binance es público. Si quieres añadir operaciones en Binance en el futuro, sus credenciales pueden añadirse aparte.

Para Polymarket se usan:
- `POLY_PRIVATE_KEY`: private key de la wallet que firma las órdenes.
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`

No compartas nunca `keys/.env`.

## 3. Primero: prueba de conexión

```bash
python scripts/test_connection.py
```

Comprueba:
- conexión al Gamma API;
- identificación de la ronda BTC 5m actual;
- conexión al CLOB;
- credenciales L2;
- lectura del order book.

## 4. Paper trading

No manda órdenes.

```bash
python scripts/paper_btc5m.py
```

Para acelerar una prueba:

```bash
python scripts/paper_btc5m.py --poll 1
```

Los logs normales se guardan temporalmente en `logs/` y se archivan automáticamente en archivos diarios dentro de `logs/paper/` o `logs/live/`. Los eventos de trading se archivan por ronda en `trades/paper/` o `trades/live/`.

## 5. Gestión automática de logs

- **History:** los logs normales se acumulan durante 6 rondas (30 minutos). Al comenzar la ronda siguiente se archivan automáticamente en el archivo histórico del día y se limpia el NOW.
- **Trades:** los eventos `New 5m round`, `Entry`, `Hedge` y `Exit` se archivan al comenzar cada nueva ronda, dejando el NOW preparado para la ronda siguiente.
- **STOP:** cualquier contenido pendiente de la ronda o bloque actual se archiva automáticamente antes de terminar el proceso.
- Ya no se utiliza la carpeta `data/`.
- El guardado se realiza en los archivos diarios existentes de `logs/<mode>/` y `trades/<mode>/`.

## 5. Live trading

**Esto envía órdenes reales a Polymarket.**

```bash
python scripts/live_btc5m.py
```

El tamaño por operación se controla con `TRADE_USDC`.

Antes de utilizar dinero real, recomiendo ejecutar paper durante suficientes rondas y comprobar especialmente:
- liquidez real del contrato;
- slippage;
- fill parcial;
- diferencia entre Binance y Chainlink;
- comportamiento cerca del cierre.

## Variables principales

En `keys/.env`:

```text
ROUND_SECONDS=300
ENTRY_WINDOW_SECONDS=120
MIN_MOVE_USD=70
MAX_MOVE_USD=100
MIN_CONTRACT_PRICE=0.80
MAX_CONTRACT_PRICE=0.99
EXTREME_PROBABILITY=0.95
PARTIAL_HEDGE_PCT=0.10
TRADE_USDC=10
POLL_SECONDS=1
```

`ENTRY_WINDOW_SECONDS=120` significa que solo se evalúa una entrada cuando quedan <=120 segundos.

## Lógica de protección

El bot:
- no abre dos posiciones en la misma ronda;
- no entra si BTC no está dentro del rango de movimiento;
- no entra si el contrato está fuera del rango 0.80–0.99;
- no invierte la dirección;
- no vuelve a entrar después de una salida parcial;
- registra cada decisión en logs.

La "cobertura" implementada por defecto es una **venta parcial del 10% de la posición ganadora cuando el precio alcanza >=0.95**. Esto evita introducir una segunda apuesta contra la posición principal.

## Nota sobre ejecución

El modo live utiliza órdenes FOK para la entrada de mercado. Si no existe liquidez suficiente al precio disponible, la orden puede no ejecutarse. Esto es deliberado: el bot no persigue el precio fuera del rango configurado.

## Live / real trading configuration

Real Polymarket credentials are kept outside `.env` in `configuration.py`.
The supplied file intentionally contains `undefined` placeholders.

Required real-account values:

- `POLY_PRIVATE_KEY`
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`
- `POLY_FUNDER`
- `POLY_SIGNATURE_TYPE`

`configuration.py` is ignored by Git so real credentials are not committed.

### Live safety behaviour

`scripts/live_btc5m.py` uses the same round calculation, entry conditions, hedge logic, exit logic and logging flow as paper mode.

If any required real credential is `undefined`, Live does **not** send real orders. It automatically runs the same execution logic in paper fallback and writes a clear `Operation not performed` message. Once all required credentials are configured and the account/authentication check succeeds, real `buy`/`sell` orders are enabled.

The web application uses `scripts/live_btc5m.py` for the Live button and stores Live logs under `logs/live` and `trades/live`.
