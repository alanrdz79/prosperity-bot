###### **1\. OBJETIVO**

Evaluar desde la microestructura, la teoría de colas y la ingeniería cuantitativa de **PROSPERITY** la viabilidad de fragmentar la operativa semanal en **3 bots o instancias especializadas por sesión** (de lunes a viernes), concentrando la actividad en ventanas de alta liquidez e impacto:

> 1. **El Gran Solapamiento:** Londres / Nueva York (13:00 a 17:00 UTC).  
> 2. **Apertura y Cierre de Wall Street:** Apertura de contado y rebalanceo de cierre (14:30 y 20:00 UTC).  
> 3. **Apertura Asiática:** Tokio / Hong Kong / Singapur (00:00 a 02:00 UTC).

###### **2\. ESTADO ACTUAL**

Anteriormente se descartó la operativa ininterrumpida 24/7 sin filtros debido a que los periodos de mercado muerto o compresión con bajo volumen generan rupturas falsas, ensanchan los spreads relativos y aumentan el riesgo de selección adversa (*toxic order flow*). Además, se verificó que la fricción acumulada por comisiones y deslizamiento (*slippage*) canibaliza el retorno si el sistema sobreopera en zonas de bajo volumen.

###### **3\. PROBLEMA**

> 1. **Riesgo de Sobreposición de Inventario:** Si el "Bot 1" (Solapamiento) y el "Bot 2" (Wall Street) operan en simultáneo entre las 14:30 y las 17:00 UTC sobre el mismo activo (ej. SOL/USDT o BTC/USDT), ambos pueden emitir señales en la misma dirección, duplicando involuntariamente el apalancamiento global y violando los límites de margen del Risk Engine.  
> 2. **Asimetría de Microestructura entre Sesiones:** La dinámica del libro de órdenes no es idéntica en Asia que en Nueva York. Intentar usar la misma calibración de indicadores (ej. ATR, bandas o umbral de RSI) para la sesión asiática y la apertura de Wall Street generará falsas activaciones: lo que en Asia es una ruptura estadística válida, en Nueva York es simple ruido de baja frecuencia absorbido por creadores de mercado.  
> 3. **Peligro de Fugas de Estado y Conflictos de Órdenes:** Múltiples scripts independientes enviando órdenes a Binance para la misma cuenta pueden colisionar en la gestión de las órdenes de contingencia (reduceOnly, Take Profit y Stop Loss nativos).

###### **4\. ANÁLISIS ARQUITECTÓNICO Y DE MICROESTRUCTURA**

La división por ventanas horarias de lunes a viernes es cualitativamente superior a un bucle ciego de 24 horas, siempre que cada ventana responda a su régimen de liquidez real:

  00:00 UTC            02:00 UTC     13:00 UTC           17:00 UTC   20:00 UTC  
      │                    │             │                   │           │  
      ▼                    ▼             ▼                   ▼           ▼  
┌────────────────────────────┐         ┌───────────────────────────┐   ┌───────────┐  
│     VENTANA ASIÁTICA       │         │    GRAN SOLAPAMIENTO      │   │ CIERRE NY │  
│   (Hong Kong / Singapur)   │         │     (Londres / NY)        │   │(Rebalance)│  
├────────────────────────────┤         ├───────────────────────────┤   ├───────────┤  
│ • Menor volumen global     │         │ • Volumen institucional   │   │ • Ajustes │  
│ • Reversión a la media     │         │ • Rupturas direccionales  │   │   finales │  
│ • Rango / Spreads estables │         │ • Flujo agresivo ETF      │   │ • MOC     │  
└────────────────────────────┘         └───────────────────────────┘   └───────────┘

### **A. Ventana 1: El Gran Solapamiento Londres / Nueva York (13:00 – 17:00 UTC)**

* **Dinámica:** Concentra más del 50% del volumen negociado en derivados cripto y divisas mayores. El libro de órdenes muestra una profundidad densa (Nivel 2/3).  
* **Comportamiento Óptimo:** **Estrategias de Momentum / Ruptura (Breakout)**. Cuando el precio rompe una zona de consolidación con volumen de ETF o futuros institucionales, la inercia suele sostenerse durante varios minutos, permitiendo que un Take Profit del \+2.5% a \+3.5% se alcance con rapidez antes de que ocurra una reversión.

### **B. Ventana 2: Apertura y Cierre de Wall Street (14:30 y 20:00 UTC)**

* **Dinámica:** A las 14:30 UTC abren los mercados de renta variable en EE. UU., provocando una inyección violenta de volatilidad y un aumento abrupto en la métrica VPIN (toxicidad de flujo). A las 20:00 UTC (16:00 EST) se ejecuta el *Market-On-Close* (MOC), donde los fondos institucionales rebalancean carteras.  
* **Comportamiento Óptimo:** **Filtro de Ruptura Confirmada o Espera de 15 Minutos.** Operar exactamente en el segundo de apertura (14:30:00 UTC) suele activar stops debido a barridos bidireccionales de liquidez (mechas largas). La ventana más limpia ocurre entre **14:45 y 16:30 UTC**.

