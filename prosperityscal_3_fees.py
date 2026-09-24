"""
prosperityscal_3_fees.py - Módulo 3 de 10: Análisis de Comisiones y Break-Even
Proyecto CONTINUITY - Scalping Automatizado

Este módulo incorpora la realidad del mercado: las comisiones de Binance.
Dado que la estrategia de scalping buscará abrir muchísimas operaciones por 
pequeños movimientos, el impacto de las tarifas (Fees) apalancadas es crítico.

Especificaciones Binance USDⓈ-M Futures:
- Maker (Orden Límite): 0.02%
- Taker (Orden de Mercado): 0.05%
- Descuento BNB: 10% de reducción en comisiones.
Nota: Las comisiones se cobran sobre el Tamaño Nocional (Margen * Apalancamiento).
"""

class FeeCalculator:
    def __init__(self, use_bnb_discount: bool = True):
        # Tarifas base de Binance Futuros USDⓈ-M
        self.base_maker_fee = 0.0002  # 0.02%
        self.base_taker_fee = 0.0005  # 0.05%
        
        # Aplicación de descuento si se usa BNB para pagar comisiones
        self.discount = 0.90 if use_bnb_discount else 1.0
        
        self.maker_fee = self.base_maker_fee * self.discount
        self.taker_fee = self.base_taker_fee * self.discount

    def calculate_round_trip_fee(self, notional_size_usd: float, entry_is_maker: bool = True, exit_is_maker: bool = True) -> float:
        """
        Calcula el costo total (ida y vuelta) de abrir y cerrar una posición.
        notional_size_usd = margen_inicial * apalancamiento
        """
        # Comisión de entrada
        entry_fee_rate = self.maker_fee if entry_is_maker else self.taker_fee
        entry_fee_cost = notional_size_usd * entry_fee_rate
        
        # Comisión de salida (asumiendo que el tamaño de salida es el mismo)
        exit_fee_rate = self.maker_fee if exit_is_maker else self.taker_fee
        exit_fee_cost = notional_size_usd * exit_fee_rate
        
        return entry_fee_cost + exit_fee_cost

    def calculate_breakeven_distance(self, entry_price: float, leverage: int, entry_is_maker: bool = True, exit_is_maker: bool = True) -> float:
        """
        Calcula qué distancia porcentual debe moverse el activo a nuestro favor
        exclusivamente para cubrir el costo de las comisiones.
        """
        entry_fee_rate = self.maker_fee if entry_is_maker else self.taker_fee
        exit_fee_rate = self.maker_fee if exit_is_maker else self.taker_fee
        
        # El precio debe moverse el porcentaje total de comisiones cobradas
        total_fee_rate = entry_fee_rate + exit_fee_rate
        
        # Traducido a movimiento de precio absoluto
        breakeven_price_movement = entry_price * total_fee_rate
        
        return breakeven_price_movement

    def is_profitable_scalp(self, entry_price: float, target_price: float, notional_size_usd: float, entry_is_maker: bool = True, exit_is_maker: bool = True) -> dict:
        """
        Evalúa si el movimiento de precio (target) sobrepasa el costo de comisiones 
        y deja un margen de ganancia real (Net Profit).
        """
        gross_profit_per_unit = abs(target_price - entry_price)
        asset_quantity = notional_size_usd / entry_price
        gross_profit_usd = gross_profit_per_unit * asset_quantity
        
        total_fees = self.calculate_round_trip_fee(notional_size_usd, entry_is_maker, exit_is_maker)
        
        net_profit = gross_profit_usd - total_fees
        
        return {
            "gross_profit_usd": gross_profit_usd,
            "total_fees_usd": total_fees,
            "net_profit_usd": net_profit,
            "is_viable": net_profit > 0
        }

if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 3/10: Comisiones Binance")
    print("---------------------------------------------------------")
    
    fee_calc = FeeCalculator(use_bnb_discount=True) # Usamos BNB para el 10% de descuento
    
    # Supongamos una operación con $100 de nuestro capital a 10x de apalancamiento
    margen_inicial = 100.0
    apalancamiento = 10
    nocional_usd = margen_inicial * apalancamiento # $1,000 USD reales en el mercado
    
    print(f"Capital Invertido: ${margen_inicial} | Apalancamiento: {apalancamiento}x")
    print(f"Tamaño Nocional (sobre el que se cobra comisión): ${nocional_usd}\n")
    
    # Escenario 1: Entramos al mercado agresivamente (Taker) y salimos agresivamente (Taker)
    costo_taker_taker = fee_calc.calculate_round_trip_fee(nocional_usd, entry_is_maker=False, exit_is_maker=False)
    print(f"Comisión [Taker In -> Taker Out]: ${costo_taker_taker:.2f} USD")
    
    # Escenario 2: Bot Avellaneda-Stoikov entra con Límite (Maker) y sale con Límite (Maker)
    costo_maker_maker = fee_calc.calculate_round_trip_fee(nocional_usd, entry_is_maker=True, exit_is_maker=True)
    print(f"Comisión [Maker In -> Maker Out]: ${costo_maker_maker:.2f} USD (¡Ahorro masivo!)\n")
    
    # Análisis de un Scalp ultra-corto en BTC (Entrada 60000, Salida 60020 - mov. de 20 USD)
    entry_btc = 60000.0
    target_btc = 60020.0
    
    print("--- Análisis de Scalp Ultra-Corto en BTC ---")
    print(f"Entrada: ${entry_btc} | Salida Esperada: ${target_btc}")
    
    # Si somos impacientes (Taker)
    resultado_impaciente = fee_calc.is_profitable_scalp(entry_btc, target_btc, nocional_usd, False, False)
    print(f"Como TAKER: Ganancia bruta ${resultado_impaciente['gross_profit_usd']:.2f} - Comisiones ${resultado_impaciente['total_fees_usd']:.2f} = Neto ${resultado_impaciente['net_profit_usd']:.2f}")
    if not resultado_impaciente['is_viable']:
        print("   ❌ ¡Peligro! El scalp es perdedor por culpa de las comisiones Taker.")
        
    # Si el bot opera pasivamente (Maker)
    resultado_bot = fee_calc.is_profitable_scalp(entry_btc, target_btc, nocional_usd, True, True)
    print(f"Como MAKER (Bot): Ganancia bruta ${resultado_bot['gross_profit_usd']:.2f} - Comisiones ${resultado_bot['total_fees_usd']:.2f} = Neto ${resultado_bot['net_profit_usd']:.2f}")
    if resultado_bot['is_viable']:
         print("   ✅ El scalp es rentable. Aquí radica el poder del Market Making automático.")
