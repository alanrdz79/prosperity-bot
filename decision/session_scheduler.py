from datetime import datetime, timezone
from typing import Tuple, Optional
from core.config.session_config import VENTANA_ASIA, VENTANA_SOLAPAMIENTO, HORA_CIERRE_NY

class SessionScheduler:
    """
    Controlador temporal de sesiones institucionales para PROSPERITY.
    Determina qué perfil de estrategia debe estar activo en función del reloj UTC.
    """
    def __init__(self):
        self.VENTANA_ASIA = VENTANA_ASIA
        self.VENTANA_SOLAPAMIENTO = VENTANA_SOLAPAMIENTO
        self.HORA_CIERRE_NY = HORA_CIERRE_NY

    def get_active_session(self) -> Tuple[bool, Optional[str], str]:
        """
        Evalúa el estado del mercado según el día y la hora UTC.
        Retorna: (esta_activo, nombre_estrategia, descripcion)
        """
        ahora_utc = datetime.now(timezone.utc)
        dia_semana = ahora_utc.weekday() # 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo
        hora = ahora_utc.hour
        minuto = ahora_utc.minute

        # 1. Filtro estricto de fin de semana (Cierre viernes 21:00 UTC hasta domingo 23:59 UTC)
        if dia_semana == 5 or (dia_semana == 4 and hora >= 21) or (dia_semana == 6 and hora < 23):
            return False, None, "Fin de semana: Baja liquidez institucional. Mercado suspendido."

        # 2. Ventana: Apertura Asiática (00:00 a 02:00 UTC)
        if self.VENTANA_ASIA[0] <= hora < self.VENTANA_ASIA[1]:
            return True, "MEAN_REVERSION_ASIA", f"Sesión Asiática ({ahora_utc.strftime('%H:%M')} UTC): Rango y rebotes."

        # 3. Ventana: Gran Solapamiento Londres / Nueva York (13:00 a 17:00 UTC)
        if self.VENTANA_SOLAPAMIENTO[0] <= hora < self.VENTANA_SOLAPAMIENTO[1]:
            if hora == 14 and minuto < 45:
                # Primeros 15 min de Wall Street: alta toxicidad
                return False, None, "Apertura Wall Street (14:30 - 14:45 UTC): Pausa por volatilidad tóxica."
            return True, "BREAKOUT_MOMENTUM_NY", f"Gran Solapamiento ({ahora_utc.strftime('%H:%M')} UTC): Impulso direccional."

        # 4. Ventana: Cierre de Wall Street (20:00 a 20:30 UTC)
        if hora == self.HORA_CIERRE_NY and minuto <= 30:
            return True, "REBALANCE_CLOSE_NY", f"Cierre Wall Street ({ahora_utc.strftime('%H:%M')} UTC): Flujo institucional de cierre."

        return False, None, f"Fuera de ventanas óptimas ({ahora_utc.strftime('%H:%M')} UTC). Esperando volumen institucional."
