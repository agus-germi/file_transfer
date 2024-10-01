import socket
import sys
import os
import signal
import traceback
from lib.parser import parse_download_args
from lib.logger import setup_logger
from lib.connection import (
    Connection,
    send_package,
    receive_package,
    close_connection,
    send_ack,
    send_end_confirmation,
    send_sack_ack,
    force_send_end,
    force_send_close,
    connect_server,
)
from lib.udp import UDPFlags, UDPHeader
from lib.constants import MAX_RETRIES, TIMEOUT, TIMEOUT_SACK


UPLOAD = False
DOWNLOAD = True

args = parse_download_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
    addr=(args.host, args.port),
    sequence=0,
    download=DOWNLOAD,
    path=args.name,
)


def download_stop_and_wait():
    """Descarga un archivo del servidor en fragmentos usando UDP."""
    connection.is_active = True

    while connection.is_active:
        try:
            addr, header, data = receive_package(client_socket)
            if header.has_data():
                # Cuando recibo data exitosamente reseteo el retries
                connection.retries = 0
                if header.sequence not in connection.fragments:
                    connection.fragments[header.sequence] = data
                    connection.sequence = header.sequence
                    logger.info(f"Fragmento {header.sequence} recibido del servidor.")
                else:
                    logger.warning(f"Fragmento {header.sequence} ya recibido.")

                send_ack(client_socket, connection, sequence=header.sequence)
                logger.info(f"Se envio ACK  {header.sequence}")

            # Se recibio por completo el archivo
            elif header.has_end():
                connection.is_active = False
                connection.save_file()

            # Se cierra conexion desde el servidor
            elif header.has_close():
                connection.is_active = False
                if len(data) > 0:
                    logger.info(f"Cierre del servidor: [{data.decode()}]")
                    raise ValueError(f"Archivo inexistente en Servidor")
        except ConnectionResetError:
            logger.error("Error: Conexion perdida")
        except socket.timeout:
            send_ack(client_socket, connection, sequence=connection.sequence)
            logger.warning(f"Reenviando ACK {connection.sequence}")
            if connection.retries > MAX_RETRIES:
                connection.is_active = False
                return False
            connection.retries += 1


def download_with_sack():
    client_socket.settimeout(TIMEOUT_SACK)
    connection.is_active = True

    while connection.is_active:
        try:
            addr, header, data = receive_package(client_socket)

            if header.has_data():
                connection.retries = 0
                if header.sequence not in connection.fragments:
                    connection.fragments[header.sequence] = data
                    logger.info(f"Fragmento {header.sequence} recibido del servidor.")

                if header.sequence == connection.sequence + 1:
                    connection.sequence = header.sequence
                    send_sack_ack(client_socket, connection, connection.sequence)
                    connection.received_out_of_order.sort()
                    received_out_of_order = list(connection.received_out_of_order)
                    for i in received_out_of_order:
                        logger.info(f"Recibidos: , {received_out_of_order},  i: , {i}")
                        if i == connection.sequence + 1:
                            connection.sequence = i
                            send_sack_ack(
                                client_socket, connection, connection.sequence
                            )
                            connection.received_out_of_order.remove(i)
                        else:
                            break

                elif header.sequence > connection.sequence + 1:
                    logger.warning(
                        f"Fragmento {header.sequence} recibido fuera de orden."
                    )
                    if header.sequence not in connection.received_out_of_order:
                        connection.received_out_of_order.append(header.sequence)

                send_sack_ack(
                    client_socket,
                    connection,
                    connection.sequence,
                    connection.received_out_of_order,
                )
                # time.sleep(0.05)

            elif header.has_end():
                connection.is_active = False
                if len(connection.fragments) > 1:
                    connection.save_file()
                    logger.info("Archivo recibido completamente.")

            elif header.has_close():
                connection.is_active = False
                if data:
                    logger.warning(f"Cierre del servidor: [{data.decode()}]")
                    raise ValueError("Archivo inexistente en Servidor")

        except socket.timeout:
            # Manejo de tiempo de espera: reenviar el último SACK
            send_sack_ack(
                client_socket,
                connection,
                connection.sequence,
                connection.received_out_of_order,
            )
            if connection.retries > MAX_RETRIES:
                connection.is_active = False
                return False
            connection.retries += 1

    return True


def handle_download():
    connection.path = f"{args.dst}/{args.name}"
    if args.protocol == "stop_and_wait":
        download_stop_and_wait()
    elif args.protocol == "sack":
        download_with_sack()
    else:
        logger.error(f"Protocolo no soportado: {args.protocol}")
        raise ValueError(f"Protocolo no soportado: {args.protocol}")

    force_send_end(client_socket, connection, send_end_confirmation)

    try:
        pass
    except Exception as e:
        logger.error(f"Error durante el download: {e}")
    finally:
        force_send_close(client_socket, connection, close_connection)


def limpiar_recursos(signum, frame):
    logger.info(f"Recibiendo señal {signum}, limpiando recursos...")
    close_connection(client_socket, connection)
    sys.exit(0)  # Salgo del programa con código 0 (éxito)


def setup_signal_handling():
    signal.signal(signal.SIGINT, limpiar_recursos)
    signal.signal(signal.SIGTERM, limpiar_recursos)
    if os.name != "nt":
        signal.signal(signal.SIGQUIT, limpiar_recursos)
        signal.signal(signal.SIGHUP, limpiar_recursos)


if __name__ == "__main__":
    setup_signal_handling()
    try:
        if connect_server(client_socket, connection, DOWNLOAD, args):
            handle_download()
    except ValueError as e:
        logger.error(e)
    except Exception as e:
        logger.error(f"Error en main: {e}")
        #logger.error(traceback.format_exc())
    finally:
        close_connection(client_socket, connection)
        client_socket.close()
