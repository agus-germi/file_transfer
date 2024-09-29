import struct



TIMEOUT = 0.2  # Timeout in seconds
MAX_RETRIES = 10 # Numero maximo de reintentos
SACK_WINDOW_SIZE = 8
SEND_WINDOW_SIZE = SACK_WINDOW_SIZE *2

HEADER_FORMAT = '!B I I'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FRAGMENT_SIZE = 4096 * 2
PACKAGE_SIZE = HEADER_SIZE + FRAGMENT_SIZE


HOST = "10.0.0.1"
PORT = 8087

PATH = "file.txt"
STORAGE = "storage"
