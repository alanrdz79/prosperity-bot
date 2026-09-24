"""
prosperityscal_btc.py - Módulo 1 de 10: Dinámica Microestructural y Libro de Órdenes
Proyecto CONTINUITY - Scalping de Alta Frecuencia en BTC/USDT

Basado en la "Arquitectura Avanzada y Modelos Cuantitativos para Bots de Trading HFT",
este primer script (modelo en cascada) se encarga de las bases fundamentales:
- Lectura de la Microestructura (Limit Order Book).
- Cálculo de Order Flow Imbalance (OFI).
- Estimación del Micro-Precio.

Este módulo alimenta a los subsecuentes módulos de predicción y ejecución (ej. Avellaneda-Stoikov).
"""

import numpy as np

class MicrostructureAnalyzer:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol = symbol
        
        # Estado previo del LOB (Mejor Bid y Mejor Ask) para calcular OFI
        self.prev_bid_price = None
        self.prev_bid_vol = None
        self.prev_ask_price = None
        self.prev_ask_vol = None

    def calculate_ofi(self, bid_price: float, bid_vol: float, ask_price: float, ask_vol: float) -> float:
        """
        Calcula el Order Flow Imbalance (OFI) según el modelo de Cont et al.
        Mide el desequilibrio neto entre la oferta y la demanda en el extremo del libro.
        Un OFI positivo indica presión de compra, y un OFI negativo presión de venta.
        """
        # Si es el primer tick, solo inicializamos el estado
        if self.prev_bid_price is None:
            self._update_state(bid_price, bid_vol, ask_price, ask_vol)
            return 0.0

        # --- Contribución de la Demanda (Bid) ---
        if bid_price > self.prev_bid_price:
            # Nuevo nivel de precio superior, toda la liquidez es nueva
            e_bid = bid_vol
        elif bid_price == self.prev_bid_price:
            # Mismo nivel de precio, calculamos el delta de volumen
            e_bid = bid_vol - self.prev_bid_vol
        else:
            # Nivel de precio inferior, el volumen previo se consumió/canceló
            e_bid = -self.prev_bid_vol

        # --- Contribución de la Oferta (Ask) ---
        if ask_price > self.prev_ask_price:
            # Nivel de precio superior, el volumen previo se consumió/canceló
            e_ask = -self.prev_ask_vol
        elif ask_price == self.prev_ask_price:
            # Mismo nivel de precio, calculamos el delta de volumen
            e_ask = ask_vol - self.prev_ask_vol
        else:
            # Nuevo nivel de precio inferior, toda la liquidez es nueva
            e_ask = ask_vol

        # OFI Neto
        ofi = e_bid - e_ask
        
        # Actualizamos el estado para el siguiente tick
        self._update_state(bid_price, bid_vol, ask_price, ask_vol)
        return ofi

    def calculate_micro_price(self, bid_price: float, bid_vol: float, ask_price: float, ask_vol: float) -> float:
        """
        Calcula el Micro-Precio propuesto por Stoikov.
        A diferencia del Mid-Price tradicional, el Micro-Precio se ajusta probabilísticamente 
        basado en la profundidad y volumen del spread actual.
        """
        if (bid_vol + ask_vol) == 0:
            return (bid_price + ask_price) / 2.0  # Fallback a mid-price clásico en anomalías

        # P_micro = (V_ask * P_bid + V_bid * P_ask) / (V_bid + V_ask)
        micro_price = ((ask_vol * bid_price) + (bid_vol * ask_price)) / (bid_vol + ask_vol)
        return micro_price
    
    def _update_state(self, bid_price: float, bid_vol: float, ask_price: float, ask_vol: float):
        """Actualiza el estado interno de la memoria temporal del LOB."""
        self.prev_bid_price = bid_price
        self.prev_bid_vol = bid_vol
        self.prev_ask_price = ask_price
        self.prev_ask_vol = ask_vol


if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 1/10: Microestructura LOB")
    print(" Mercado Objetivo: BTC/USDT")
    print("---------------------------------------------------------")
    
    analyzer = MicrostructureAnalyzer(symbol="BTC/USDT")
    
    # 1. Simulación Inicial de Mercado Estático (Precios y volúmenes de BTC)
    bid_p, bid_v = 60000.00, 2.5
    ask_p, ask_v = 60000.10, 3.0
    ofi = analyzer.calculate_ofi(bid_p, bid_v, ask_p, ask_v)
    mp = analyzer.calculate_micro_price(bid_p, bid_v, ask_p, ask_v)
    mid_price = (bid_p + ask_p) / 2
    
    print(f"Tick 1 (Base):")
    print(f"  Bid: {bid_v}@{bid_p} | Ask: {ask_v}@{ask_p}")
    print(f"  Mid-Price: {mid_price:.4f} | Micro-Price: {mp:.4f} | OFI: {ofi}")
    
    # 2. Simulación de un Incremento de Demanda (Entrada de Compradores)
    # Aumenta el volumen en el Bid, indicando que hay interés comprador
    bid_p, bid_v = 60000.00, 8.5
    ask_p, ask_v = 60000.10, 1.2
    ofi = analyzer.calculate_ofi(bid_p, bid_v, ask_p, ask_v)
    mp = analyzer.calculate_micro_price(bid_p, bid_v, ask_p, ask_v)
    
    print(f"\nTick 2 (Aumento de Presión de Compra):")
    print(f"  Bid: {bid_v}@{bid_p} | Ask: {ask_v}@{ask_p}")
    print(f"  Micro-Price se desplaza hacia {mp:.4f} anticipando el alza | OFI: {ofi} (Presión Positiva)")

    # 3. Simulación de Consumo del LOB (Un comprador de mercado agresivo cruza el spread)
    # El Ask se consume y se mueve un nivel arriba.
    bid_p, bid_v = 60000.10, 1.5
    ask_p, ask_v = 60000.20, 5.0
    ofi = analyzer.calculate_ofi(bid_p, bid_v, ask_p, ask_v)
    mp = analyzer.calculate_micro_price(bid_p, bid_v, ask_p, ask_v)
    
    print(f"\nTick 3 (Ruptura del Nivel por Agresor - Desplazamiento de Precio):")
    print(f"  Bid: {bid_v}@{bid_p} | Ask: {ask_v}@{ask_p}")
    print(f"  Micro-Price: {mp:.4f} | OFI: {ofi} (Fuerte desequilibrio de la ráfaga)")
