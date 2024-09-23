import socket
import sys
import os
import signal
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
	client_sequence=0,
	server_sequence=0,
	download=DOWNLOAD,
	upload=UPLOAD,
	path = args.name
)


def connect_server():
	header = UDPHeader(0, connection.client_sequence, 0, 0)
	header.set_flag(UDPFlags.START)
	if DOWNLOAD:
		header.set_flag(UDPFlags.DOWNLOAD)
	try:
		send_package(client_socket, connection, header, connection.path.encode())
		addr, header, data = receive_package(client_socket)

		if header.has_ack() and header.has_start() and header.server_sequence == 0:
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

	file_dir = f"{dir}/{name}"
	connection.client_sequence = 0
	with open(file_dir, 'rb') as f:
		while True:
			fragment = f.read(FRAGMENT_SIZE)
			if not fragment:
				break

			send_data(client_socket, connection, fragment, sequence=connection.client_sequence)

			print(f"Fragmento {connection.client_sequence} enviado al servidor. Con Data {fragment}")

			addr, header, data = receive_package(client_socket)

			print(f"Header Client sequence {header.client_sequence}")
			print(f"Connection Client sequence {connection.client_sequence}")
			if header.has_ack() and header.client_sequence == connection.client_sequence:
				print(f"ACK {connection.client_sequence} recibido del servidor.")
				connection.client_sequence += 1
			
			else:
				print(f"Error: ACK {connection.client_sequence} no recibido del servidor.")
				break
		
		send_end(client_socket, connection)
		close_connection(client_socket, connection)
		print("Archivo enviado exitosamente.")



def limpiar_recursos(signum, frame):
	print(f"Recibiendo señal {signum}, limpiando recursos...")
	sys.exit(0)  # Salgo del programa con código 0 (éxito)


if __name__ == '__main__':
	# Capturo señales de interrupción
	signal.signal(signal.SIGINT, limpiar_recursos)  # Ctrl+C
	signal.signal(signal.SIGTERM, limpiar_recursos)  # kill
	signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
	if os.name != 'nt':  # Windows 
		signal.signal(signal.SIGQUIT, limpiar_recursos)  # Ctrl+\
		signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
		signal.signal(signal.SIGHUP, limpiar_recursos)  # hangup
	
	if connect_server():
		try:
			if UPLOAD:
				upload_file(args.src, args.name)
		except CloseConnectionException as e:
			print(e)
		finally:
			client_socket.close()

