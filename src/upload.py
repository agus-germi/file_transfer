import socket
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.parser import parse_upload_args
from lib.connection import (
	Connection,
	send_package,
	receive_package,
	close_connection,
	send_data,
	send_end,
	confirm_endfile,
)
from lib.udp import UDPFlags, UDPHeader
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
			return False
	except ConnectionResetError:
		logger.error("Error: Conexión rechazada por el servidor.")
		return False
	except socket.timeout:
		logger.error("Error: No se pudo establecer conexión con el servidor.")
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





def upload_with_sack(dir, name):
	try:
		window_size = WINDOW_SIZE  # Tamaño de la ventana
		connection.sequence = 0  # Inicia el número de secuencia en 0
		unacknowledged_packets = {}  # Diccionario para almacenar los paquetes no reconocidos

		# Construye la ruta del archivo
		file_dir = f"{dir}/{name}"

		# Abre el archivo en modo lectura binaria
		with open(file_dir, "rb") as file:
			while True:
				# Actualiza y muestra la ventana actual
				current_window = list(range(connection.sequence, connection.sequence + window_size))
				logger.info(f"Ventana actual: {current_window}")

				# Envía paquetes hasta alcanzar el tamaño de la ventana
				while len(unacknowledged_packets) < window_size:
					fragment = file.read(FRAGMENT_SIZE)
					if not fragment:
						break
					
					# Envía el fragmento y almacénalo en paquetes no reconocidos
					send_data(
						client_socket,
						connection,
						fragment,
						sequence=connection.sequence,
					)
					unacknowledged_packets[connection.sequence] = fragment
					connection.sequence += 1

					# Actualiza la ventana después de enviar un nuevo paquete
					current_window = list(range(connection.sequence, connection.sequence + window_size))
					logger.info(f"Ventana actual después de enviar: {current_window}")

				# Si no hay más fragmentos y todos los paquetes han sido reconocidos, salir del bucle
				if not fragment and not unacknowledged_packets:
					break

				# Manejar los ACKs entrantes
				try:
					client_socket.settimeout(TIMEOUT)
					addr, header, data = receive_package(client_socket)
					
					if header.has_ack():  # Si el paquete es un ACK
						ack_num = header.sequence
						
						if ack_num in unacknowledged_packets:
							# Elimina el paquete reconocido
							del unacknowledged_packets[ack_num]
							
							# Desliza la ventana si el ACK corresponde al paquete no reconocido más bajo
							if not unacknowledged_packets or ack_num == min(unacknowledged_packets.keys()):
								logger.info(f"ACK recibido para el paquete {ack_num}, moviendo ventana")
								connection.sequence = ack_num + 1

								# Actualiza la ventana después de moverla
								current_window = list(range(connection.sequence, connection.sequence + window_size))
								logger.info(f"Ventana actual después de recibir ACK: {current_window}")

				except TimeoutError:
					# Reenvía los paquetes no reconocidos en caso de timeout
					logger.info("Tiempo de espera agotado, reenviando paquetes faltantes")
					logger.info(f"Reenviando paquetes sin ACK: {list(unacknowledged_packets.keys())}")
					
					for pkt_num, data in unacknowledged_packets.items():
						send_data(client_socket, connection, data, sequence=pkt_num)
						logger.info(f"Reenviado paquete con número de secuencia {pkt_num}")

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
			handle_upload(args.src, args.name, args.protocol)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		client_socket.close()
