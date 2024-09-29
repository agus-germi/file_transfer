import socket
import sys
import os
import signal
import traceback
import time
from lib.parser import parse_download_args
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.connection import Connection, CloseConnectionException, send_package, receive_package, close_connection, send_end, send_ack, send_end_confirmation, send_sack_ack, confirm_send
from lib.udp import UDPFlags, UDPHeader
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
	path = args.name
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
			logger.error("Error: No se pudo establecer conexión con el servidor. 1")
			return False
	except ConnectionResetError:
		logger.error("Error: Conexión rechazada por el servidor.")
		return False
	except socket.timeout:
		logger.error("Error: No se pudo establecer conexión con el servidor. 2")
		return False


def download_stop_and_wait():
	connection.is_active  = True

	while connection.is_active:
		try:
			addr, header, data = receive_package(client_socket)
			if header.has_data():
				if header.sequence not in connection.fragments:
					connection.fragments[header.sequence] = data
					connection.sequence = header.sequence
					logger.info(f"Fragmento {header.sequence} recibido del servidor.")
				else:
					logger.warning(f"Fragmento {header.sequence} ya recibido.")
					
											
				send_ack(client_socket, connection, sequence=header.sequence)
				print("Se envio ACK ", header.sequence)

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
			send_ack(client_socket, connection, sequence=header.sequence)
			logger.warning(f"Reenviando ACK {header.sequence}")
			if connection.retrys > MAX_RETRIES:
				# TODO Nunca se sube el retries
				return False


def download_with_sack():
	connection.is_active = True
	expected_sequence = 0

	#diccionario auxiliar para guardar cuantos retries tuvo cada paquete
	retries_per_packet = {}

	while connection.is_active:
		try:
			addr, header, data = receive_package(client_socket)
			
			if header.has_data():
				#print("OutOrder: ", received_out_of_order)
				if header.sequence not in connection.fragments:
					connection.fragments[header.sequence] = data
					logger.info(f"Fragmento {header.sequence} recibido del servidor.")

				if header.sequence == connection.sequence +1:
					connection.sequence = header.sequence
					connection.received_out_of_order.sort()
					send_sack_ack(client_socket, connection, connection.sequence)
					for i in connection.received_out_of_order:
						if i == connection.sequence +1:
							connection.sequence = i
							send_sack_ack(client_socket, connection, connection.sequence)							
							connection.received_out_of_order.remove(i)		
						else:
							break

				elif header.sequence > connection.sequence +1:
					logger.warning(f"Fragmento {header.sequence} recibido fuera de orden.")
					if header.sequence not in connection.received_out_of_order:
						connection.received_out_of_order.append(header.sequence)

				
				send_sack_ack(client_socket, connection, connection.sequence, connection.received_out_of_order)
				#time.sleep(0.05)
				

			elif header.has_end():
				connection.is_active = False
				connection.save_file()
				logger.info("Archivo recibido completamente.")
			
			elif header.has_close():
				connection.is_active = False
				if data:
					logger.warning(f"Cierre del servidor: [{data.decode()}]")
					raise ValueError("Archivo inexistente en Servidor")

		except socket.timeout:
			# Manejo de tiempo de espera: reenviar el último SACK
			print("Timeout")
			# Actualizo el diccionario de retries, si no tuve ninguno le cargo 1, si ya tuve le sumo 1.
			if expected_sequence in retries_per_packet:
				retries_per_packet[expected_sequence] +=1
			else: retries_per_packet[expected_sequence] = 1

			# Si tuve el maximo numero de retries para un paquete, mato la conexion
			if retries_per_packet[expected_sequence] >= MAX_RETRIES:
				logger.error("Numero maximo de reintentos alcanzado. Cerrando conexion.")
				return False


			send_sack_ack(client_socket, connection, connection.sequence, connection.received_out_of_order)
			logger.info(f"SACK enviado. Último ACK: { connection.sequence }, SACK: {bin(header.sack)[2:].zfill(32)}")

	return True




def handle_download(protocol):
	if protocol == "stop_and_wait":
		download_stop_and_wait()
	elif protocol == "sack":
		download_with_sack()
	else:
		logger.error(f"Protocolo no soportado: {protocol}")
		raise ValueError(f"Protocolo no soportado: {protocol}")

	confirm_send(client_socket, connection, send_end_confirmation)
	logger.info("Archivo recibido exitosamente.")
	
	try:
		pass
	except Exception as e:
		logger.error(f"Error durante el download: {e}")
	finally:
		close_connection(client_socket, connection)


if __name__ == "__main__":
	setup_signal_handling()
	try:
		if connect_server(args.protocol):
			connection.path = f"{args.dst}/{args.name}"
			handle_download(args.protocol)
	except ValueError as e:
		logger.error(e)
		logger.error(traceback.format_exc())
	except Exception as e:
		logger.error(f"Error en main: {e}")
		logger.error(traceback.format_exc())
	finally:
		client_socket.close()
