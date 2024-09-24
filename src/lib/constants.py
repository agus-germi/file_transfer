import struct

TIMEOUT = 0.02  # Timeout in seconds
MAX_RETRIES = 3  # Numero maximo de reintentos
WINDOW_SIZE = 5

HEADER_FORMAT = "!B I I I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FRAGMENT_SIZE = 1010


HOST = "10.0.0.1"
PORT = 8087

PATH = "file.txt"
STORAGE = "storage"
