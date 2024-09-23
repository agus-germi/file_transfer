import signal
import sys
import os
import logging

def limpiar_recursos(signum, frame):
    print(f"Recibiendo señal {signum}, limpiando recursos...")
    sys.exit(0)  # Salgo del programa con código 0 (éxito)

def setup_signal_handling():
    signal.signal(signal.SIGINT, limpiar_recursos)
    signal.signal(signal.SIGTERM, limpiar_recursos)
    if os.name != "nt":
        signal.signal(signal.SIGQUIT, limpiar_recursos)
        signal.signal(signal.SIGHUP, limpiar_recursos)