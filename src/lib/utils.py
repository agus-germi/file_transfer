import signal
import sys
import os

from lib.logger import setup_logger
from lib.parser import parse_upload_args

# TODO: poner todo esto en otro lado
args = parse_upload_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)


def limpiar_recursos(signum, frame):
    logger.info(f"Recibiendo señal {signum}, limpiando recursos...")
    sys.exit(0)  # Salgo del programa con código 0 (éxito)


def setup_signal_handling():
    signal.signal(signal.SIGINT, limpiar_recursos)
    signal.signal(signal.SIGTERM, limpiar_recursos)
    if os.name != "nt":
        signal.signal(signal.SIGQUIT, limpiar_recursos)
        signal.signal(signal.SIGHUP, limpiar_recursos)
