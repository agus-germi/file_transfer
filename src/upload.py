import socket
import time
import signal
import sys
import os
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
	force_send_end,
	is_data_available,
)
from lib.udp import UDPFlags, UDPHeader
from lib.constants import TIMEOUT, TIMEOUT_SACK, FRAGMENT_SIZE, SACK_WINDOW_SIZE, SEND_WINDOW_SIZE, PACKAGE_SEND_DELAY, MAX_SAC_DIF

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
		connection.sequence = key
		data = connection.fragments[key]
		send_data(client_socket, connection, data, sequence=connection.sequence)
		logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

		try:
			addr, header, data = receive_package(client_socket)
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
			send_data(
				client_socket,
				connection,
				data,
				sequence=connection.sequence,
			)


def send_sack_data():
	for seq, (key, data) in enumerate(connection.fragments.items()):
		if seq >= SACK_WINDOW_SIZE or connection.window_sents > SEND_WINDOW_SIZE:  # Solo mandamos los primeros 8 elementos
			if connection.window_sents > SEND_WINDOW_SIZE:
				print("ASADASfasfadsdfasfg")
			break
		if key > connection.sequence + MAX_SAC_DIF:
			print("Se me lleno la cola")
			break

		# Print saber que segmentos quedan cuando quedan pocos
		#if len(connection.fragments) < 10:
		#	print("FRAG: ", connection.fragments.keys())

		send_data(client_socket, connection, data, sequence=key)
		connection.window_sents += 1
		print("Enviando paquete ", key, " quedan : ", len(connection.fragments))
	
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
			print("ACK recibido ", header.sequence, " Nuevo sequence: ", connection.sequence)

			for i in range(seq, header.sequence +1):
				if i in connection.fragments:
					print("Borrando fragmento ", i)
					del connection.fragments[i]
			
		else:
			sack = header.get_sequences()[1]
			for i in sack:
				if i in connection.fragments:
					print("Borrando fragmento SACK", i, " sequence: ", connection.sequence, " header " , header.sequence)
					#connection.window_sents -= 1
					del connection.fragments[i]
	if header.has_close():
		connection.is_active = False


def upload_with_sack(dir, name):
	client_socket.settimeout(TIMEOUT_SACK)
	connection.sequence = 1  # Inicia el número de secuencia en 1
	connection.path = f"{dir}/{name}"
	connection.get_fragments()
	connection.is_active = True

	send_sack_data()
	while connection.is_active:
		try:		
			addr, header, data = receive_package(client_socket)
			handle_ack_sack(header)
			print("AAheader sequence: ", header.sequence)
			while is_data_available(client_socket):
				addr, header, data = receive_package(client_socket)
				print("header sequence: ", header.sequence)
				handle_ack_sack(header)

			send_sack_data()
			# Para que el cliente no sature al servidor con el envio de paquetes
			time.sleep(PACKAGE_SEND_DELAY)

		except TimeoutError:
			logger.error("TIMEOUT")
			connection.window_sents -= SACK_WINDOW_SIZE/2
			print("quedan fragmentos: ", len(connection.fragments))
			time.sleep(PACKAGE_SEND_DELAY*2)
			send_sack_data()
		except Exception as e:
			logger.error("Traceback info:\n" + traceback.format_exc())


def handle_upload(dir, name, protocol):
	try:
		if protocol == "stop_and_wait":
			upload_stop_and_wait(dir, name)
		elif protocol == "sack":
			upload_with_sack(dir, name)
		else:
			logger.error(f"Protocolo no soportado: {protocol}")
			raise ValueError(f"Protocolo no soportado: {protocol}")
		
		if not connection.fragments and connection.sequence > 1:
			force_send_end(client_socket, connection, send_end)
			logger.info(f"Archivo cargado exitosamente")
	except Exception as e:
		logger.error(f"Error durante el upload: {e}")
	finally:
		close_connection(client_socket, connection)



def limpiar_recursos(signum, frame):
	print(f"Recibiendo señal {signum}, limpiando recursos...")
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
		if connect_server(args.protocol):
			handle_upload(args.src, args.name, args.protocol)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		client_socket.close()
