class DynamicLeverageSizer:
    """Gestiona el dimensionamiento y desescalado de apalancamiento."""
    
    @staticmethod
    def calculate_trade_parameters(balance: float, price: float):
        if balance < 30.0:
            leverage = 4        # Microcuenta: superar lote mínimo
            margin_pct = 0.50   # Margen de $5 a $15 USD
        elif balance < 100.0:
            leverage = 3
            margin_pct = 0.35
        elif balance < 500.0:
            leverage = 2
            margin_pct = 0.25
        else:
            leverage = 1        # Cuenta consolidada: preservación
            margin_pct = 0.15

        margin_used = balance * margin_pct
        notional_value = margin_used * leverage
        
        # Filtro estricto de mínimo nocional de Binance ($5 USDT)
        if notional_value < 5.0:
            notional_value = 5.0
            margin_used = notional_value / leverage

        units = notional_value / price
        return {
            'balance': balance,
            'leverage': leverage,
            'margin_used': round(margin_used, 2),
            'notional_value': round(notional_value, 2),
            'units': units
        }
