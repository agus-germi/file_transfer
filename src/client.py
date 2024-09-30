import socket
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.parser import parse_upload_args
from lib.connection import (
    Connection,
    send_package,
    receive_package,
)
from lib.udp import UDPFlags, UDPHeader
from lib.constants import TIMEOUT


UPLOAD = True
DOWNLOAD = False

args = parse_upload_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
    addr=(args.host, args.port),  # Usa los argumentos parseados
    sequence=0,
    download=DOWNLOAD,
    path=args.name,
)


def connect_server():
    header = UDPHeader(0, connection.sequence, 0)
    header.set_flag(UDPFlags.START)
    if DOWNLOAD:
        header.set_flag(UDPFlags.DOWNLOAD)
    try:
        send_package(client_socket, connection, header, connection.path.encode())
        addr, header, data = receive_package(client_socket)
        logger.info(f"Header: , {header.get_sequences()}")
        logger.info(f"Sack:  {format(header.sack, f"0{32}b")}")

        if header.has_ack() and header.has_start() and header.sequence == 0:
            header.set_flag(UDPFlags.ACK)
            send_package(client_socket, connection, header, b"")
            logger.info("Conexión establecida con el servidor.")
            return True
        else:
            logger.error("Error: No se pudo establecer conexión con el servidor.")
            return False
    except ConnectionResetError:
        logger.error("Error: Conexión rechazada por el servidor.")
        return False
    except socket.timeout:
        logger.error("Error: No se pudo establecer conexión con el servidor.")
        return False


if __name__ == "__main__":
    setup_signal_handling()
    if connect_server():
        pass
    try:
        pass
    except Exception as e:
        logger.error(f"Error en main: {e}")
    finally:
        client_socket.close()
