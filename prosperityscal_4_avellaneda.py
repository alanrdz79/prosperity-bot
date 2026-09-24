"""
prosperityscal_4_avellaneda.py - Módulo 4 de 10: Ejecución Estocástica (Avellaneda-Stoikov)
Proyecto CONTINUITY - Scalping Automatizado

Este módulo implementa las matemáticas fundacionales para la "Creación de Mercado" 
(Market Making) y la fijación de precios según el modelo estocástico de Avellaneda-Stoikov.

Dado que en criptomonedas (como Binance) el mercado es 24/7 y no tiene cierre (T - t = 0 asintótico),
se aplica una aproximación heurística donde el tiempo se neutraliza y la gestión 
depende de la volatilidad y el riesgo de inventario.

El bot calculará:
1. Precio de Reserva (Reservation Price): Hacia dónde debe sesgar sus cotizaciones
   dependiendo de qué tanto inventario acumulado tiene (riesgo direccional).
2. Diferencial Óptimo (Optimal Spread): A qué distancia colocar las órdenes de 
   Bid y Ask para maximizar la probabilidad de captura protegiéndose de la selección adversa.
"""

import math

class AvellanedaStoikovModel:
    def __init__(self, risk_aversion_gamma: float = 0.1, order_book_density_kappa: float = 1.5):
        """
        :param risk_aversion_gamma: (gamma) Nivel de aversión al riesgo del inventario.
                                    Valores más altos hacen que el bot sea más agresivo
                                    deshaciéndose del inventario rápidamente.
        :param order_book_density_kappa: (kappa) Probabilidad de llenado de órdenes. 
                                         Representa la liquidez/densidad del mercado.
        """
        self.gamma = risk_aversion_gamma
        self.kappa = order_book_density_kappa

    def calculate_reservation_price(self, mid_price: float, inventory_qty: float, volatility: float) -> float:
        """
        Calcula el 'Reservation Price' ajustando el mid-price por el riesgo de inventario acumulado.
        Si tienes mucho inventario (Long), el precio de reserva baja, forzando a tus órdenes 
        a colocarse más abajo para vender rápido y no comprar más.
        """
        # Fórmula adaptada para cripto (horizonte infinito temporal T-t = 1)
        # r = s - q * gamma * sigma^2
        variance = volatility ** 2
        reservation_price = mid_price - (inventory_qty * self.gamma * variance)
        
        return reservation_price

    def calculate_optimal_spread(self, volatility: float) -> float:
        """
        Calcula la separación total matemática (Spread Óptimo) entre el Bid y el Ask.
        A mayor volatilidad, el spread se ensancha automáticamente para absorber el choque.
        """
        variance = volatility ** 2
        
        # Componente de compensación por riesgo + componente de interacción con liquidez
        # spread = gamma * sigma^2 + (2/gamma) * ln(1 + gamma/kappa)
        risk_premium = self.gamma * variance
        liquidity_premium = (2 / self.gamma) * math.log(1 + (self.gamma / self.kappa))
        
        optimal_spread = risk_premium + liquidity_premium
        return optimal_spread

    def get_optimal_quotes(self, mid_price: float, inventory_qty: float, volatility: float) -> dict:
        """
        Devuelve el nivel exacto de precio en el que colocar la orden Límite de Compra (Bid)
        y la orden Límite de Venta (Ask) usando el precio de reserva.
        """
        reservation_price = self.calculate_reservation_price(mid_price, inventory_qty, volatility)
        optimal_spread = self.calculate_optimal_spread(volatility)
        
        # Cotizaciones simétricas alrededor del precio de reserva (no del mid-price)
        optimal_bid = reservation_price - (optimal_spread / 2)
        optimal_ask = reservation_price + (optimal_spread / 2)
        
        return {
            "mid_price": mid_price,
            "reservation_price": reservation_price,
            "optimal_spread": optimal_spread,
            "optimal_bid": optimal_bid,
            "optimal_ask": optimal_ask,
            "inventory_bias": reservation_price - mid_price
        }

if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 4/10: Avellaneda-Stoikov")
    print(" Mercado Objetivo: SOL/USDT")
    print("---------------------------------------------------------")
    
    # Parámetros del modelo
    gamma = 0.1 # Aversión al riesgo
    kappa = 1.5 # Liquidez del LOB
    volatility = 2.0 # Volatilidad estimada (desviación del precio a corto plazo)
    
    model = AvellanedaStoikovModel(risk_aversion_gamma=gamma, order_book_density_kappa=kappa)
    
    mid_p = 150.0 # Precio actual de SOL
    
    # Simulación 1: Inventario en 0 (Bot neutral)
    print("\n[Escenario 1] Inventario Neutral (0 SOL acumulados):")
    quotes_neutral = model.get_optimal_quotes(mid_p, inventory_qty=0, volatility=volatility)
    print(f"  Mid-Price: ${quotes_neutral['mid_price']:.2f} | Reservation Price: ${quotes_neutral['reservation_price']:.2f}")
    print(f"  Colocar COMPRA (Bid) en: ${quotes_neutral['optimal_bid']:.2f}")
    print(f"  Colocar VENTA (Ask) en:  ${quotes_neutral['optimal_ask']:.2f}")
    
    # Simulación 2: El bot ha acumulado muchas compras y tiene sobrexposición (Inventario = +10 SOL)
    print("\n[Escenario 2] Inventario Peligroso (+10 SOL comprados):")
    quotes_long = model.get_optimal_quotes(mid_p, inventory_qty=10, volatility=volatility)
    print(f"  Mid-Price: ${quotes_long['mid_price']:.2f} | Reservation Price: ${quotes_long['reservation_price']:.2f}")
    print(f"  Sesgo: El precio de reserva cayó ${quotes_long['inventory_bias']:.2f} dólares.")
    print(f"  Colocar COMPRA (Bid) en: ${quotes_long['optimal_bid']:.2f} (Se aleja para NO comprar más)")
    print(f"  Colocar VENTA (Ask) en:  ${quotes_long['optimal_ask']:.2f} (Se acerca al precio actual para vender rápido y liquidar inventario)")

    # Simulación 3: Choque de Volatilidad (Volatilidad pasa de 2.0 a 6.0)
    print("\n[Escenario 3] Aumento brusco de Volatilidad (Inventario 0, Volatilidad = 6.0):")
    quotes_vol = model.get_optimal_quotes(mid_p, inventory_qty=0, volatility=6.0)
    print(f"  Spread Óptimo original: ${quotes_neutral['optimal_spread']:.2f}")
    print(f"  Spread Óptimo ajustado por volatilidad: ${quotes_vol['optimal_spread']:.2f}")
    print("  (El bot ensancha su red de seguridad automáticamente para absorber el choque de mercado)")
