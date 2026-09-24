"""
prosperityscal_10_vpin.py - Módulo 10 de 10: Probabilidad de Trading Informado (VPIN)
Proyecto CONTINUITY - Scalping Automatizado

El modelo VPIN (Volume-Synchronized Probability of Informed Trading) es el 
escudo final del sistema. Detecta "Toxicidad en el Flujo de Órdenes".

Cuando participantes institucionales con información privilegiada o gran 
capital ("Ballenas") entran al mercado, consumen agresivamente la liquidez. 
Si el Market Maker (nuestro bot) provee liquidez pasiva en ese momento, 
sufrirá pérdidas masivas (Selección Adversa).

El VPIN no se basa en marcos de tiempo (velas), sino en "Buckets de Volumen",
asegurando que el análisis no se deforme por horas de baja actividad.
Si el VPIN supera un umbral crítico (ej. > 0.8), el bot activa un "Circuit Breaker"
y suspende el Market Making.
"""

import numpy as np

class VPINCalculator:
    def __init__(self, volume_bucket_size: float = 1000.0, num_buckets: int = 50):
        """
        :param volume_bucket_size: La cantidad fija de volumen que define un "Bucket" 
                                   (ej. 1000 SOL negociados).
        :param num_buckets: Tamaño de la muestra rodante (n) para calcular la probabilidad.
        """
        self.volume_bucket_size = volume_bucket_size
        self.num_buckets = num_buckets
        self.buckets = []
        
        # Estado actual del bucket que se está llenando
        self.current_bucket_buy_vol = 0.0
        self.current_bucket_sell_vol = 0.0

    def add_trade(self, trade_vol: float, is_buyer_maker: bool):
        """
        Ingesta de transacciones crudas de la red (Tick a Tick).
        Si is_buyer_maker es True, un TAKER vendió (Presión de Venta).
        Si is_buyer_maker es False, un TAKER compró (Presión de Compra).
        """
        # Clasificamos el volumen
        if is_buyer_maker:
            self.current_bucket_sell_vol += trade_vol
        else:
            self.current_bucket_buy_vol += trade_vol
            
        current_total = self.current_bucket_buy_vol + self.current_bucket_sell_vol
        
        # Si el bucket se llenó (alcanzó el volumen estático)
        if current_total >= self.volume_bucket_size:
            # Empaquetamos y guardamos el bucket
            self.buckets.append({
                "buy_vol": self.current_bucket_buy_vol,
                "sell_vol": self.current_bucket_sell_vol
            })
            
            # Mantenemos el tamaño de la ventana (n)
            if len(self.buckets) > self.num_buckets:
                self.buckets.pop(0)
                
            # Reiniciamos para el siguiente bucket
            self.current_bucket_buy_vol = 0.0
            self.current_bucket_sell_vol = 0.0

    def calculate_vpin(self) -> float:
        """
        Cálculo matemático del VPIN sobre la muestra de buckets sincronizados.
        Fórmula: Sumatoria(|Vol_Buy - Vol_Sell|) / (n * V)
        Devuelve un valor entre 0 y 1. 
        Cercano a 1 = Altamente Tóxico (Direccionalidad Extrema).
        """
        if len(self.buckets) < self.num_buckets:
            # No hay suficientes datos aún
            return 0.0
            
        total_imbalance = sum(abs(b["buy_vol"] - b["sell_vol"]) for b in self.buckets)
        total_volume_sample = self.num_buckets * self.volume_bucket_size
        
        vpin = total_imbalance / total_volume_sample
        return vpin

    def check_toxicity_alert(self, threshold: float = 0.75) -> bool:
        """Verifica si el VPIN ha superado la alerta de Toxicidad Institucional."""
        current_vpin = self.calculate_vpin()
        return current_vpin > threshold

if __name__ == "__main__":
    print("---------------------------------------------------------")
    print(" CONTINUITY PROJECT - Módulo 10/10: Análisis VPIN")
    print("---------------------------------------------------------")
    
    # Creamos un calculador que requiera 5 buckets pequeños para tener datos rápido
    vpin_monitor = VPINCalculator(volume_bucket_size=100.0, num_buckets=5)
    
    print("Simulación de Trades [Mercado Sano y Equilibrado]...")
    # Simulamos 5 buckets llenándose de forma equilibrada (50% compras, 50% ventas)
    for _ in range(5):
        vpin_monitor.add_trade(50.0, is_buyer_maker=False) # 50 Compras Taker
        vpin_monitor.add_trade(50.0, is_buyer_maker=True)  # 50 Ventas Taker
        
    vpin_sano = vpin_monitor.calculate_vpin()
    print(f"Lectura VPIN (0 a 1): {vpin_sano:.4f} -> El mercado está tranquilo.")
    
    print("\nSimulación de Trades [Ataque Institucional Tóxico]...")
    # De repente, entra una ballena a devorar liquidez (90% compras agresivas)
    for _ in range(5):
        vpin_monitor.add_trade(90.0, is_buyer_maker=False) # Fuerte Compra Taker
        vpin_monitor.add_trade(10.0, is_buyer_maker=True)  # Poca Venta Taker
        
    vpin_toxico = vpin_monitor.calculate_vpin()
    print(f"Lectura VPIN (0 a 1): {vpin_toxico:.4f} -> Desequilibrio direccional severo.")
    
    if vpin_monitor.check_toxicity_alert(threshold=0.70):
        print("\n[CIRCUIT BREAKER] [ALERTA] TOXICIDAD DETECTADA! [ALERTA]")
        print("El flujo está severamente manipulado. El bot apaga cotizaciones Maker para evitar ser atropellado.")