### **C. Ventana 3: Apertura Asiática (00:00 – 02:00 UTC)**

* **Dinámica:** La liquidez total en el par SOL/USDT y BTC/USDT es sensiblemente inferior a la sesión americana. Las instituciones occidentales están fuera de mercado.  
* **Comportamiento Óptimo:** **Estrategias de Reversión a la Media (Mean Reversion)**. Salvo que ocurra una noticia macroeconómica o regulatoria nocturna, los intentos de ruptura suelen fallar y el precio tiende a rebotar dentro de los límites del rango previo.

###### **5\. COMPARATIVA DE ARQUITECTURA: 3 SCRIPTS SEPARADOS VS. 1 MOTOR MULTI-RÉGIMEN**

| Criterio | 3 Bots/Scripts Separados | 1 Orquestador Modular (PROSPERITY) |
| :---- | :---- | :---- |
| **Control de Margen Global** | Nulo; cada script ignora el balance de los otros. | Centralizado en el GlobalRiskManager. |
| **Colisiones de Órdenes** | Alto riesgo de emitir señales opuestas simultáneas. | Cola de despacho FIFO con bloqueo de activo único. |
| **Uso de Recursos** | 3 conexiones WebSocket redundantes a Binance. | 1 conexión compartida mediante MarketStream. |
| **Transición de Turnos** | Riego si una posición queda abierta al expirar la ventana. | Manejo persistente del trade hasta su cierre natural. |

###### **6\. IMPACTO**

* **Eliminación del Sobreoperar en Horas Muertas:** Limitar la operativa a estas tres ventanas reduce el tiempo de exposición a mercado de 24 horas a aproximadamente **8 a 9 horas diarias netas**, evitando los periodos de baja liquidez donde los falsos rompimientos degradan la cuenta.  
* **Control de Exposición:** Al no solapar bots en scripts aislados, el capital disponible no se diluye en márgenes duplicados.

###### **7\. SOLUCIÓN PROPUESTA PARA PROSPERITY**

En lugar de levantar 3 procesos de Python separados que compitan entre sí por la API key de Binance, se implementa un **Orquestador de Sesiones (SessionScheduler)** dentro de la capa decision/ de PROSPERITY.

> 1. El orquestador evalúa en tiempo real la hora actual en **UTC**.  
> 2. Si la hora se encuentra dentro de una ventana activa, selecciona y despierta el perfil de estrategia correspondiente:  
   * **13:00 a 17:00 UTC:** BreakoutMomentumStrategy (Impulso fuerte).  
   * **14:30 y 20:00 UTC:** HighVolatilityGuard (Filtro anti-mechas).  
   * **00:00 a 02:00 UTC:** MeanReversionStrategy (Rebote en bandas).  
> 3. **Regla de Posesión Abierta (Handover Rule):** Si el reloj marca el final de la ventana pero hay una posición abierta con sus órdenes condicionales puestas en Binance, el sistema no fuerza un cierre a mercado: delega la custodia al motor de salida hasta que el TP o SL se completen de manera natural en el exchange.

###### **8\. FLUJO DE DATOS**

\[Reloj del Sistema (UTC)\] ──► \[SessionScheduler (Lunes a Viernes)\]  
                                        │  
           ┌────────────────────────────┼────────────────────────────┐  
           ▼ (00:00 \- 02:00 UTC)        ▼ (13:00 \- 17:00 UTC)        ▼ (Fuera de Rango / Fin de Semana)  
  \[Modo: Reversión Asia\]      \[Modo: Impulso Solapamiento\]       \[Modo: SLEEP / IDLE\]  
           │                            │                            │  
           └────────────────────────────┼────────────────────────────┘  
                                        ▼  
                           \[DecisionEngine: Evaluador\]  
                                        │  
                                        ▼  
                     \[GlobalRiskManager: Límite Diario / DLD\]  
                                        │  
                                        ▼  
                         \[BinanceFuturesAdapter: CCXT\]

###### **9\. COMPONENTES AFECTADOS**

* core/config/session\_config.py: Definición formal de las franjas horarias UTC y días operativos.  
* decision/session\_scheduler.py: Módulo que activa y desactiva las estrategias según la sesión activa.  
* risk/risk\_manager.py: Supervisión del saldo y conteo de pérdidas con reset al final de la jornada de Nueva York.

###### **10\. RIESGOS**

* **Transición de Horario de Verano (DST):** Estados Unidos y Europa cambian de horario de verano en semanas distintas de marzo y octubre/noviembre, desplazando el solapamiento UTC en una hora temporalmente.  
* **Gaps de Apertura:** La apertura asiática del domingo por la noche (lunes en Asia) suele presentar vacíos de liquidez (*slippage* en mercado). Se debe programar el inicio formal los lunes a las 00:00 UTC.

###### **11\. IMPLEMENTACIÓN**

