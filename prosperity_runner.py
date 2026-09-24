import ccxt
import pandas as pd
import time
from datetime import datetime, timezone

from core.config.session_config import API_KEY, API_SECRET, SYMBOL, TIMEFRAME, CAPITAL_BASE_INICIAL
from decision.session_scheduler import SessionScheduler
from risk.dynamic_leverage import DynamicLeverageSizer

class ProsperityFuturesRunner:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True
            }
        })
        self.exchange.set_sandbox_mode(True)
        self.scheduler = SessionScheduler()
        self.sizer = DynamicLeverageSizer()

    def inicializar(self):
        """Prepara conexión, apalancamiento y tipo de margen."""
        try:
            self.exchange.load_markets()
            try:
                self.exchange.set_margin_mode('ISOLATED', SYMBOL)
            except Exception:
                pass  # Ya configurado en aislado
            print(f"✅ Conectado a Binance Futures Testnet | Par: {SYMBOL} | Modo: ISOLATED")
            return True
        except Exception as e:
            print(f"❌ Error de inicialización: {e}")
            return False

    def obtener_posicion_abierta(self) -> float:
        """Verifica si el exchange registra contratos abiertos en el par."""
        try:
            positions = self.exchange.fetch_positions([SYMBOL])
            for pos in positions:
                if pos['symbol'] == SYMBOL:
                    contratos = float(pos.get('contracts') or 0.0)
                    return contratos
            return 0.0
        except Exception as e:
            print(f"⚠️ Error consultando posiciones: {e}")
            return 0.0

    def obtener_balance_disponible(self) -> float:
        try:
            balance_data = self.exchange.fetch_balance()
            return float(balance_data.get('USDT', {}).get('free', CAPITAL_BASE_INICIAL))
        except Exception:
            return CAPITAL_BASE_INICIAL

    def evaluar_estrategia(self, estrategia: str) -> bool:
        """Calcula indicadores según la sesión activa y retorna si hay entrada."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=60)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['std'] = df['close'].rolling(window=20).std()
            df['upper_band'] = df['ema_20'] + (df['std'] * 2.0)
            df['lower_band'] = df['ema_20'] - (df['std'] * 2.0)
            df['vol_promedio'] = df['volume'].rolling(window=20).mean()

            precio = df['close'].iloc[-1]
            vol_actual = df['volume'].iloc[-1]
            vol_medio = df['vol_promedio'].iloc[-1]

            hora_str = datetime.now(timezone.utc).strftime('%H:%M:%S')
            print(f"[{hora_str} UTC] Modo: {estrategia} | Precio: ${precio:.2f} | Vol Ratio: {vol_actual/vol_medio:.2f}x")

            # Estrategia de Gran Solapamiento: Ruptura con volumen
            if estrategia == "BREAKOUT_MOMENTUM_NY":
                if precio > df['upper_band'].iloc[-1] and vol_actual > (vol_medio * 1.8):
                    return True

            # Estrategia de Asia: Reversión desde banda inferior
            elif estrategia == "MEAN_REVERSION_ASIA":
                if precio <= df['lower_band'].iloc[-1] and vol_actual > vol_medio:
                    return True

            return False
        except Exception as e:
            print(f"⚠️ Error evaluando estrategia: {e}")
            return False

    def despachar_orden(self):
        """Ejecuta orden de compra y coloca TP (+3%) y SL (-1.2%) nativos en servidor."""
        try:
            balance = self.obtener_balance_disponible()
            ticker = self.exchange.fetch_ticker(SYMBOL)
            precio_actual = float(ticker['last'])

            params_trade = self.sizer.calculate_trade_parameters(balance, precio_actual)
            leverage = params_trade['leverage']
            
            self.exchange.set_leverage(leverage, SYMBOL)
            cantidad_ajustada = float(self.exchange.amount_to_precision(SYMBOL, params_trade['units']))
            
            print(f"\n🚀 [EJECUCIÓN] Enviando orden BUY de {cantidad_ajustada} {SYMBOL} (Apalancamiento: x{leverage})...")
            orden = self.exchange.create_order(SYMBOL, 'market', 'buy', cantidad_ajustada)
            precio_llenado = float(orden.get('average') or precio_actual)

            precio_tp = float(self.exchange.price_to_precision(SYMBOL, precio_llenado * 1.030))
            precio_sl = float(self.exchange.price_to_precision(SYMBOL, precio_llenado * 0.988))

            self.exchange.create_order(SYMBOL, 'TAKE_PROFIT_MARKET', 'sell', cantidad_ajustada, 
                                       params={'stopPrice': precio_tp, 'reduceOnly': True})
            self.exchange.create_order(SYMBOL, 'STOP_MARKET', 'sell', cantidad_ajustada, 
                                       params={'stopPrice': precio_sl, 'reduceOnly': True})

            print(f"🛡️ Órdenes activas en Binance: TP @ ${precio_tp} | SL @ ${precio_sl}")
        except Exception as e:
            print(f"❌ Error al despachar orden: {e}")

    def ejecutar_ciclo(self):
        # 1. Comprobar si hay una posición activa en el broker (Regla de Posesión Abierta)
        posicion = self.obtener_posicion_abierta()
        if posicion > 0:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] 🔒 Custodia Activa: Posición de {posicion} {SYMBOL} abierta. Esperando resolución de TP/SL...")
            time.sleep(30)
            return

        # 2. Evaluar el reloj institucional (SessionScheduler)
        operable, estrategia, motivo = self.scheduler.get_active_session()
        if not operable:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] 💤 En reposo: {motivo}")
            time.sleep(60)  # Pausa prolongada para respetar límites de API
            return

        # 3. Evaluar señales de mercado
        try:
            if self.evaluar_estrategia(estrategia):
                print(f"🔥 Señal detectada en régimen {estrategia}.")
                self.despachar_orden()
                time.sleep(30)
            else:
                time.sleep(15)
        except Exception as e:
            print(f"⚠️ Error en ciclo de mercado: {e}")
            time.sleep(15)

if __name__ == "__main__":
    runner = ProsperityFuturesRunner()
    if runner.inicializar():
        print("Iniciando orquestador institucional de PROSPERITY...")
        while True:
            runner.ejecutar_ciclo()
