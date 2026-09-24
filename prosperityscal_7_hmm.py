"""
prosperityscal_7_hmm.py - Módulo 7 de 10: Modelos Ocultos de Markov (HMM)
Proyecto CONTINUITY - Scalping Automatizado

Este módulo implementa el análisis metaanalítico del mercado usando 
Hidden Markov Models (HMM). 

El mercado no se comporta igual todo el tiempo. Un modelo de Scalping
o Market Making que funciona perfecto en un mercado lateral (rango) será
destruido en un mercado direccional tendencial (alta volatilidad).

El HMM observa variables visibles (retornos del precio, volatilidad, volumen)
y decodifica en qué "régimen oculto" se encuentra el mercado:
- Estado 0: Mercado Lateral (Rango, baja volatilidad). Ideal para Avellaneda-Stoikov.
- Estado 1: Mercado Tendencial (Alta volatilidad direccional). Peligro de selección adversa.

Requiere la instalación de la librería hmmlearn: `pip install hmmlearn`
"""

import numpy as np
import warnings

try:
    from hmmlearn import hmm
except ImportError:
    hmm = None
    print("[SISTEMA] Advertencia: La librería 'hmmlearn' no está instalada.")
    print("Para usar este módulo en producción, ejecuta: pip install hmmlearn")

class MarketRegimeDetector:
    def __init__(self, n_components: int = 2):
        """
        n_components define la cantidad de regímenes.
        Típicamente 2 (Lateral vs Tendencial) o 3 (Alcista, Bajista, Lateral).
        Usaremos 2 por simplicidad para el bot de Scalping.
        """
        self.n_components = n_components
        
        if hmm:
            # Inicializamos el modelo Gausiano HMM
            # covariance_type="full" permite capturar la estructura de correlación
            # completa entre nuestras variables (ej. Retorno vs Volumen)
            self.model = hmm.GaussianHMM(n_components=self.n_components, 
                                         covariance_type="full", 
                                         n_iter=1000)
            self.is_trained = False
        else:
            self.model = None

    def train_model(self, historical_data: np.ndarray):
        """
        historical_data: Un array 2D de numpy con la forma (muestras, características).
        Características típicas: [Retornos a 1 minuto, Volatilidad de los últimos 5 minutos, OFI].
        El algoritmo de Baum-Welch (EM) ajusta las probabilidades de transición.
        """
        if not self.model:
            return

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Entrenamos el modelo oculto
            self.model.fit(historical_data)
            self.is_trained = True
            print(f"[HMM] Modelo entrenado exitosamente con {len(historical_data)} observaciones.")

    def predict_current_regime(self, recent_data: np.ndarray) -> int:
        """
        Utiliza el algoritmo de Viterbi para decodificar la secuencia más probable
        del régimen actual basándose en los datos más recientes (ej. las últimas 10 velas de 1m).
        """
        if not self.is_trained or not self.model:
            # Si no hay modelo, asumimos un entorno seguro (Estado 0) por defecto
            return 0
            
        # Predice el estado oculto del último dato de la secuencia
        predicted_states = self.model.predict(recent_data)
        current_state = predicted_states[-1]
        
        return current_state

    def execute_regime_action(self, current_state: int):
        """
        Traduce la matemática del HMM en acciones directas para el Orquestador (Módulo 6).
        """
        if current_state == 0:
            print("[ACCIÓN] Régimen Detectado: LATERAL (Consolidación).")
            print(" -> Estrategia Óptima: Market Making Pasivo.")
            print(" -> El bot debe usar órdenes Límite a ambos lados (Avellaneda-Stoikov) para cobrar el spread.")
            return "MARKET_MAKING"
            
        elif current_state == 1:
            print("[ACCIÓN] Régimen Detectado: TENDENCIAL (Alta Volatilidad / Ruptura).")
            print(" -> Estrategia Óptima: Suspensión Pasiva o Scalping Direccional.")
            print(" -> ¡Peligro de Selección Adversa! Pausar órdenes Maker y operar a favor de la tendencia.")
            return "DIRECTIONAL_OR_PAUSE"

if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 7/10: HMM Market Regimes")
    print("---------------------------------------------------------")
    
    detector = MarketRegimeDetector(n_components=2)
    
    if hmm:
        # 1. Simulación de entrenamiento con datos ficticios
        # Columna 1: Retornos absolutos de precios de velas de 1 minuto
        # Columna 2: Varianza/Volatilidad
        # Filas 1 a 50: Mercado tranquilo. Filas 51 a 100: Mercado agresivo.
        calm_market = np.random.normal(loc=[0.01, 0.5], scale=[0.005, 0.1], size=(50, 2))
        trending_market = np.random.normal(loc=[0.15, 2.5], scale=[0.05, 0.5], size=(50, 2))
        
        # Concatenamos la historia para que el algoritmo aprenda los dos patrones ciegamente
        training_history = np.vstack([calm_market, trending_market])
        
        print("Entrenando el Filtro HMM con 100 minutos de historia...")
        detector.train_model(training_history)
        
        # 2. El Orquestador le inyecta las últimas 5 velas al modelo en tiempo real
        print("\nCaso A: Las últimas 5 velas de 1 minuto muestran poco movimiento.")
        recent_calm_data = np.random.normal(loc=[0.01, 0.5], scale=[0.005, 0.1], size=(5, 2))
        estado_a = detector.predict_current_regime(recent_calm_data)
        detector.execute_regime_action(estado_a)
        
        print("\nCaso B: De repente, el OFI se dispara y las velas muestran gran volatilidad.")
        recent_volatile_data = np.random.normal(loc=[0.16, 2.8], scale=[0.05, 0.5], size=(5, 2))
        estado_b = detector.predict_current_regime(recent_volatile_data)
        detector.execute_regime_action(estado_b)
    else:
        print("Instala hmmlearn para ejecutar la simulación de aprendizaje automático.")
