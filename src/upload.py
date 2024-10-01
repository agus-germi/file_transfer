import socket
import time
import signal
import sys
import os
import traceback
from lib.logger import setup_logger
from lib.parser import parse_upload_args
from lib.connection import (
	Connection,
	send_package,
	receive_package,
	close_connection,
	send_data,
	send_end,
	force_send_end,
	is_data_available,
	force_send_close,
	connect_server,
)
from lib.udp import UDPFlags, UDPHeader
from lib.constants import (
	TIMEOUT,
	TIMEOUT_SACK,
	SACK_WINDOW_SIZE,
	SEND_WINDOW_SIZE,
	PACKAGE_SEND_DELAY,
	MAX_SAC_DIF,
	MAX_RETRIES,
)


UPLOAD = True
DOWNLOAD = False

args = parse_upload_args()
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


def upload_stop_and_wait():
	"""Envía un archivo al servidor en fragmentos usando UDP."""
	connection.get_fragments()
	connection.is_active = True

	while connection.fragments and connection.is_active:
		key = next(iter(connection.fragments))
		connection.sequence = key
		data = connection.fragments[key]
		send_data(client_socket, connection, data, sequence=connection.sequence)
		logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

		try:
			addr, header, data = receive_package(client_socket)
			connection.retries = 0
			if header.has_ack() and header.sequence == connection.sequence:
				logger.info(f"ACK {connection.sequence} recibido del servidor.")
				if header.sequence in connection.fragments:
					connection.fragments.pop(header.sequence)
			elif header.has_close():
				connection.is_active = False
			else:
				logger.error(
					f"Received ACK {header.sequence} is not {connection.sequence} "
				)

		except TimeoutError:
			logger.error(
				f"ACK {connection.sequence} no recibido del servidor. Reenviando."
			)
			if connection.retries > MAX_RETRIES:
				connection.is_active = False
			connection.retries += 1


def send_sack_data():
	for seq, (key, data) in enumerate(connection.fragments.items()):
		if (
			seq >= SACK_WINDOW_SIZE or connection.window_sents > SEND_WINDOW_SIZE
		):  # Solo mandamos los primeros 8 elementos
			break
		if key > connection.sequence + MAX_SAC_DIF:
			# Se lleno la cola
			break


		send_data(client_socket, connection, data, sequence=key)
		connection.window_sents += 1
		logger.info(f"Enviando paquete  {key}  quedan {len(connection.fragments)}")

	# Se enviaron por completo el archivo
	if not connection.fragments:
		connection.is_active = False


def handle_ack_sack(header: UDPHeader):
	if header.has_ack():
		connection.window_sents -= 1
		if header.sequence > connection.sequence:
			connection.window_sents -= header.sequence - connection.sequence

			seq = connection.sequence
			connection.sequence = header.sequence


			for i in range(seq, header.sequence + 1):
				if i in connection.fragments:
					logger.info(f"Borrando fragmento {i}")
					del connection.fragments[i]

		else:
			sack = header.get_sequences()[1]
			for i in sack:
				if i in connection.fragments:
					# connection.window_sents -= 1
					del connection.fragments[i]
	if header.has_close():
		connection.is_active = False


def upload_with_sack():
	client_socket.settimeout(TIMEOUT_SACK)
	connection.sequence = 1
	connection.get_fragments()
	connection.is_active = True

	send_sack_data()
	while connection.is_active:
		try:
			addr, header, data = receive_package(client_socket)
			connection.retries = 0
			handle_ack_sack(header)
			while is_data_available(client_socket):
				addr, header, data = receive_package(client_socket)
				handle_ack_sack(header)

			send_sack_data()
			# Para que el cliente no sature al servidor con el envio de paquetes
			time.sleep(PACKAGE_SEND_DELAY)

		except TimeoutError:
			logger.error("TIMEOUT")
			connection.window_sents -= SACK_WINDOW_SIZE / 2
			if connection.retries > MAX_RETRIES:
				connection.is_active = False
			if connection.retries % 2 == 0:
				logger.info(f"Quedan fragmentos:  {len(connection.fragments)}")
				#time.sleep(PACKAGE_SEND_DELAY)
				send_sack_data()
			connection.retries += 1
		except Exception as e:
			logger.error(f"Error: {e} - Traceback info:\n" + traceback.format_exc())


def handle_upload():
	connection.path = args.src
	try:
		if args.protocol == "stop_and_wait":
			upload_stop_and_wait()
		elif args.protocol == "sack":
			upload_with_sack()
		else:
			logger.error(f"Protocolo no soportado: {args.protocol}")
			raise ValueError(f"Protocolo no soportado: {args.protocol}")

		if not connection.fragments and connection.sequence > 1:
			force_send_end(client_socket, connection, send_end)
			logger.info(f"Archivo cargado exitosamente")
	except Exception as e:
		logger.error(f"Error durante el upload: {e}")
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
			handle_upload()
	except ValueError as e:
		logger.error(e)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		close_connection(client_socket, connection)
		client_socket.close()
