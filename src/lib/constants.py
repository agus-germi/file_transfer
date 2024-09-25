import struct


TIMEOUT = 0.5  # Timeout in seconds
MAX_RETRIES = 3 # Numero maximo de reintentos
WINDOW_SIZE = 5 

HEADER_FORMAT = '!B I I'

HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FRAGMENT_SIZE = 1024
PACKAGE_SIZE = HEADER_SIZE + FRAGMENT_SIZE


HOST = "10.0.0.1"
PORT = 8087

PATH = "file.txt"
STORAGE = "storage"
