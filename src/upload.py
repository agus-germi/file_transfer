import socket
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.parser import parse_upload_args
from lib.udp import (
    Connection,
    UDPFlags,
    UDPHeader,
    send_package,
    receive_package,
    close_connection,
    send_data,
    send_end,
)
from lib.udp import CloseConnectionException
from lib.constants import TIMEOUT, FRAGMENT_SIZE, WINDOW_SIZE


UPLOAD = True
DOWNLOAD = False

# TODO: poner todo esto en otro lado
args = parse_upload_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
    addr=(args.host, args.port),  # Usa los argumentos parseados
    sequence=0,
    download=DOWNLOAD,
    upload=UPLOAD,
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

        if header.has_ack() and header.has_start() and header.sequence == 0:
            header.set_flag(UDPFlags.ACK)
            send_package(client_socket, connection, header, b"")
            logger.info("Conexión establecida con el servidor.")
            return True
        else:
            logger.error("Error: No se pudo establecer conexión con el servidor.")
            client_socket.close()
            return False
    except socket.timeout:
        logger.error("Error: No se pudo establecer conexión con el servidor.")
        client_socket.close()  # seguir intentando, por lo menos unas 5 veces
        return False


def upload_file(dir, name):
    """Envía un archivo al servidor en fragmentos usando UDP."""
    file_dir = f"{dir}/{name}"
    connection.sequence = 0
    with open(file_dir, "rb") as f:
        while True:
            fragment = f.read(FRAGMENT_SIZE)
            if not fragment:
                break

            send_data(client_socket, connection, fragment, sequence=connection.sequence)
            logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

            addr, header, data = receive_package(client_socket)

            if header.has_ack() and header.sequence == connection.sequence:
                logger.info(f"ACK {connection.sequence} recibido del servidor.")
                connection.sequence += 1
            else:
                logger.error(
                    f"Error: ACK {connection.sequence} no recibido del servidor."
                )
                break

        send_end(client_socket, connection)
        close_connection(client_socket, connection)
        logger.info("Archivo enviado exitosamente.")


def upload_stop_and_wait(dir, name):
    """Envía un archivo al servidor en fragmentos usando UDP."""
    file_dir = f"{dir}/{name}"

    with open(file_dir, "rb") as file:
        connection.sequence = 0
        while True:
            fragment = file.read(FRAGMENT_SIZE)
            if not fragment:
                break

            send_data(client_socket, connection, fragment, sequence=connection.sequence)
            logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

            while True:
                try:
                    addr, header, data = receive_package(client_socket)
                    if header.has_ack() and header.sequence == connection.sequence:
                        logger.info(f"ACK {connection.sequence} recibido del servidor.")
                        connection.sequence += 1
                        break
                    else:
                        logger.error(
                            f"Received ACK {header.sequence} is not {connection.sequence} "
                        )

                except TimeoutError:
                    logger.error(
                        f"ACK {connection.sequence} no recibido del servidor. Reenviando."
                    )
                    send_data(
                        client_socket,
                        connection,
                        fragment,
                        sequence=connection.sequence,
                    )


def confirm_endfile():
    for i in range(3):
        try:
            send_end(client_socket, connection)
            addr, header, data = receive_package(client_socket)
            if header.has_end() and header.has_ack():
                break
        except TimeoutError:
            logger.warning(
                "Tiempo de espera agotado al confirmar el final del archivo."
            )


def upload_with_sack(dir, name):
    try:
        window_size = WINDOW_SIZE  # Tamaño de la ventana
        connection.sequence = 0  # Inicia el número de secuencia en 0
        unacknowledged_packets = (
            {}
        )  # Diccionario para almacenar los paquetes no reconocidos

        # Construye la ruta del archivo
        file_dir = f"{dir}/{name}"

        # Abre el archivo en modo lectura binaria
        with open(file_dir, "rb") as file:
            while True:
                # Envía paquetes hasta alcanzar el tamaño de la ventana
                for _ in range(window_size - len(unacknowledged_packets)):
                    fragment = file.read(FRAGMENT_SIZE)  # Lee un fragmento del archivo
                    if not fragment:
                        break

                    # Envía el fragmento de datos con el número de secuencia actual
                    send_data(
                        client_socket,
                        connection,
                        fragment,
                        sequence=connection.sequence,
                    )

                    # Almacena el fragmento en el diccionario de paquetes no reconocidos
                    unacknowledged_packets[connection.sequence] = fragment
                    connection.sequence += 1  # Incrementa el número de secuencia

                # Si se ha terminado de enviar el archivo y no hay paquetes no reconocidos, sale del bucle
                if not fragment and not unacknowledged_packets:
                    break

                # Manejar los ACKs entrantes (paquetes reconocidos por el receptor)
                try:
                    client_socket.settimeout(TIMEOUT)
                    addr, header, data = receive_package(
                        client_socket
                    )  # Recibe un paquete
                    if header.has_ack():  # Si el paquete es un ACK
                        ack_num = header.sequence  # Número de secuencia del ACK
                        if (
                            ack_num in unacknowledged_packets
                        ):  # Si el número de secuencia del ACK es válido
                            logger.info(f"ACK recibido para el paquete {ack_num}")
                            del unacknowledged_packets[
                                ack_num
                            ]  # Elimina el paquete reconocido
                except socket.timeout:
                    logger.warning(
                        "Tiempo de espera agotado, reenviando paquetes faltantes"
                    )
                    # Si hay un timeout, se reenvían los paquetes no reconocidos
                    for pkt_num, data in unacknowledged_packets.items():
                        send_data(client_socket, connection, data, sequence=pkt_num)

    except Exception as e:
        logger.error(f"Error durante la subida SACK: {e}")
        raise



def handle_upload(dir, name, protocol):
    try:
        if protocol == "stop_and_wait":
            upload_stop_and_wait(dir, name)
        elif protocol == "sack":
            upload_with_sack(dir, name)
        else:
            logger.error(f"Protocolo no soportado: {protocol}")
            raise ValueError(f"Protocolo no soportado: {protocol}")

        confirm_endfile()
        logger.info("Archivo enviado exitosamente.")
    except Exception as e:
        logger.error(f"Error durante el upload: {e}")
    finally:
        close_connection(client_socket, connection)

if __name__ == "__main__":
    setup_signal_handling()
    if connect_server():
        try:
            handle_upload(args.src, args.name, args.protocol)
        except Exception as e:
            logger.error(f"Error en main: {e}")
        finally:
            client_socket.close()
