import socket
import sys
import os
import signal
from lib.parser import parse_download_args
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package, close_connection, send_end, send_ack, confirm_endfile
from lib.udp import CloseConnectionException
from lib.constants import MAX_RETRIES, TIMEOUT, FRAGMENT_SIZE


UPLOAD = False
DOWNLOAD = True

# TODO: poner todo esto en otro lado
args = parse_download_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)


# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
    addr=(args.host, args.port),  # Usa los argumentos parseados
    sequence=0,
    download=DOWNLOAD,
    upload=UPLOAD,
    path = args.name
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
			return False
	except ConnectionResetError:
		logger.error("Error: Conexión rechazada por el servidor.")
		return False
	except socket.timeout:
		logger.error("Error: No se pudo establecer conexión con el servidor.")
		return False


def download_file():
    fragments = {}
    is_running = True

    while is_running:
        addr, header, data = receive_package(client_socket)
        if header.has_data() and header.sequence == connection.sequence:
            if header.sequence not in fragments:
                fragments[header.sequence] = data
                connection.sequence += 1
                print(f"Fragmento {header.sequence} recibido del servidor.")
            else:
                 print(f"Fragmento {header.sequence} ya recibido.")
                        
            send_ack(client_socket, connection, sequence=header.sequence)

        elif header.has_end():
            is_running = False
        elif header.has_close():
            is_running = False
            if len(data) > 0:
                print(f"Cierre del servidor: [{data.decode()}]")



def handle_download(dir, name, protocol):
	try:
		if protocol == "stop_and_wait":
			download_stop_and_wait(dir, name)
		elif protocol == "sack":
			download_with_sack(dir, name)
		else:
			logger.error(f"Protocolo no soportado: {protocol}")
			raise ValueError(f"Protocolo no soportado: {protocol}")

		confirm_endfile(client_socket, connection)
		logger.info("Archivo enviado exitosamente.")
	except Exception as e:
		logger.error(f"Error durante el upload: {e}")
	finally:
		close_connection(client_socket, connection)


if __name__ == "__main__":
	setup_signal_handling()
	try:
		if connect_server():
			handle_download(args.src, args.name, args.protocol)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		client_socket.close()
