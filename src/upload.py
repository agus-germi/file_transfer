import socket
import traceback
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
	confirm_send,
	is_data_available,
)
from lib.udp import UDPFlags, UDPHeader
from lib.constants import TIMEOUT, FRAGMENT_SIZE, SACK_WINDOW_SIZE, SEND_WINDOW_SIZE

from collections import deque

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


def connect_server(protocol):
	header = UDPHeader(connection.sequence)
	header.set_flag(UDPFlags.START)
	if DOWNLOAD:
		header.set_flag(UDPFlags.DOWNLOAD)
	if protocol == "stop_and_wait":
		header.clear_flag(UDPFlags.PROTOCOL)
	elif protocol == "sack":
		header.set_flag(UDPFlags.PROTOCOL)

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


def upload_stop_and_wait(dir, name):
	"""Envía un archivo al servidor en fragmentos usando UDP."""
	file_dir = f"{dir}/{name}"
	connection.path = f"{dir}/{name}"
	connection.get_fragments()
	connection.is_active = True

	while connection.fragments and connection.is_active:
		key = next(iter(connection.fragments))
		data = connection.fragments[key]
		send_data(client_socket, connection, data, sequence=connection.sequence)
		logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

		try:
			addr, header, data = receive_package(client_socket)
			if header.has_ack() and header.sequence == connection.sequence:
				logger.info(f"ACK {connection.sequence} recibido del servidor.")
				connection.sequence += 1
				if header.sequence in connection.fragments:
					connection.fragments.pop(header.sequence)
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
				data,
				sequence=connection.sequence,
			)


def send_sack_data():
	for seq, (key, data) in enumerate(connection.fragments.items()):
		if seq >= SACK_WINDOW_SIZE or connection.window_sents > SEND_WINDOW_SIZE:  # Solo mandamos los primeros 8 elementos
			break
		if key > connection.sequence + 30: # Nunca haya tanta difrencia entre el puntero del server y el mio
			break

		# Print saber que segmentos quedan cuando quedan pocos
		if len(connection.fragments) < 10:
			print("FRAG: ", connection.fragments.keys())

		send_data(client_socket, connection, data, sequence=key)
		if key == 10:
			send_data(client_socket, connection, data, sequence=14)
		connection.window_sents += 1
		print("Enviando paquete ", key)
	
	if not connection.fragments:
		send_end(client_socket, connection)
		connection.is_active = False


def handle_ack_sack(header: UDPHeader):
	if header.has_ack():
		connection.window_sents -= 1
		if header.sequence > connection.sequence:
			connection.window_sents -= header.sequence - connection.sequence
			seq = connection.sequence
			connection.sequence = header.sequence
			print("ACK recibido ", header.sequence, " Nuevo sequence: ", connection.sequence)

			for i in range(seq, header.sequence +1):
				if i in connection.fragments:
					print("Borrando fragmento ", i)
					del connection.fragments[i]
			
		else:
			sack = header.get_sequences()[1]
			for i in sack:
				print("Borrando fragmento SACK", i, " sequence: ", connection.sequence, " header " , header.sequence)
				if i in connection.fragments:
					connection.window_sents -= 1
					del connection.fragments[i]



def upload_with_sack_mati(dir, name):
	try: 
		connection.sequence = 1  # Inicia el número de secuencia en 1
		connection.path = f"{dir}/{name}"
		connection.get_fragments()
		connection.is_active = True

		send_sack_data()
		while connection.is_active:
			addr, header, data = receive_package(client_socket)
			handle_ack_sack(header)
			while is_data_available(client_socket):
				addr, header, data = receive_package(client_socket)
				handle_ack_sack(header)

			send_sack_data()
		

	except TimeoutError:
		logger.error("TIMEOUT")
	except:
		logger.error("Traceback info:\n" + traceback.format_exc())


def handle_upload(dir, name, protocol):
	try:
		if protocol == "stop_and_wait":
			upload_stop_and_wait(dir, name)
		elif protocol == "sack":
			upload_with_sack_mati(dir, name)
		else:
			logger.error(f"Protocolo no soportado: {protocol}")
			raise ValueError(f"Protocolo no soportado: {protocol}")
		
		confirm_send(client_socket, connection, send_end)
		logger.info("Archivo enviado exitosamente.")
	except Exception as e:
		logger.error(f"Error durante el upload: {e}")
	finally:
		close_connection(client_socket, connection)


if __name__ == "__main__":
	setup_signal_handling()
	try:
		if connect_server(args.protocol):
			handle_upload(args.src, args.name, args.protocol)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		client_socket.close()
