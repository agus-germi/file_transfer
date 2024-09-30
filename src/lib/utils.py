import signal
import sys
import os


def limpiar_recursos(signum, frame):
    """Encargada de cerrar cuando se recibe un Control C, un kill pid en la consola
    o incluso  cuando se cierra la terminal."""
    print(f"Recibiendo señal {signum}, limpiando recursos...")
    sys.exit(0)  # Salgo del programa con código 0 (éxito)


def setup_signal_handling():
    """Funcion encargada de manejar las distintas funciones del Sistema operativo"""
    signal.signal(signal.SIGINT, limpiar_recursos)
    signal.signal(signal.SIGTERM, limpiar_recursos)
    if os.name != "nt": #Si el SO no es Windows
        signal.signal(signal.SIGQUIT, limpiar_recursos)
        signal.signal(signal.SIGHUP, limpiar_recursos)