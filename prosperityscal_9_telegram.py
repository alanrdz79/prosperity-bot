"""
prosperityscal_9_telegram.py - Módulo 9 de 10: Notificaciones por Telegram (v2, corregido)
Proyecto CONTINUITY - Scalping Automatizado

Cambios vs v1:
  - URL corregida: https://api.telegram.org/bot<TOKEN>/sendMessage (faltaba "bot").
  - Se distingue "sin operaciones hoy" de "error de base de datos".
  - No se crea una BD vacía si el archivo no existe; se valida que exista la tabla.
  - Filtro de "hoy" por rango [00:00, 24:00) local, robusto ante formatos ISO.
  - Conexión SQLite cerrada siempre (try/finally).
  - parse_mode HTML (Markdown legacy falla con '_' o '*' sueltos).
  - Validación de token Y chat_id; verify_connection() para diagnóstico.
  - logging en lugar de print.

Supuesto sobre la BD: tabla `trades` con columnas
  timestamp (texto ISO local, ej. '2026-09-23 14:05:31'), net_profit_usd, fees_usd.
Si guardas timestamps en UTC o en epoch, ajusta _day_bounds() / la consulta.
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict

import requests
from dotenv import load_dotenv


# Fallback temporal para herencia de ConectorBase
class ConectorBase:
    pass


load_dotenv()

logger = logging.getLogger("CONTINUITY.Telegram")

_PLACEHOLDERS = {"", "TU_TOKEN_AQUI", "TU_CHAT_ID_AQUI"}


class DBError(Exception):
    """Error al leer la base de datos (distinto de 'sin operaciones')."""


class TelegramNotifier(ConectorBase):
    """Envía mensajes y reportes periódicos al chat de Telegram configurado."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        db_path: str = "continuity_metrics.db",
        initial_capital: float = 1000.0,
    ):
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = str(chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.db_path = db_path
        self.initial_capital = initial_capital

    # ------------------------------------------------------------------ #
    # Configuración
    # ------------------------------------------------------------------ #
    @property
    def configured(self) -> bool:
        return self.bot_token not in _PLACEHOLDERS and self.chat_id not in _PLACEHOLDERS

    def _api_url(self, method: str) -> str:
        return self.BASE_URL.format(token=self.bot_token, method=method)

    def verify_connection(self) -> bool:
        """Diagnóstico: valida token (getMe) y envía un mensaje de prueba al chat."""
        if not self.configured:
            logger.error("Token o chat_id sin configurar (revisa .env: "
                         "TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID).")
            return False
        try:
            r = requests.get(self._api_url("getMe"), timeout=10)
            if r.status_code != 200:
                logger.error("Token inválido. HTTP %s: %s", r.status_code, r.text)
                return False
            logger.info("Bot OK: @%s", r.json()["result"].get("username"))
        except requests.RequestException as e:
            logger.error("Sin conexión con Telegram: %s", e)
            return False
        return self.send_telegram_message("✅ CONTINUITY: conexión con Telegram verificada.", html=False)

    # ------------------------------------------------------------------ #
    # Base de datos
    # ------------------------------------------------------------------ #
    @staticmethod
    def _day_bounds() -> tuple:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        fmt = "%Y-%m-%d %H:%M:%S"
        return start.strftime(fmt), end.strftime(fmt)

    def _fetch_metrics_from_db(self) -> Optional[Dict]:
        """
        Devuelve métricas de hoy, o None si hoy no hubo operaciones.
        Lanza DBError si la BD no existe, no tiene la tabla o falla la consulta.
        """
        if not os.path.exists(self.db_path):
            raise DBError(f"No existe la base de datos: {self.db_path}")

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trades'")
            if cur.fetchone() is None:
                raise DBError(f"La BD {self.db_path} no tiene la tabla 'trades'.")

            start, end = self._day_bounds()
            cur.execute(
                "SELECT net_profit_usd, fees_usd FROM trades "
                "WHERE timestamp >= ? AND timestamp < ?",
                (start, end),
            )
            trades = cur.fetchall()
        except sqlite3.Error as e:
            raise DBError(f"Error SQLite: {e}") from e
        finally:
            if conn is not None:
                conn.close()

        if not trades:
            return None

        winning = 0
        gross_profit = gross_loss = total_fees = net_pnl = 0.0
        for pnl, fees in trades:
            pnl = pnl or 0.0
            fees = fees or 0.0
            total_fees += fees
            net_pnl += pnl
            if pnl > 0:
                winning += 1
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)

        total = len(trades)
        return {
            "total_trades": total,
            "winning_trades": winning,
            "win_rate": winning / total * 100,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_fees": total_fees,
            "net_pnl": net_pnl,
            "roi": net_pnl / self.initial_capital * 100,
        }

    # ------------------------------------------------------------------ #
    # Formato y envío
    # ------------------------------------------------------------------ #
    def format_report_message(self, metrics: Optional[Dict]) -> str:
        """Mensaje en HTML para Telegram."""
        if not metrics:
            return ("📊 <b>REPORTE CONTINUITY</b>\n\n"
                    "No se han ejecutado operaciones en lo que va de la jornada.")

        signo = "🟢" if metrics["roi"] > 0 else "🔴"
        return (
            f"📊 <b>REPORTE PERIÓDICO - PROSPERITY</b>\n"
            f"📅 {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📉 <b>Operaciones:</b> {metrics['total_trades']}\n"
            f"🏆 <b>Win Rate:</b> {metrics['win_rate']:.2f}%\n"
            f"📈 <b>Ganancia Bruta:</b> ${metrics['gross_profit']:.2f}\n"
            f"🩸 <b>Pérdida Bruta:</b> ${metrics['gross_loss']:.2f}\n"
            f"💸 <b>Comisiones:</b> ${metrics['total_fees']:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>PnL NETO:</b> ${metrics['net_pnl']:.2f}\n"
            f"{signo} <b>ROI del Capital:</b> {metrics['roi']:.4f}%\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <i>Sistema automatizado</i>"
        )

    def send_telegram_message(self, message: str, html: bool = True) -> bool:
        """Envía el mensaje. Devuelve True si Telegram lo aceptó."""
        if not self.configured:
            logger.warning("Telegram sin configurar; imprimiendo reporte localmente:\n%s", message)
            print("\n" + message)
            return False

        payload = {"chat_id": self.chat_id, "text": message}
        if html:
            payload["parse_mode"] = "HTML"

        try:
            r = requests.post(self._api_url("sendMessage"), json=payload, timeout=10)
        except requests.RequestException as e:
            logger.error("Error de conexión con Telegram: %s", e)
            return False

        if r.status_code == 200:
            logger.info("Reporte enviado a Telegram.")
            return True

        logger.error("Falló el envío. HTTP %s: %s", r.status_code, r.text)
        return False

    def send_report(self) -> bool:
        """Punto de entrada para el Orquestador: lee BD, formatea y envía."""
        try:
            metrics = self._fetch_metrics_from_db()
        except DBError as e:
            logger.error("No se pudo generar el reporte: %s", e)
            return self.send_telegram_message(f"⚠️ CONTINUITY: error al leer métricas.\n{e}", html=False)
        return self.send_telegram_message(self.format_report_message(metrics))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 9/10: Reportes por Telegram")
    print("---------------------------------------------------------")

    notifier = TelegramNotifier(db_path="test_metrics.db", initial_capital=1000.0)

    # Paso 1: comprobar token y chat (independiente de la BD)
    if notifier.configured:
        notifier.verify_connection()

    # Paso 2: reporte real
    notifier.send_report()