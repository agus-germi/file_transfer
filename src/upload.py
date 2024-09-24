import socket
import sys
import os
import signal
from lib.utils import setup_signal_handling, limpiar_recursos
from lib.parser import parse_upload_args, configure_logging
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package, close_connection, send_data, send_end
from lib.udp import CloseConnectionException
from lib.constants import MAX_RETRIES, TIMEOUT, FRAGMENT_SIZE


# > python upload -h
# usage : upload [ - h ] [ - v | -q ] [ - H ADDR ] [ - p PORT ] [ - s FILEPATH ] [ - n FILENAME ]
# < command description >
# optional arguments :
# -h , -- help show this help message and exit
# -v , -- verbose increase output verbosity
# -q , -- quiet decrease output verbosity
# -H , -- host server IP address
# -p , -- port server port
# -s , -- src source file path
# -n , -- name file name

UPLOAD = True
DOWNLOAD = False

# Parsear los argumentos usando la función importada
args = parse_upload_args()
logger = configure_logging(args)

# Configurar la verbosidad (ejemplo de uso de verbosity)
if args.verbose:
	print("Verbosity turned on")

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
	addr=(args.host, args.port),  # Usa los argumentos parseados
	sequence=0,
	download=DOWNLOAD,
	upload=UPLOAD,
	path = args.name,

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
			print("Conexión establecida con el servidor.")
			return True
		else:
			print("Error: No se pudo establecer conexión con el servidor.")
			client_socket.close()
			return False
	except socket.timeout:
		print("Error: No se pudo establecer conexión con el servidor.")
		client_socket.close()
		return False


def upload_file(dir, name):
	"""Envía un archivo al servidor en fragmentos usando UDP."""

	# TODO Deberia reenviar en caso que no llegue ACK del server
	file_dir = f"{dir}/{name}"
	connection.sequence = 0
	with open(file_dir, 'rb') as f:
		while True: # TODO While true NO DEBERIA ESTAR
			fragment = f.read(FRAGMENT_SIZE)
			if not fragment:
				break

			send_data(client_socket, connection, fragment, sequence=connection.sequence)

			#print(f"Fragmento {connection.sequence} enviado al servidor. Con Data {fragment}")

			addr, header, data = receive_package(client_socket)

			#print(f"Header Client sequence {header.sequence}")
			#print(f"Connection Client sequence {connection.sequence}")
			if header.has_ack() and header.sequence == connection.sequence:
				#print(f"ACK {connection.sequence} recibido del servidor.")
				connection.sequence += 1
			
			else:
				print(f"Error: ACK {connection.sequence} no recibido del servidor.")
				break
		
		send_end(client_socket, connection)
		close_connection(client_socket, connection)
		print("Archivo enviado exitosamente.")


def upload_stop_and_wait(dir, name):
	"""Envía un archivo al servidor en fragmentos usando UDP."""

	# TODO Deberia reenviar en caso que no llegue ACK del server
	file_dir = f"{dir}/{name}"
	
	with open(file_dir, 'rb') as f:
		connection.sequence = 0
		while True: # TODO While true NO DEBERIA ESTAR
			
			fragment = f.read(FRAGMENT_SIZE)
			if not fragment:
				break

			send_data(client_socket, connection, fragment, sequence=connection.sequence)

			#print(f"Fragmento {connection.sequence} enviado al servidor. Con Data {fragment}")

			# a partir de aca, espero por el ack del servidor
			while True:
				try:
					addr, header, data = receive_package(client_socket)
					#print(f"Header Client sequence {header.sequence}")
					#print(f"Connection Client sequence {connection.sequence}")
					if header.has_ack() and header.sequence == connection.sequence:
						#print(f"ACK {connection.sequence} recibido del servidor.")
						connection.sequence += 1
						break
				except TimeoutError:
					print(f"Error: ACK {connection.sequence} no recibido del servidor.")
					#print(f"Enviando paquete nuevamente")
					send_data(client_socket, connection, fragment, sequence=connection.sequence)
		
		send_end(client_socket, connection)
		close_connection(client_socket, connection)
		print("Archivo enviado exitosamente.")

def upload_with_sack(dir, name, protocol):
	pass

def handle_upload(dir, name, protocol):
    if protocol == "stop_and_wait":
        upload_stop_and_wait(dir, name)
    elif protocol == "sack":
        upload_with_sack(dir, name)
    else:
        raise ValueError(f"Unsupported protocol: {protocol}")

if __name__ == '__main__':
	setup_signal_handling()
	if connect_server():
		try:
			handle_upload(args.src, args.name, args.protocol)
			print(args.src, args.name)
		except CloseConnectionException as e:
			print(e)
		finally:
			client_socket.close()

