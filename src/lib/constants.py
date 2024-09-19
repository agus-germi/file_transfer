import struct

TIMEOUT = 2  # Timeout in seconds
MAX_RETRIES = 3 # Numero maximo de reintentos

# Constants related to UDP Header
HEADER_FORMAT = '!B I I I'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

HOST = '10.0.0.1'
PORT = 8087
#server_address = ('10.0.0.1', 8087)

PATH = 'file.txt'
STORAGE = 'storage'