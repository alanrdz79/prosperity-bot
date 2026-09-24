import os
from datetime import timezone

# Configuración y Credenciales
API_KEY = os.getenv('BINANCE_API_KEY', 'TU_API_KEY_TESTNET')
API_SECRET = os.getenv('BINANCE_API_SECRET', 'TU_API_SECRET_TESTNET')

SYMBOL = 'SOL/USDT'
TIMEFRAME = '5m'
CAPITAL_BASE_INICIAL = 10.0

# Horarios UTC
VENTANA_ASIA = (0, 2)         # 00:00 a 02:00 UTC (Apertura Tokio/HK/Singapur)
VENTANA_SOLAPAMIENTO = (13, 17) # 13:00 a 17:00 UTC (Pico Londres/NY y Wall St)
HORA_CIERRE_NY = 20           # 20:00 UTC (Rebalanceo Wall Street)
