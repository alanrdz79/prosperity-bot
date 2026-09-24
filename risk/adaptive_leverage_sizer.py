class AdaptiveLeverageSizer:
    """
    Controlador adaptativo de apalancamiento multifactorial.
    Reduce el apalancamiento por capital, por volatilidad y por racha negativa.
    """
    def __init__(self, min_notional_floor: float = 5.5):
        self.min_notional_floor = min_notional_floor

    def calculate_leverage_and_sizing(
        self, 
        current_balance: float, 
        current_price: float, 
        atr_ratio: float = 1.0, 
        consecutive_losses: int = 0
    ) -> dict:
        """
        Calcula apalancamiento y tamaño de posición considerando:
        - Escalamiento por balance (DLD)
        - Penalización por alta volatilidad (atr_ratio > 1.5)
        - Freno de racha adversa (consecutive_losses >= 2)
        """
        # 1. Apalancamiento base por tramo de capital
        if current_balance < 30.0:
            base_leverage = 4
            base_margin_pct = 0.50
        elif current_balance < 100.0:
            base_leverage = 3
            base_margin_pct = 0.35
        elif current_balance < 500.0:
            base_leverage = 2
            base_margin_pct = 0.25
        else:
            base_leverage = 1
            base_margin_pct = 0.15

        effective_leverage = base_leverage

        # 2. Reducción por volatilidad anómala
        if atr_ratio > 1.5:
            # Si el mercado está 50% más volátil de lo normal, recorta 1 escalón
            effective_leverage = max(1, effective_leverage - 1)

        # 3. Freno de mano por racha de pérdidas consecutivas
        margin_pct = base_margin_pct
        if consecutive_losses >= 2:
            # Corta la asignación de margen al 50% para frenar interés compuesto inverso
            margin_pct = margin_pct * 0.5

        # 4. Cálculo del valor nocional y validación de piso mínimo
        margin_to_use = current_balance * margin_pct
        notional_value = margin_to_use * effective_leverage

        # Garantizar que cumpla el piso de $5.5 USDT de Binance
        if notional_value < self.min_notional_floor:
            notional_value = self.min_notional_floor
            # Ajustar el margen necesario según el apalancamiento efectivo
            margin_to_use = notional_value / effective_leverage

        # Verificar si el margen requerido supera el balance disponible
        if margin_to_use > current_balance:
            raise ValueError("Saldo insuficiente para cumplir el tamaño mínimo de orden de Binance.")

        units = notional_value / current_price

        return {
            'leverage': int(effective_leverage),
            'margin_allocated': round(margin_to_use, 2),
            'notional_value': round(notional_value, 2),
            'units': units,
            'reason': (
                f"CapTier: x{base_leverage} | "
                f"VolPenalty: {'SÍ' if atr_ratio > 1.5 else 'NO'} | "
                f"LossPenalty: {'SÍ' if consecutive_losses >= 2 else 'NO'}"
            )
        }
