import os
import time
import logging
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict

import ccxt
import pandas as pd
from dotenv import load_dotenv

# =====================================================================
# 1. CONFIGURACIÓN GLOBAL Y CREDENCIALES
# =====================================================================
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY', 'TU_API_KEY_TESTNET')
API_SECRET = os.getenv('BINANCE_API_SECRET', 'TU_API_SECRET_TESTNET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

SYMBOL = 'SOL/USDT'
TIMEFRAME = '5m'
CAPITAL_BASE_INICIAL = 10.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PROSPERITY")

# =====================================================================
# 2. NOTIFICACIONES (TELEGRAM)
# =====================================================================
class TelegramNotifier:
    """Envía notificaciones de ejecución y estado a Telegram."""
    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str, chat_id: str):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id and self.token != "TU_TOKEN_AQUI")

    def _api_url(self, method: str) -> str:
        return self.BASE_URL.format(token=self.token, method=method)

    def send_message(self, message: str) -> bool:
        if not self.configured:
            logger.warning(f"Telegram inactivo. Log local:\n{message}")
            return False

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        try:
            r = requests.post(self._api_url("sendMessage"), json=payload, timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Error Telegram: {e}")
            return False

# =====================================================================
# 3. CONTROLADOR DE SESIONES INSTITUCIONALES
# =====================================================================
class SessionScheduler:
    """Gobierna las ventanas de liquidez institucional en UTC."""
    def __init__(self):
        self.VENTANA_ASIA = (0, 2)         # 00:00 a 02:00 UTC
        self.VENTANA_SOLAPAMIENTO = (13, 17) # 13:00 a 17:00 UTC
        self.HORA_CIERRE_NY = 20           # 20:00 UTC

    def get_active_session(self) -> Tuple[bool, Optional[str], str]:
        ahora_utc = datetime.now(timezone.utc)
        dia_semana = ahora_utc.weekday()
        hora = ahora_utc.hour
        minuto = ahora_utc.minute

        if dia_semana == 5 or (dia_semana == 4 and hora >= 21) or (dia_semana == 6 and hora < 23):
            return False, None, "Fin de semana (Baja liquidez)."

        if self.VENTANA_ASIA[0] <= hora < self.VENTANA_ASIA[1]:
            return True, "MEAN_REVERSION_ASIA", "Sesión Asiática (Rango)."

        if self.VENTANA_SOLAPAMIENTO[0] <= hora < self.VENTANA_SOLAPAMIENTO[1]:
            if hora == 14 and minuto < 45:
                return False, None, "Apertura WS (14:30-14:45): Alta toxicidad."
            return True, "BREAKOUT_MOMENTUM_NY", "Gran Solapamiento (Impulso)."

        if hora == self.HORA_CIERRE_NY and minuto <= 30:
            return True, "REBALANCE_CLOSE_NY", "Cierre WS (Rebalanceo)."

        return False, None, f"Fuera de horario óptimo ({ahora_utc.strftime('%H:%M')} UTC)."

# =====================================================================
# 4. DIMENSIONAMIENTO DINÁMICO (ADAPTIVE LEVERAGE)
# =====================================================================
class AdaptiveLeverageSizer:
    """Reduce el apalancamiento por capital, volatilidad (ATR) y drawdown."""
    def __init__(self, min_notional_floor: float = 5.5):
        self.min_notional_floor = min_notional_floor

    def calculate_sizing(self, balance: float, price: float, atr_ratio: float, consecutive_losses: int) -> dict:
        # 1. Tramo de capital
        if balance < 30.0:
            leverage, margin_pct = 4, 0.50
        elif balance < 100.0:
            leverage, margin_pct = 3, 0.35
        elif balance < 500.0:
            leverage, margin_pct = 2, 0.25
        else:
            leverage, margin_pct = 1, 0.15

        # 2. Volatilidad Anómala
        if atr_ratio > 1.5:
            leverage = max(1, leverage - 1)

        # 3. Drawdown / Racha
        if consecutive_losses >= 2:
            margin_pct *= 0.5

        margin_to_use = balance * margin_pct
        notional_value = margin_to_use * leverage

        # Validar piso de Binance (5 USDT)
        if notional_value < self.min_notional_floor:
            notional_value = self.min_notional_floor
            margin_to_use = notional_value / leverage

        if margin_to_use > balance:
            raise ValueError("Saldo insuficiente para mínimo de orden.")

        return {
            'leverage': int(leverage),
            'margin_allocated': round(margin_to_use, 2),
            'notional_value': round(notional_value, 2),
            'units': notional_value / price,
            'reason': f"Cap: x{leverage} | Vol>1.5: {atr_ratio>1.5} | Losses>=2: {consecutive_losses>=2}"
        }

# =====================================================================
# 5. ORQUESTADOR PRINCIPAL PROSPERITY
# =====================================================================
class ProsperityBot:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })
        self.exchange.set_sandbox_mode(True)
        
        self.scheduler = SessionScheduler()
        self.sizer = AdaptiveLeverageSizer()
        self.notifier = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
        
        self.consecutive_losses = 0
        self.current_atr_ratio = 1.0

    def inicializar(self) -> bool:
        try:
            self.exchange.load_markets()
            try: self.exchange.set_margin_mode('ISOLATED', SYMBOL)
            except Exception: pass
            
            msg = f"✅ <b>PROSPERITY RUNNER INICIADO</b>\nConectado a Binance Testnet | {SYMBOL} AISLADO"
            logger.info(msg)
            self.notifier.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Error de inicialización: {e}")
            return False

    def obtener_posicion_abierta(self) -> float:
        try:
            positions = self.exchange.fetch_positions([SYMBOL])
            for pos in positions:
                if pos['symbol'] == SYMBOL:
                    return float(pos.get('contracts') or 0.0)
            return 0.0
        except Exception: return 0.0

    def evaluar_estrategia(self, estrategia: str) -> bool:
        ohlcv = self.exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['std'] = df['close'].rolling(window=20).std()
        df['upper_band'] = df['ema_20'] + (df['std'] * 2.0)
        df['lower_band'] = df['ema_20'] - (df['std'] * 2.0)
        df['vol_promedio'] = df['volume'].rolling(window=20).mean()

        # ATR proxy para volatilidad
        df['tr'] = df['high'] - df['low']
        df['atr_14'] = df['tr'].rolling(14).mean()
        df['atr_mean_50'] = df['atr_14'].rolling(50).mean()
        
        atr_actual = df['atr_14'].iloc[-1]
        atr_medio = df['atr_mean_50'].iloc[-1]
        self.current_atr_ratio = atr_actual / atr_medio if pd.notnull(atr_medio) and atr_medio > 0 else 1.0

        precio = df['close'].iloc[-1]
        vol_actual = df['volume'].iloc[-1]
        vol_medio = df['vol_promedio'].iloc[-1]

        logger.info(f"[{estrategia}] P: ${precio:.2f} | VolRatio: {vol_actual/vol_medio:.2f}x | ATR: {self.current_atr_ratio:.2f}")

        if estrategia == "BREAKOUT_MOMENTUM_NY":
            return precio > df['upper_band'].iloc[-1] and vol_actual > (vol_medio * 1.8)
        elif estrategia == "MEAN_REVERSION_ASIA":
            return precio <= df['lower_band'].iloc[-1] and vol_actual > vol_medio
        return False

    def despachar_orden(self):
        try:
            balance = float(self.exchange.fetch_balance().get('USDT', {}).get('free', CAPITAL_BASE_INICIAL))
            precio_actual = float(self.exchange.fetch_ticker(SYMBOL)['last'])

            params = self.sizer.calculate_sizing(balance, precio_actual, self.current_atr_ratio, self.consecutive_losses)
            
            self.exchange.set_leverage(params['leverage'], SYMBOL)
            cantidad = float(self.exchange.amount_to_precision(SYMBOL, params['units']))
            
            logger.info(f"🚀 Enviando orden BUY {cantidad} {SYMBOL} (x{params['leverage']})")
            orden = self.exchange.create_order(SYMBOL, 'market', 'buy', cantidad)
            p_llenado = float(orden.get('average') or precio_actual)

            p_tp = float(self.exchange.price_to_precision(SYMBOL, p_llenado * 1.030))
            p_sl = float(self.exchange.price_to_precision(SYMBOL, p_llenado * 0.988))

            self.exchange.create_order(SYMBOL, 'TAKE_PROFIT_MARKET', 'sell', cantidad, params={'stopPrice': p_tp, 'reduceOnly': True})
            self.exchange.create_order(SYMBOL, 'STOP_MARKET', 'sell', cantidad, params={'stopPrice': p_sl, 'reduceOnly': True})

            msg = (
                f"🚨 <b>NUEVA OPERACIÓN EJECUTADA</b>\n"
                f"<b>Par:</b> {SYMBOL}\n"
                f"<b>Tipo:</b> BUY/LONG\n"
                f"<b>Precio:</b> ${p_llenado:.2f}\n"
                f"<b>Apalancamiento:</b> x{params['leverage']}\n"
                f"<b>Motivo Riesgo:</b> {params['reason']}\n"
                f"<b>TP:</b> ${p_tp} | <b>SL:</b> ${p_sl}"
            )
            self.notifier.send_message(msg)

        except Exception as e:
            logger.error(f"Error de despacho: {e}")
            self.notifier.send_message(f"❌ <b>ERROR AL DESPACHAR ORDEN:</b>\n{e}")

    def ejecutar_ciclo(self):
        # 1. Regla de Posesión Abierta
        posicion = self.obtener_posicion_abierta()
        if posicion > 0:
            logger.info(f"🔒 Custodia Activa: Posición de {posicion} {SYMBOL} abierta...")
            time.sleep(30)
            return

        # 2. Horario Institucional
        operable, estrategia, motivo = self.scheduler.get_active_session()
        if not operable:
            logger.info(f"💤 Reposo: {motivo}")
            time.sleep(60)
            return

        # 3. Señal
        try:
            if self.evaluar_estrategia(estrategia):
                logger.info(f"🔥 Señal en {estrategia}.")
                self.despachar_orden()
                time.sleep(30)
            else:
                time.sleep(15)
        except Exception as e:
            logger.error(f"Error en ciclo: {e}")
            time.sleep(15)

if __name__ == "__main__":
    bot = ProsperityBot()
    if bot.inicializar():
        while True:
            bot.ejecutar_ciclo()
