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
from lib.constants import TIMEOUT, FRAGMENT_SIZE, SACK_WINDOW_SIZE


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





# def upload_with_sack(dir, name):
# 	#try:
# 	connection.sequence = 0  # Inicia el número de secuencia en 0
# 	unacked_packets = {}  # Diccionario para almacenar los paquetes no reconocidos <- TOTAL DE PAQUETES

# 	# Construye la ruta del archivo
# 	file_dir = f"{dir}/{name}"

# 	# WHILE UNACKED_PACKETS:
		

# 	# Abre el archivo en modo lectura binaria
# 	with open(file_dir, "rb") as file:
# 		unacked_packets = connection.get_fragments() #Primero guardamos el total de los paquetes

# 		#TODO que pasa si hay menos paquetes que window size
# 		network_load = []
# 		while len(network_load) < WINDOW_SIZE: # Envio la cantidad que la windowSize me pe
# 			packet_to_send = unacked_packets[connection.sequence]
# 			send_data(
# 					client_socket,
# 					connection,
# 					packet_to_send,
# 					sequence=connection.sequence,
# 				)
# 			network_load.append(connection.sequence)
# 			connection.sequence += 1	
# 		while unacked_packets: # Mientras tengamos paquetes sin ACK (no enviados correctamente)
# 			client_socket.settimeout(TIMEOUT)
# 			try:
# 				_, header, _ = receive_package(client_socket)
# 				last_complete_secuence, sack = header.decode_sack()
# 				#borrar los sack correspondientes
				
# 				#borrar todo lo previo a last_complete 
# 				index_from = 0 if last_complete_secuence < WINDOW_SIZE else last_complete_secuence - WINDOW_SIZE #esto puede ser *2
# 				for i in range(index_from, last_complete_secuence):
# 					unacked_packets.remove(i)
				
# 				#Borrar aquellos que recibi fuera de orden
# 				for selected_ack in sack:
# 					unacked_packets.remove(selected_ack)
				
# 				## aca recibe el paquete y tenemos que ver como hacer para enviar el siguiente moviendo la ventana acorde
# 				first_item = next(iter(my_dict.items())) # si obtenemos el primer elemento del dict luego de borrar los que estoy segura que ya se enviaron => envio ese
# 				send_data(
# 					client_socket,
# 					connection,
# 					packet_to_send,
# 					sequence=connection.sequence,
# 				)					

# 			except TimeoutError:
					#mandar el primero en la cola
	#except Exception as e:
		#logger.error(f"Error durante la subida SACK: {e}")
		#raise ValueError(f"Protocolo no soportado: {protocol}")

#recibimos ack 1000
#(1000 - 8 , 1000 + 8)
#recibinmos ack 5
#5-8
		# while buff.not_empty:
		# 	try:
		# 		header = socket_read()
		# 		sec, sacks = decode(header)
		# 		buff.remove(sec, sacks)
		# 		buff.refil
		# 		buff.send_first
		# 	except timeout:
		# 		buff.send_first

				


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