El siguiente módulo implementa el despachador de sesiones sincronizado con UTC, listo para ser integrado en el bucle principal de PROSPERITY:

Python  
\# decision/session\_scheduler.py  
from datetime import datetime, timezone  
from typing import Tuple, Optional

class SessionScheduler:  
    """  
    Controlador temporal de sesiones institucionales para PROSPERITY.  
    Determina qué perfil de estrategia debe estar activo en función del reloj UTC.  
    """  
    def \_\_init\_\_(self):  
        \# Definición de ventanas horarias en UTC (Lunes=0 a Viernes=4)  
        self.VENTANA\_ASIA \= (0, 2)         \# 00:00 a 02:00 UTC (Apertura Tokio/HK/Singapur)  
        self.VENTANA\_SOLAPAMIENTO \= (13, 17) \# 13:00 a 17:00 UTC (Pico Londres/NY y Wall St)  
        self.HORA\_CIERRE\_NY \= 20            \# 20:00 UTC (Rebalanceo Wall Street)

    def get\_active\_session(self) \-\> Tuple\[bool, Optional\[str\], str\]:  
        """  
        Evalúa el estado del mercado según el día y la hora UTC.  
        Retorna: (esta\_activo, nombre\_estrategia, descripcion)  
        """  
        ahora\_utc \= datetime.now(timezone.utc)  
        dia\_semana \= ahora\_utc.weekday() \# 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo  
        hora \= ahora\_utc.hour  
        minuto \= ahora\_utc.minute

        \# 1\. Filtro estricto de fin de semana (Cierre viernes 21:00 UTC hasta domingo 23:59 UTC)  
        if dia\_semana \== 5 or (dia\_semana \== 4 and hora \>= 21) or (dia\_semana \== 6 and hora \< 23):  
            return False, None, "Fin de semana: Baja liquidez institucional. Mercado suspendido."

        \# 2\. Ventana: Apertura Asiática (00:00 a 02:00 UTC)  
        if self.VENTANA\_ASIA\[0\] \<= hora \< self.VENTANA\_ASIA\[1\]:  
            return True, "MEAN\_REVERSION\_ASIA", f"Sesión Asiática ({ahora\_utc.strftime('%H:%M')} UTC): Rango y rebotes."

        \# 3\. Ventana: Gran Solapamiento Londres / Nueva York (13:00 a 17:00 UTC)  
        if self.VENTANA\_SOLAPAMIENTO\[0\] \<= hora \< self.VENTANA\_SOLAPAMIENTO\[1\]:  
            if hora \== 14 and minuto \< 45:  
                \# Primeros 15 min de Wall Street: alta toxicidad  
                return False, None, "Apertura Wall Street (14:30 \- 14:45 UTC): Pausa por volatilidad tóxica."  
            return True, "BREAKOUT\_MOMENTUM\_NY", f"Gran Solapamiento ({ahora\_utc.strftime('%H:%M')} UTC): Impulso direccional."

        \# 4\. Ventana: Cierre de Wall Street (20:00 a 20:30 UTC)  
        if hora \== self.HORA\_CIERRE\_NY and minuto \<= 30:  
            return True, "REBALANCE\_CLOSE\_NY", f"Cierre Wall Street ({ahora\_utc.strftime('%H:%M')} UTC): Flujo institucional de cierre."

        return False, None, f"Fuera de ventanas óptimas ({ahora\_utc.strftime('%H:%M')} UTC). Esperando volumen institucional."

\# Ejemplo de prueba de verificación  
if \_\_name\_\_ \== "\_\_main\_\_":  
    scheduler \= SessionScheduler()  
    activo, estrategia, desc \= scheduler.get\_active\_session()  
    print(f"Estado Activo: {activo}")  
    print(f"Estrategia Asignada: {estrategia}")  
    print(f"Detalle: {desc}")

###### **12\. PRUEBAS**

> 1. **Prueba de Transición de Sesión:** Simular marcas temporales a las 01:15 UTC, 14:35 UTC y 18:00 UTC para comprobar que el despachador retorne respectivamente MEAN\_REVERSION\_ASIA, bloqueo por toxicidad y estado inactivo (False).  
> 2. **Prueba de Persistencia en Traspaso:** Verificar que si una orden se ejecuta a las 16:55 UTC, el sistema continúe monitoreando el cierre a las 17:05 UTC sin abortar el trade forzosamente.

###### **13\. ESCALABILIDAD**

Al centralizar las sesiones en este despachador, no requieres administrar 3 procesos independientes en el sistema operativo ni pagar costos adicionales de CPU en tu máquina o servidor: un único hilo ligero de Python ejecuta el ciclo y selecciona la estrategia matemáticamente alineada con el horario vigente\[cite: 1\].

###### **14\. SIGUIENTE PASO**

¿Deseas que incorporemos este SessionScheduler dentro del bucle de ejecución de Binance Futures para que el bot solo abra posiciones durante estas franjas institucionales exactas de lunes a viernes\[cite: 1, 4\]?