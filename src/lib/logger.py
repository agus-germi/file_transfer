import logging


def setup_logger(verbose=False, quiet=False):
    """Configures the logger based on verbosity options."""
    logger = logging.getLogger("file_transfer")
    handler = logging.StreamHandler()

    # Define the logging format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    if verbose:
        logger.setLevel(logging.DEBUG)  
    elif quiet:
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.INFO)  

    return logger
