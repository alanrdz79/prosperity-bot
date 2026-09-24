"""
prosperityscal_8_logger.py - Módulo 8 de 10: Almacenamiento y Registro (Logging/Database)
Proyecto CONTINUITY - Scalping Automatizado

En estrategias de Alta Frecuencia (HFT), la velocidad es clave, pero el registro 
de las métricas es vital para el análisis posterior. Si no puedes medir el desempeño,
no puedes optimizar el bot.

Este módulo implementa dos capas de persistencia sin causar latencias pesadas:
1. Logging en archivo de texto: Para rastrear decisiones operativas (Errores, Alertas HMM).
2. Base de Datos SQLite local: Para almacenar el historial de operaciones (Trades),
   cambios de inventario, y estado del OFI en cada ejecución, permitiendo generar
   reportes estadísticos sin necesidad de consultar Binance.
"""

import sqlite3
import logging
import os
from datetime import datetime

class DataLogger:
    def __init__(self, db_name="continuity_metrics.db", log_file="bot_execution.log"):
        self.db_name = db_name
        self._setup_logging(log_file)
        self._setup_database()

    def _setup_logging(self, log_file):
        """Configura el registro de texto en archivo."""
        # Evita duplicar handlers si la clase se instancia varias veces
        logger = logging.getLogger("ContinuityBot")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
            
            # Handler para Archivo
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            # Handler para Consola
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        self.logger = logger

    def _setup_database(self):
        """
        Crea una base de datos SQLite ultraligera localmente.
        Ideal para hacer consultas rápidas mediante SQL (ej. sumar PnL del día).
        """
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        cursor = self.conn.cursor()
        
        # Tabla de Operaciones (Trades)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                symbol TEXT,
                side TEXT,
                price REAL,
                qty REAL,
                fees_usd REAL,
                net_profit_usd REAL,
                hmm_state INTEGER
            )
        ''')
        
        # Tabla de Telemetría (Microestructura)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telemetry (
                timestamp DATETIME,
                symbol TEXT,
                ofi REAL,
                micro_price REAL,
                volatility REAL,
                spread_optimal REAL,
                inventory_qty REAL
            )
        ''')
        
        self.conn.commit()

    def log_info(self, message: str):
        self.logger.info(message)

    def log_warning(self, message: str):
        self.logger.warning(message)

    def log_error(self, message: str):
        self.logger.error(message)

    def record_trade(self, symbol: str, side: str, price: float, qty: float, fees: float, pnl: float, hmm_state: int):
        """Almacena una operación finalizada en la base de datos."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, side, price, qty, fees_usd, net_profit_usd, hmm_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now(), symbol, side, price, qty, fees, pnl, hmm_state))
        self.conn.commit()
        self.logger.info(f"TRADE REGISTRADO | {side.upper()} {qty} {symbol} @ {price} | PnL: ${pnl:.4f}")

    def record_telemetry(self, symbol: str, ofi: float, micro_price: float, vol: float, spread: float, inv: float):
        """Almacena métricas internas del bot (sin necesariamente haber tradeado)."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO telemetry (timestamp, symbol, ofi, micro_price, volatility, spread_optimal, inventory_qty)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now(), symbol, ofi, micro_price, vol, spread, inv))
        self.conn.commit()

    def get_daily_performance(self):
        """
        Consulta rápida a la base de datos para obtener las métricas de hoy.
        """
        cursor = self.conn.cursor()
        today_date = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute('''
            SELECT count(id), sum(net_profit_usd), sum(fees_usd) 
            FROM trades 
            WHERE date(timestamp) = ?
        ''', (today_date,))
        
        result = cursor.fetchone()
        trades_count = result[0] or 0
        total_pnl = result[1] or 0.0
        total_fees = result[2] or 0.0
        
        return {
            "total_trades": trades_count,
            "net_profit_usd": total_pnl,
            "total_fees_paid": total_fees
        }

if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 8/10: Base de Datos y Logs")
    print("---------------------------------------------------------")
    
    # Instanciamos el manejador de datos
    datalogger = DataLogger(db_name="test_metrics.db")
    
    # Simulación 1: El bot registra sus métricas (Telemetría de la red)
    datalogger.log_info("Iniciando escaneo de mercado HFT...")
    datalogger.record_telemetry(symbol="SOL/USDT", ofi=15.5, micro_price=150.05, vol=0.8, spread=0.04, inv=0.0)
    
    # Simulación 2: El modelo detecta toxicidad y arroja advertencia
    datalogger.log_warning("HMM Detectó mercado tendencial (Estado 1). Pausando Market Making.")
    
    # Simulación 3: Operación cerrada exitosamente
    # Se registrará en la terminal, en el archivo de texto y en SQLite.
    datalogger.record_trade(symbol="SOL/USDT", side="BUY", price=150.00, qty=10.0, fees=0.30, pnl=2.50, hmm_state=0)
    datalogger.record_trade(symbol="SOL/USDT", side="SELL", price=150.25, qty=10.0, fees=0.30, pnl=2.50, hmm_state=0)
    datalogger.record_trade(symbol="SOL/USDT", side="SELL", price=150.10, qty=5.0, fees=0.15, pnl=-1.00, hmm_state=1) # Un SL
    
    # Simulación 4: Extraer reporte del día sin conectar a Binance
    print("\n--- REPORTE ESTADÍSTICO LOCAL (Consultado desde SQLite) ---")
    stats = datalogger.get_daily_performance()
    print(f"Operaciones hoy: {stats['total_trades']}")
    print(f"Comisiones pagadas: ${stats['total_fees_paid']:.2f}")
    print(f"Ganancia Neta (PnL): ${stats['net_profit_usd']:.2f}")
    
    print("\n-> Revisa el archivo 'bot_execution.log' que se acaba de crear en la carpeta.")
