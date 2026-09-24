import ccxt
import pandas as pd
import time
import sys
import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Tuple, Optional

sys.stdout.reconfigure(encoding='utf-8')

# =====================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# =====================================================================
load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY', 'TU_API_KEY_TESTNET')
API_SECRET = os.getenv('BINANCE_API_SECRET', 'TU_API_SECRET_TESTNET')

SYMBOL = 'SOL/USDT'
TIMEFRAME = '5m'
CAPITAL_BASE_INICIAL = 10.0  # Microcuenta de arranque ($10 USD)

# =====================================================================
# 2. NOTIFICADOR DE TELEGRAM (Conectado Externamente)
# =====================================================================
from prosperityscal_9_telegram import TelegramNotifier

# =====================================================================
# 3. CONTROLADOR DE APALANCAMIENTO Y TAMAÑO DINÁMICO (DLD ADAPTATIVO)
# =====================================================================
class AdaptiveLeverageSizer:
    """
    Controlador adaptativo de apalancamiento multifactorial.
    Reduce el apalancamiento por capital, por volatilidad y por racha negativa.
    """
    def __init__(self, min_notional_floor: float = 5.5):
        self.min_notional_floor = min_notional_floor

    def calculate_leverage_and_sizing(
        self, 
        current_balance: float, 
        current_price: float, 
        atr_ratio: float = 1.0, 
        consecutive_losses: int = 0
    ) -> dict:
        # 1. Apalancamiento base por tramo de capital
        if current_balance < 30.0:
            base_leverage = 4
            base_margin_pct = 0.50
        elif current_balance < 100.0:
            base_leverage = 3
            base_margin_pct = 0.35
        elif current_balance < 500.0:
            base_leverage = 2
            base_margin_pct = 0.25
        else:
            base_leverage = 1
            base_margin_pct = 0.15

        effective_leverage = base_leverage

        # 2. Reducción por volatilidad anómala
        if atr_ratio > 1.5:
            # Si el mercado está 50% más volátil de lo normal, recorta 1 escalón
            effective_leverage = max(1, effective_leverage - 1)

        # 3. Freno de mano por racha de pérdidas consecutivas
        margin_pct = base_margin_pct
        if consecutive_losses >= 2:
            # Corta la asignación de margen al 50% para frenar interés compuesto inverso
            margin_pct = margin_pct * 0.5

        # 4. Cálculo del valor nocional y validación de piso mínimo
        margin_to_use = current_balance * margin_pct
        notional_value = margin_to_use * effective_leverage

        # Garantizar que cumpla el piso de Binance
        if notional_value < self.min_notional_floor:
            notional_value = self.min_notional_floor
            margin_to_use = notional_value / effective_leverage

        # Verificar si el margen requerido supera el balance disponible
        if margin_to_use > current_balance:
            raise ValueError("Saldo insuficiente para cumplir el tamaño mínimo de orden de Binance.")

        units = notional_value / current_price

        return {
            'leverage': int(effective_leverage),
            'margin_allocated': round(margin_to_use, 2),
            'notional_value': round(notional_value, 2),
            'units': units,
            'reason': (
                f"CapTier: x{base_leverage} | "
                f"VolPenalty: {'SÍ' if atr_ratio > 1.5 else 'NO'} | "
                f"LossPenalty: {'SÍ' if consecutive_losses >= 2 else 'NO'}"
            )
        }

# =====================================================================
# 4. CONTROLADOR TEMPORAL DE SESIONES (LUNES A VIERNES)
# =====================================================================
class SessionScheduler:
    def __init__(self):
        self.VENTANA_ASIA = (0, 2)            
        self.VENTANA_SOLAPAMIENTO = (13, 17)  
        self.HORA_CIERRE_NY = 20               

    def get_session_status(self) -> Tuple[bool, Optional[str], str]:
        ahora_utc = datetime.now(timezone.utc)
        dia_semana = ahora_utc.weekday()  
        hora = ahora_utc.hour
        minuto = ahora_utc.minute

        if dia_semana == 5 or (dia_semana == 4 and hora >= 21) or (dia_semana == 6 and hora < 23):
            return False, None, "Fin de semana (Baja liquidez institucional)."
            
        if self.VENTANA_ASIA[0] <= hora < self.VENTANA_ASIA[1]:
            return True, "MEAN_REVERSION_ASIA", "Sesión Asiática (Reversión a la media)."
            
        if self.VENTANA_SOLAPAMIENTO[0] <= hora < self.VENTANA_SOLAPAMIENTO[1]:
            # Pausa exacta de 14:30 a 14:45 UTC
            if hora == 14 and (30 <= minuto <= 45):
                return False, None, "Apertura Wall Street (14:30 - 14:45 UTC): Pausa por volatilidad tóxica."
            return True, "BREAKOUT_MOMENTUM_NY", "Gran Solapamiento Londres / Nueva York (Rupturas y momentum)."
            
        if hora == self.HORA_CIERRE_NY and minuto <= 30:
            return True, "REBALANCE_CLOSE_NY", "Cierre de Wall Street (Rebalanceos MOC)."

        return False, None, f"Fuera de horario óptimo ({ahora_utc.strftime('%H:%M')} UTC)."

