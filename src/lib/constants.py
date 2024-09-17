import struct


TIMEOUT = 2  # Timeout in seconds
MAX_RETRIES = 3 # Numero maximo de reintentos


# Constants related to UDP Header
HEADER_FORMAT = '!B I I I'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

HOST = 'localhost'
PORT = 8088