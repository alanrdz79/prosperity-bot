import ccxt
import pandas as pd
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from typing import Tuple, Optional

# =====================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES (TESTNET BINANCE FUTURES)
# =====================================================================
# Llaves obtenidas en: https://testnet.binancefuture.com
import os
from dotenv import load_dotenv

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
    """Gestiona el dimensionamiento y desescalado de apalancamiento."""
    @staticmethod
    def calculate_trade_parameters(balance: float, price: float):
        if balance < 30.0:
            leverage = 4        # Microcuenta: superar lote mínimo
            margin_pct = 0.50   # Margen de $5 a $15 USD
        elif balance < 100.0:
            leverage = 3
            margin_pct = 0.35
        elif balance < 500.0:
            leverage = 2
            margin_pct = 0.25
        else:
            leverage = 1        # Cuenta consolidada: preservación
            margin_pct = 0.15

        margin_used = balance * margin_pct
        notional_value = margin_used * leverage
        
        # Filtro estricto de mínimo nocional de Binance ($5 USDT)
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
# 3. CONTROLADOR TEMPORAL DE SESIONES (LUNES A VIERNES)
# =====================================================================
class SessionScheduler:
    """Gobierna las ventanas de liquidez institucional en UTC."""
    def __init__(self):
        self.VENTANA_ASIA = (0, 2)            # 00:00 a 02:00 UTC
        self.VENTANA_SOLAPAMIENTO = (13, 17)  # 13:00 a 17:00 UTC
        self.HORA_CIERRE_NY = 20               # 20:00 UTC

    def get_session_status(self) -> Tuple[bool, Optional[str], str]:
        ahora_utc = datetime.now(timezone.utc)
        dia_semana = ahora_utc.weekday()  # 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo
        hora = ahora_utc.hour
        minuto = ahora_utc.minute

        # 1. Filtro estricto de fin de semana
        if dia_semana == 5 or (dia_semana == 4 and hora >= 21) or (dia_semana == 6 and hora < 23):
            return False, None, "Fin de semana (Baja liquidez institucional)."

        # 2. Ventana Asiática (00:00 - 02:00 UTC)
        if self.VENTANA_ASIA[0] <= hora < self.VENTANA_ASIA[1]:
            return True, "MEAN_REVERSION_ASIA", "Sesión Asiática (Régimen Reversión a la Media)."

        # 3. Gran Solapamiento Londres / Nueva York (13:00 - 17:00 UTC)
        if self.VENTANA_SOLAPAMIENTO[0] <= hora < self.VENTANA_SOLAPAMIENTO[1]:
            if hora == 14 and minuto < 45:
                return False, None, "Apertura Wall Street (14:30 - 14:45 UTC): Pausa por volatilidad tóxica."
            return True, "BREAKOUT_MOMENTUM_NY", "Gran Solapamiento (Régimen Ruptura y Momentum)."

        # 4. Cierre Wall Street (20:00 - 20:30 UTC)
        if hora == self.HORA_CIERRE_NY and minuto <= 30:
            return True, "REBALANCE_CLOSE_NY", "Cierre Wall Street (Régimen Rebalanceo)."

        return False, None, f"Fuera de horario óptimo ({ahora_utc.strftime('%H:%M')} UTC)."

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

    def despachar_orden(self):
        """Ejecuta orden de compra y coloca TP (+3%) y SL (-1.2%) nativos en servidor."""
        try:
            balance = self.obtener_balance_disponible()
            ticker = self.exchange.fetch_ticker(SYMBOL)
            precio_actual = float(ticker['last'])

            params_trade = self.sizer.calculate_trade_parameters(balance, precio_actual)
            leverage = params_trade['leverage']
            
            # Fija el apalancamiento dinámico calculado
            self.exchange.set_leverage(leverage, SYMBOL)
            
            cantidad_ajustada = float(self.exchange.amount_to_precision(SYMBOL, params_trade['units']))
            
            print(f"\n🚀 [EJECUCIÓN] Enviando orden BUY de {cantidad_ajustada} {SYMBOL} (Apalancamiento: x{leverage})...")
            orden = self.exchange.create_order(SYMBOL, 'market', 'buy', cantidad_ajustada)
            precio_llenado = float(orden.get('average') or precio_actual)

            # Colocar órdenes de protección nativas en Binance
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
        # 1. Comprobar si hay una posición activa en el broker
        posicion = self.obtener_posicion_abierta()
        if posicion > 0:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] 🔒 Custodia Activa: Posición de {posicion} {SYMBOL} abierta. Esperando resolución de TP/SL...")
            time.sleep(30)
            return

        # 2. Evaluar el reloj institucional (SessionScheduler)
        operable, estrategia, motivo = self.scheduler.get_session_status()
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