from collections import deque
import numpy as np

# =====================================================================
# 5. FAST PATH: MEMORIA RAM PURA (DEQUE)
# =====================================================================
class FastPathMemory:
    """
    Mantiene el estado del mercado en memoria RAM pura usando deques.
    Evita recalcular o descargar el historial completo en cada ciclo.
    """
    def __init__(self, maxlen: int = 100):
        self.maxlen = maxlen
        self.candles = deque(maxlen=maxlen)

    def inicializar_memoria(self, exchange, symbol: str, timeframe: str):
        """Descarga el historial inicial de una sola vez."""
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=self.maxlen)
            for candle in ohlcv:
                self.candles.append(candle)
            print(f"🧠 FastPath: Memoria RAM cargada con {len(self.candles)} velas.")
            return True
        except Exception as e:
            print(f"❌ Error cargando memoria FastPath: {e}")
            return False

    def actualizar_ultima_vela(self, exchange, symbol: str, timeframe: str):
        """Descarga solo la vela actual/reciente y actualiza el Deque (O(1))."""
        recientes = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=2)
        if not recientes:
            return
        
        # Actualiza o inserta la vela en el deque
        ultima_memoria = self.candles[-1][0] if len(self.candles) > 0 else 0
        for vela in recientes:
            if vela[0] > ultima_memoria:
                self.candles.append(vela) # Nueva vela cerrada
            elif vela[0] == ultima_memoria:
                self.candles[-1] = vela   # Actualiza la vela viva actual

    def get_dataframe(self) -> pd.DataFrame:
        """Convierte la memoria a DataFrame de forma ultrarrápida."""
        return pd.DataFrame(list(self.candles), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

# =====================================================================
# 6. MOTOR PRINCIPAL DE EJECUCIÓN (PROSPERITY RUNNER)
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
        self.sizer = AdaptiveLeverageSizer()
        self.telegram = TelegramNotifier()
        self.consecutive_losses = 0 
        self.fast_path = FastPathMemory(maxlen=100) # Memoria RAM pura

    def inicializar(self):
        try:
            self.exchange.load_markets()
            try:
                self.exchange.set_margin_mode('ISOLATED', SYMBOL)
            except Exception:
                pass  
            
            # Llenar la RAM con el historial
            if not self.fast_path.inicializar_memoria(self.exchange, SYMBOL, TIMEFRAME):
                return False

            msg = f"✅ Conectado a Binance Futures Testnet | Par: {SYMBOL} | Modo: ISOLATED"
            print(msg)
            self.telegram.send_telegram_message(f"<b>PROSPERITY INICIADO</b>\n{msg}")
            return True
        except Exception as e:
            msg = f"❌ Error de inicialización: {e}"
            print(msg)
            self.telegram.send_telegram_message(f"<b>ALERTA PROSPERITY</b>\n{msg}")
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

    def evaluar_estrategia(self, estrategia: str) -> tuple[bool, float]:
        # 1. Actualización Ultrarrápida (Solo vela actual)
        self.fast_path.actualizar_ultima_vela(self.exchange, SYMBOL, TIMEFRAME)
        df = self.fast_path.get_dataframe()
        
        # 2. Cálculo de Bandas
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['std'] = df['close'].rolling(window=20).std()
        df['upper_band'] = df['ema_20'] + (df['std'] * 2.0)
        df['lower_band'] = df['ema_20'] - (df['std'] * 2.0)
        df['vol_promedio'] = df['volume'].rolling(window=20).mean()

        # 3. Cálculo de Volatilidad (ATR Ratio)
        df['tr'] = df['high'] - df['low']
        atr_14 = df['tr'].rolling(14).mean().iloc[-1]
        atr_50 = df['tr'].rolling(50).mean().iloc[-1]
        atr_ratio = (atr_14 / atr_50) if atr_50 > 0 else 1.0

        # 4. Cálculo de RSI (Nuevo)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        rsi_actual = df['rsi'].iloc[-1]

        precio = df['close'].iloc[-1]
        vol_actual = df['volume'].iloc[-1]
        vol_medio = df['vol_promedio'].iloc[-1]

        hora_str = datetime.now(timezone.utc).strftime('%H:%M:%S')
        print(f"[{hora_str} UTC] {estrategia} | P: ${precio:.2f} | RSI: {rsi_actual:.1f} | ATR Ratio: {atr_ratio:.2f}")

        # 5. Inferencia de señal
        if estrategia == "BREAKOUT_MOMENTUM_NY":
            # Ruptura con volumen fuerte y sin sobrecompra extrema
            if precio > df['upper_band'].iloc[-1] and vol_actual > (vol_medio * 1.8) and rsi_actual < 75:
                return True, atr_ratio
        elif estrategia == "MEAN_REVERSION_ASIA":
            # Reversión desde banda inferior con RSI indicando sobreventa
            if precio <= df['lower_band'].iloc[-1] and vol_actual > vol_medio and rsi_actual < 35:
                return True, atr_ratio

        return False, atr_ratio

    def despachar_orden(self, estrategia: str, atr_ratio: float):
        try:
            balance = self.obtener_balance_disponible()
            ticker = self.exchange.fetch_ticker(SYMBOL)
            precio_actual = float(ticker['last'])

            params_trade = self.sizer.calculate_leverage_and_sizing(
                current_balance=balance,
                current_price=precio_actual,
                atr_ratio=atr_ratio,
                consecutive_losses=self.consecutive_losses
            )
            leverage = params_trade['leverage']
            
            self.exchange.set_leverage(leverage, SYMBOL)
            
            cantidad_ajustada = float(self.exchange.amount_to_precision(SYMBOL, params_trade['units']))
            
            print(f"\n🚀 [EJECUCIÓN] Enviando orden BUY de {cantidad_ajustada} {SYMBOL} (Apalancamiento: x{leverage})...")
            print(f"💡 Motivo de Riesgo: {params_trade['reason']}")
            
            orden = self.exchange.create_order(SYMBOL, 'market', 'buy', cantidad_ajustada)
            precio_llenado = float(orden.get('average') or precio_actual)

            precio_tp = float(self.exchange.price_to_precision(SYMBOL, precio_llenado * 1.030))
            precio_sl = float(self.exchange.price_to_precision(SYMBOL, precio_llenado * 0.988))

            self.exchange.create_order(SYMBOL, 'TAKE_PROFIT_MARKET', 'sell', cantidad_ajustada, 
                                       params={'stopPrice': precio_tp, 'reduceOnly': True})
            self.exchange.create_order(SYMBOL, 'STOP_MARKET', 'sell', cantidad_ajustada, 
                                       params={'stopPrice': precio_sl, 'reduceOnly': True})

            print(f"🛡️ Órdenes activas en Binance: TP @ ${precio_tp} | SL @ ${precio_sl}")
            
            # Notificación a Telegram
            msg_telegram = (
                f"🚨 <b>EJECUCIÓN PROSPERITY</b> 🚨\n\n"
                f"<b>Activo:</b> {SYMBOL}\n"
                f"<b>Régimen:</b> {estrategia}\n"
                f"<b>Acción:</b> COMPRA (LONG)\n"
                f"<b>Apalancamiento:</b> x{leverage}\n"
                f"<b>Riesgo:</b> {params_trade['reason']}\n"
                f"<b>Precio Entrada:</b> ${precio_llenado:.2f}\n"
                f"<b>Take Profit:</b> ${precio_tp}\n"
                f"<b>Stop Loss:</b> ${precio_sl}"
            )
            self.telegram.send_telegram_message(msg_telegram)

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
            signal, atr_ratio = self.evaluar_estrategia(estrategia)
            if signal:
                print(f"🔥 Señal detectada en régimen {estrategia}.")
                self.despachar_orden(estrategia, atr_ratio)
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
