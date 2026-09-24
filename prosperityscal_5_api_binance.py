"""
prosperityscal_5_api_binance.py - Módulo 5 de 10: Conexión API a Binance Futures
Proyecto CONTINUITY - Scalping Automatizado

Este módulo sirve como puente de conectividad (Gateway) entre nuestros 
algoritmos cuantitativos (Módulos 1 a 4) y los servidores de Binance.
Utiliza la librería ccxt (un estándar de la industria) para manejar 
autenticación, firmas, y llamadas REST/Websockets de forma segura.

Nota de Seguridad: Nunca almacenes tus API Keys reales directamente en el código.
Se deben usar variables de entorno (.env).
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

try:
    import ccxt
except ImportError:
    print("La librería ccxt no está instalada. Para instalarla ejecuta:")
    print("pip install ccxt")
    ccxt = None

class BinanceFuturesGateway:
    def __init__(self, api_key: str = None, api_secret: str = None, use_testnet: bool = True):
        """
        Inicializa la conexión con Binance USDⓈ-M Futures.
        Por defecto utiliza la Testnet (simulador) para evitar riesgos mientras se prueba.
        """
        if not ccxt:
            raise ImportError("Instala ccxt para continuar.")

        # Obtener claves de variables de entorno si no se proveen explícitamente
        self.api_key = api_key or os.getenv("BINANCE_API_KEY", "")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET", "")
        
        # Ignorar las llaves de relleno del .env para no provocar el error -2008 en endpoints públicos
        if "Pega_aqui" in self.api_key:
            self.api_key = None
        if "Pega_aqui" in self.api_secret:
            self.api_secret = None
            
        config = {
            'enableRateLimit': True, 
            'options': {
                'defaultType': 'spot', # Cambiado a Spot para coincidir con la llave y URLs del usuario
                'adjustForTimeDifference': True,
            }
        }
        
        if self.api_key and self.api_secret:
            config['apiKey'] = self.api_key
            config['secret'] = self.api_secret
            
        self.exchange = ccxt.binance(config)

        if use_testnet:
            # Redirección manual hacia la red Demo-API de Binance (Spot)
            self.exchange.urls['api']['public'] = 'https://demo-api.binance.com/api/v3'
            self.exchange.urls['api']['private'] = 'https://demo-api.binance.com/api/v3'
            print("[OK] Conectado a Binance [SPOT TESTNET DEMO - demo-api]")
        else:
            print("[WARN] Conectado a Binance Spot [MAINNET - Dinero Real]")

    def _safe_api_call(self, func, *args, **kwargs):
        """
        Envoltorio de seguridad para ejecutar llamadas a la API gestionando 
        estrictamente los códigos HTTP según la documentación de Binance.
        """
        try:
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded as e:
            # HTTP 429: Rate Limit
            print(f"[PELIGRO - HTTP 429] Límite de peticiones excedido. Aplicando freno de emergencia (Backoff)...")
            time.sleep(5)  # Pausa obligatoria para evitar baneo
            return None
        except ccxt.DDoSProtection as e:
            # HTTP 418 o 403 WAF: IP Baneada o bloqueada
            print(f"[CRÍTICO - HTTP 418/403] IP bloqueada temporalmente por Binance WAF. Deteniendo bot de inmediato.")
            # Aquí idealmente se lanzaría una señal al orquestador para apagado total.
            time.sleep(10) 
            return None
        except (ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
            # HTTP 5XX
            error_msg = str(e).lower()
            if "error desconocido" in error_msg or "unknown error" in error_msg:
                # HTTP 503: ESTADO DESCONOCIDO (Trampa Mortal)
                print(f"[TRAMPA MORTAL - HTTP 503] Estado Desconocido. NO REINTENTAR orden ciega. Pausando para revisión de estado.")
                # Aquí el orquestador debería consultar open_orders antes de seguir.
                return "UNKNOWN_STATE"
            elif "servicio no disponible" in error_msg or "service unavailable" in error_msg:
                print(f"[HTTP 503] Binance caído temporalmente. Es seguro reintentar más tarde.")
                return None
            else:
                print(f"[HTTP 5XX] Error interno de Binance. Fallo categórico, se puede reintentar.")
                return None
        except ccxt.BaseError as e:
            print(f"[API ERROR] {e}")
            return None
        except Exception as e:
            print(f"[SYSTEM ERROR] Error inesperado de conexión: {e}")
            return None

    def check_connection_and_balance(self) -> float:
        """Verifica la conexión solicitando el balance actual de USDT."""
        # Endpoint crudo de Spot (evita que CCXT intente cargar mercados)
        balance_info = self._safe_api_call(self.exchange.privateGetAccount)
        
        if balance_info and isinstance(balance_info, dict) and 'balances' in balance_info:
            for asset in balance_info['balances']:
                if asset['asset'] == 'USDT':
                    return float(asset['free'])
        return 0.0

    def fetch_limit_order_book(self, symbol: str, limit: int = 5) -> dict:
        """Obtiene el LOB. Devuelve el mejor Bid y Ask con sus volúmenes."""
        # Endpoint crudo para Spot (symbol sin la barra de separación)
        raw_symbol = symbol.replace("/", "")
        order_book = self._safe_api_call(self.exchange.publicGetDepth, {'symbol': raw_symbol, 'limit': limit})
        if not order_book or isinstance(order_book, str):
            return None
            
        best_bid = order_book['bids'][0] if len(order_book['bids']) > 0 else [0, 0]
        best_ask = order_book['asks'][0] if len(order_book['asks']) > 0 else [0, 0]
        
        return {
            "bid_price": float(best_bid[0]),
            "bid_vol": float(best_bid[1]),
            "ask_price": float(best_ask[0]),
            "ask_vol": float(best_ask[1])
        }

    def place_maker_order(self, symbol: str, side: str, qty: float, price: float) -> dict:
        """Envía una orden Limit (Maker) en Spot."""
        raw_symbol = symbol.replace("/", "")
        params = {
            'symbol': raw_symbol,
            'side': side.upper(),
            'type': 'LIMIT',
            'timeInForce': 'GTC', # Good-Til-Canceled (Spot testnet no siempre soporta GTX Post-Only)
            'quantity': str(qty),
            'price': str(price)
        }
        order = self._safe_api_call(self.exchange.privatePostOrder, params)
        
        if order == "UNKNOWN_STATE":
            print(f"[ALERTA MÁXIMA] Orden {side.upper()} en estado fantasma. Detén envíos y consulta fetch_open_orders.")
            return None
        elif order:
            print(f"[EXITO] Orden Limit ({side.upper()}) enviada: {qty} {symbol} a ${price}")
            return order
        return None
            
    def set_leverage(self, symbol: str, leverage: int):
        """Ajusta el apalancamiento para el par específico."""
        # Mercado Spot no usa apalancamiento de futuros.
        print(f"Modo Spot activo: Apalancamiento ignorado.")
        return None

if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 5/10: Gateway Binance API")
    print("---------------------------------------------------------")
    
    gateway = BinanceFuturesGateway(use_testnet=True)
    
    print("Consultando saldo en cuenta de Futuros...")
    saldo = gateway.check_connection_and_balance()
    print(f"Saldo Actual: ${saldo:.2f} USDT\n")
    
    symbol = "SOL/USDT"
    print(f"Descargando Libro de Órdenes (LOB) para {symbol}...")
    lob_data = gateway.fetch_limit_order_book(symbol)
    
    if lob_data:
        print(f"  Mejor Bid: {lob_data['bid_vol']} SOL @ ${lob_data['bid_price']}")
        print(f"  Mejor Ask: {lob_data['ask_vol']} SOL @ ${lob_data['ask_price']}\n")
    else:
        print("No se pudo obtener el LOB (revisa tus API Keys o red).\n")
