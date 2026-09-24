import ccxt
import pandas as pd
import time
import sys
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Tuple, Optional

sys.stdout.reconfigure(encoding='utf-8')

# =====================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES (TESTNET BINANCE FUTURES)
# =====================================================================
load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY', 'TU_API_KEY_TESTNET')
API_SECRET = os.getenv('BINANCE_API_SECRET', 'TU_API_SECRET_TESTNET')

SYMBOL = 'SOL/USDT'
TIMEFRAME = '5m'
CAPITAL_BASE_INICIAL = 10.0  # Microcuenta de arranque ($10 USD)

# =====================================================================
# 2. CONTROLADOR DE APALANCAMIENTO Y TAMAÑO DINÁMICO (DLD)
# =====================================================================
class DynamicLeverageSizer:
    @staticmethod
    def calculate_trade_parameters(balance: float, price: float):
        if balance < 30.0:
            leverage = 4        
            margin_pct = 0.50   
        elif balance < 100.0:
            leverage = 3
            margin_pct = 0.35
        elif balance < 500.0:
            leverage = 2
            margin_pct = 0.25
        else:
            leverage = 1        
            margin_pct = 0.15

        margin_used = balance * margin_pct
        notional_value = margin_used * leverage
        
        if notional_value < 5.0:
            notional_value = 5.0
            margin_used = notional_value / leverage

        units = notional_value / price
        return {
            'balance': balance,
            'leverage': leverage,
            'margin_used': round(margin_used, 2),
            'notional_value': round(notional_value, 2),
            'units': units
        }

# =====================================================================
# 3. CONTROLADOR TEMPORAL (MODIFICADO PARA PRUEBA FORZADA)
# =====================================================================
class SessionScheduler:
    def get_session_status(self) -> Tuple[bool, Optional[str], str]:
        # PARA PRUEBA: Siempre devolvemos True y un régimen de prueba
        return True, "TEST_FORCE_BUY", "Modo de Prueba (Siempre Activo)."

# =====================================================================
# 4. MOTOR PRINCIPAL DE EJECUCIÓN (PROSPERITY RUNNER)
# =====================================================================
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
        try:
            self.exchange.load_markets()
            try:
                self.exchange.set_margin_mode('ISOLATED', SYMBOL)
            except Exception:
                pass  
            print(f"✅ Conectado a Binance Futures Testnet | Par: {SYMBOL} | Modo: ISOLATED")
            return True
        except Exception as e:
            print(f"❌ Error de inicialización: {e}")
            return False

    def obtener_posicion_abierta(self) -> float:
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

        # FORZADO PARA LA PRUEBA: Siempre devolver True para ver si dispara a Binance
        if estrategia == "TEST_FORCE_BUY":
            print("⚠️ Condiciones de indicador ignoradas. Disparando orden forzada para probar API.")
            return True

        return False

    def despachar_orden(self):
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
            
            # Pausa muy larga después del trade forzado para no bombardear Binance
            print("Trade de prueba enviado. El bot esperará 5 minutos antes del próximo escaneo.")
            time.sleep(300) 
        except Exception as e:
            print(f"❌ Error al despachar orden: {e}")

    def ejecutar_ciclo(self):
        posicion = self.obtener_posicion_abierta()
        if posicion > 0:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] 🔒 Custodia Activa: Posición de {posicion} {SYMBOL} abierta. Esperando resolución de TP/SL...")
            time.sleep(30)
            return

        operable, estrategia, motivo = self.scheduler.get_session_status()
        if not operable:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] 💤 En reposo: {motivo}")
            time.sleep(60)  
            return

        try:
            if self.evaluar_estrategia(estrategia):
                print(f"🔥 Señal detectada en régimen {estrategia}.")
                self.despachar_orden()
            else:
                time.sleep(15)
        except Exception as e:
            print(f"⚠️ Error en ciclo de mercado: {e}")
            time.sleep(15)

if __name__ == "__main__":
    runner = ProsperityFuturesRunner()
    if runner.inicializar():
        print("Iniciando orquestador de prueba (TEST_MODE) de PROSPERITY...")
        while True:
            runner.ejecutar_ciclo()
