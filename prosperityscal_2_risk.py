"""
prosperityscal_2_risk.py - Módulo 2 de 10: Gestión de Riesgo y Capital
Proyecto CONTINUITY - Scalping Automatizado

Este módulo integra los principios fundamentales de gestión de riesgo para operar en futuros:
- Margen Aislado (Isolated Margin) por operación.
- Apalancamiento controlado (default: 5x).
- Stop-Loss estricto para proteger capital (ej. arriesgar máximo 1% del capital).
- Ratio Riesgo/Beneficio (Risk/Reward) mínimo de 1:2.

Este módulo recibe las señales del Módulo 1 (Microestructura) y determina
si la operación cumple con las reglas de negocio y de qué tamaño debe ser.
"""

class RiskManager:
    def __init__(self, total_capital: float, max_risk_per_trade_pct: float = 0.01, 
                 leverage: int = 5, min_risk_reward_ratio: float = 2.0):
        self.total_capital = total_capital
        self.max_risk_per_trade_pct = max_risk_per_trade_pct # Por defecto 1%
        self.leverage = leverage
        self.min_risk_reward_ratio = min_risk_reward_ratio

    def calculate_position_size(self, entry_price: float, stop_loss_price: float) -> dict:
        """
        Calcula el tamaño de la posición basándose en la distancia al Stop-Loss
        y el riesgo máximo permitido de la cuenta.
        """
        if entry_price == stop_loss_price:
            raise ValueError("El precio de entrada no puede ser igual al Stop-Loss.")

        # Riesgo monetario máximo permitido para esta operación
        max_risk_usd = self.total_capital * self.max_risk_per_trade_pct

        # Distancia porcentual al Stop Loss
        stop_loss_distance_pct = abs(entry_price - stop_loss_price) / entry_price

        # Tamaño total de la posición (valor nocional en USD) para que si toca el SL,
        # solo se pierda el max_risk_usd
        # Posición_USD * stop_loss_distance_pct = max_risk_usd
        position_size_usd = max_risk_usd / stop_loss_distance_pct

        # Margen requerido (el dinero real que se bloquea de la cuenta usando apalancamiento)
        margin_required = position_size_usd / self.leverage

        # Tamaño de la posición en cantidad de criptomonedas (ej. cantidad de SOL o BTC)
        position_size_asset = position_size_usd / entry_price

        return {
            "max_risk_usd": max_risk_usd,
            "position_size_usd": position_size_usd,
            "margin_required_usd": margin_required,
            "position_size_asset": position_size_asset,
            "stop_loss_distance_pct": stop_loss_distance_pct * 100,
            "leverage_used": self.leverage,
            "margin_type": "ISOLATED"
        }

    def validate_trade_setup(self, entry_price: float, stop_loss_price: float, take_profit_price: float) -> bool:
        """
        Valida que la operación propuesta cumpla con el ratio Riesgo/Beneficio mínimo (1:2).
        """
        risk_distance = abs(entry_price - stop_loss_price)
        reward_distance = abs(take_profit_price - entry_price)

        if risk_distance == 0:
            return False

        rr_ratio = reward_distance / risk_distance
        return rr_ratio >= self.min_risk_reward_ratio

    def generate_trade_order(self, entry_price: float, stop_loss_price: float, take_profit_price: float):
        """
        Genera el bloque de parámetros finales de la orden si aprueba el filtro de riesgo.
        """
        if not self.validate_trade_setup(entry_price, stop_loss_price, take_profit_price):
            print("❌ Operación rechazada: No cumple con el Ratio Riesgo/Beneficio mínimo.")
            return None

        try:
            position_details = self.calculate_position_size(entry_price, stop_loss_price)
            
            # Verificación de capital: No podemos usar más margen del que tenemos
            if position_details["margin_required_usd"] > self.total_capital:
                 print("❌ Operación rechazada: Margen requerido supera el capital total.")
                 return None

            print("✅ Operación aprobada por el gestor de riesgo.")
            return {
                "entry_price": entry_price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "sizing": position_details
            }
        except Exception as e:
            print(f"❌ Error al calcular tamaño de posición: {e}")
            return None


if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 2/10: Gestión de Riesgo")
    print("---------------------------------------------------------")
    
    # Capital inicial de $1,000 USD
    # Apalancamiento 5x, Riesgo máximo 1% por operación
    risk_manager = RiskManager(total_capital=1000.0, max_risk_per_trade_pct=0.01, leverage=5)
    
    # Simulación 1: Trade de Scalping en BTC (Largo/Compra)
    print("\n--- Simulación 1: Scalping BTC/USDT (Largo) ---")
    entry_btc = 60000.0
    sl_btc = 59700.0   # Stop Loss a $300 de distancia (0.5%)
    tp_btc = 60600.0   # Take Profit a $600 de distancia (1.0%) -> Ratio 1:2
    
    orden_btc = risk_manager.generate_trade_order(entry_btc, sl_btc, tp_btc)
    if orden_btc:
        print(f"Precio Entrada: ${orden_btc['entry_price']}")
        print(f"Stop-Loss: ${orden_btc['stop_loss']} | Take-Profit: ${orden_btc['take_profit']}")
        print(f"Tamaño de la posición: ${orden_btc['sizing']['position_size_usd']:.2f} USD ({orden_btc['sizing']['position_size_asset']:.4f} BTC)")
        print(f"Margen Aislado Requerido (a {orden_btc['sizing']['leverage_used']}x): ${orden_btc['sizing']['margin_required_usd']:.2f} USD")
        print(f"Riesgo Monetario si toca SL: ${orden_btc['sizing']['max_risk_usd']:.2f} USD")

    # Simulación 2: Trade rechazado por mal Ratio Riesgo/Beneficio
    print("\n--- Simulación 2: Trade Malo en SOL/USDT (Largo) ---")
    entry_sol = 150.0
    sl_sol = 145.0     # Riesgo de $5
    tp_sol = 153.0     # Beneficio de $3 -> Ratio menor a 1:2
    
    orden_sol = risk_manager.generate_trade_order(entry_sol, sl_sol, tp_sol)
