import socket
from lib.logger import setup_logger
from lib.parser import parse_server_args
from lib.connection import (
    receive_package,
    reject_connection,
    close_connection,
    send_start_confirmation,
    send_end_confirmation,
    Connection,
    ClientConnection,
    ClientConnectionSACK,
)
from lib.udp import UDPFlags, UDPHeader
import signal
import sys
import os


connections: dict[Connection] = {}
args = parse_server_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)

# Create a UDP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = (args.host, args.port)
logger.info(f"Server listening on {server_address}")

recv_buffer_size = 1024 * 1024  # 1 MB
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer_size)
server_socket.bind(server_address)


def check_connection(
    server_socket, addr, header: UDPHeader, data: bytes, storage_dir: str, logger
):
    if header.has_protocol():
        connection = ClientConnectionSACK(
            server_socket,
            addr,
            f"{storage_dir}/{data.decode()}",
            download=header.has_download(),
            protocol="sack",
        )
    else:
        connection = ClientConnection(
            server_socket,
            addr,
            f"{storage_dir}/{data.decode()}",
            download=header.has_download(),
            protocol="stop_and_wait",
        )

    logger.info(
        f"Path: {data.decode()} | Upload: {connection.upload} | Download: {connection.download}"
    )
    if header.has_start() and header.sequence == 0 and data.decode() != "":
        if header.has_protocol():
            logger.info(f"Mensaje Recibido: {addr} [Start] con protocolo SACK")
        else:
            logger.info(f"Mensaje Recibido: {addr} [Start] con protocolo Stop and Wait")
        send_start_confirmation(server_socket, connection)
        send_start_confirmation(server_socket, connection)
        connections[addr] = connection
    else:
        reject_connection(server_socket, connection)


def handle_connection(server_socket, storage_dir, logger):
    try:
        addr, header, data = receive_package(server_socket)

        if not connections.get(addr):
            if header.has_start():
                check_connection(server_socket, addr, header, data, storage_dir, logger)
            return None

        connection = connections.get(addr)
        # No se inicializo la conexion y se recibio un paquete de datos
        if header.has_flag(UDPFlags.DATA) and not connection.is_active:
            connection.is_active = False
            if connection.is_alive():
                connection.join()
            close_connection(server_socket, connection)
            connections.pop(addr)

        # Confirmacion de inicio de conexion
        elif header.has_flag(UDPFlags.START) and header.has_flag(UDPFlags.ACK):
            if not connection.is_active:
                connection.is_active = True
                if not connection.is_alive():
                    connection.start()

        # Confirmacion de recepcion de paquete de fin (download)
        elif header.has_flag(UDPFlags.END) and header.has_flag(UDPFlags.ACK):
            connection.is_active = False
            if connection.is_alive():
                connection.join()
            logger.info(f"Mensaje Recibido: {addr} [END]")
            close_connection(server_socket, connection)

        # Se recibio un paquete de End
        elif header.has_flag(UDPFlags.END) and not connection.is_active:
            send_end_confirmation(server_socket, connection)

        # Se recibio un paquete de cierre
        elif header.has_flag(UDPFlags.CLOSE):
            logger.info(f"Mensaje Recibido: {addr} [Close]")
            connection.is_active = False
            if connection.is_alive():
                connection.join()
            connections.pop(addr)
            close_connection(server_socket, connection)
            logger.info(f"Cliente Desconectado: {addr}")
        else:
            message = {"addr": addr, "header": header, "data": data}
            connection.put_message(message)

    except ConnectionResetError as e:
        logger.error("Error: Conexión rechazada por el cliente.")


def start_server():
    try:
        while True:
            handle_connection(server_socket, args.storage, logger)
    except KeyboardInterrupt:
        logger.info("\nInterruption detected. The program has been stopped.")


def limpiar_recursos(signum, frame):
    logger.info(f"Recibiendo señal {signum}, limpiando recursos...")
    for addr, connection in connections.items():
        connection.is_active = False
        if connection.is_alive():
            connection.join()
        close_connection(server_socket, connection)
    server_socket.close()
    sys.exit(0)  # Salgo del programa con código 0 (exito)


def setup_signal_handling():
    signal.signal(signal.SIGINT, limpiar_recursos)
    signal.signal(signal.SIGTERM, limpiar_recursos)
    if os.name != "nt":
        signal.signal(signal.SIGQUIT, limpiar_recursos)
        signal.signal(signal.SIGHUP, limpiar_recursos)


if __name__ == "__main__":
    setup_signal_handling()
    start_server()
    limpiar_recursos(0, 0)
