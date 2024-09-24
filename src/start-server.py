import socket
from lib.utils import setup_signal_handling
from lib.logger import setup_logger
from lib.parser import parse_server_args
from lib.udp import (
    receive_package,
    reject_connection,
    close_connection,
    send_start_confirmation,
    send_end_confirmation,
)
from lib.udp import ClientConnection, UDPFlags, UDPHeader

connections = {}


def check_connection(
    server_socket, addr, header: UDPHeader, data: bytes, storage_dir: str, logger
):
    # TODO: Verificar que data se pueda decodear
    connection = ClientConnection(
        server_socket,
        addr,
        f"{storage_dir}/{data.decode()}",
        download=header.has_download(),
    )

    logger.info(
        f"Path: {data.decode()} | Upload: {connection.upload} | Download: {connection.download}"
    )
    if header.has_start() and header.sequence == 0 and data.decode() != "":
        logger.info(f"Mensaje Recibido: {addr} [Start]")
        send_start_confirmation(server_socket, connection)
        connections[addr] = connection
    else:
        reject_connection(server_socket, connection)


def handle_connection(server_socket, storage_dir, logger):
    try:
        addr, header, data = receive_package(server_socket)

        if not connections.get(addr):
            check_connection(server_socket, addr, header, data, storage_dir, logger)
            return None

        connection = connections.get(addr)
        # No se inicializo la conexion y se recibio un paquete de datos
        if header.has_flag(UDPFlags.DATA) and not connection.is_active:
            connection.is_active = False
            connection.join()  # Para cerrar el thread de la conexion
            close_connection(server_socket, connection)
            connections.pop(addr)

        # Confirmacion de inicio de conexion
        elif header.has_flag(UDPFlags.START) and header.has_flag(UDPFlags.ACK):
            connection.is_active = True
            connection.start()

        # Se recibio un paquete de End
        elif header.has_flag(UDPFlags.END) and not connection.is_active:
            send_end_confirmation(server_socket, connection)

        # Se recibio un paquete de cierre
        elif header.has_flag(UDPFlags.CLOSE):
            logger.info(f"Mensaje Recibido: {addr} [Close]")
            connection.is_active = False
            connection.join()
            connections.pop(addr)
            # TODO Habria que cerrar desde el server?
            # Si se pierde el paquete este -> El server por ttl sabe que tiene que cerrar esta conexion
            logger.info(f"Cliente Desconectado: {addr}")
        else:
            logger.info(f"Mensaje Recibido: {addr}")
            message = {"addr": addr, "header": header, "data": data}
            connection.put_message(message)

    except ConnectionResetError as e:
        logger.error(f"BLA: {e}")
        logger.error("Error: Conexión rechazada por el cliente.")


def start_server():
    args = parse_server_args()
    logger = setup_logger(verbose=args.verbose, quiet=args.quiet)

    # Crear un socket UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (args.host, args.port)
    logger.info(f"Servidor escuchando en {server_address}")
    server_socket.bind(server_address)

    try:
        while True:
            handle_connection(server_socket, args.storage, logger)
    except KeyboardInterrupt:
        server_socket.close()
        logger.info("\nInterrupción detectada. El programa ha sido detenido.")


if __name__ == "__main__":
    setup_signal_handling()
    # TODO Limpiar todos los recursos de connection con su respectivo JOIN al cerrar abruptamente
    start_server()
