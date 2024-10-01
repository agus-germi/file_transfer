import logging

_logger = None

# lib/logger.py

import logging

_logger = None  # Variable para almacenar la instancia única del logger


def setup_logger(verbose=False, quiet=False):
    global _logger
    if _logger is None:
        # Configuración inicial del logger
        _logger = logging.getLogger("app_logger")
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        _logger.addHandler(handler)

        # Establecer el nivel de logging basado en los parámetros
        if verbose:
            _logger.setLevel(logging.DEBUG)
        elif quiet:
            _logger.setLevel(logging.ERROR)
        else:
            _logger.setLevel(logging.INFO)

    return _logger
