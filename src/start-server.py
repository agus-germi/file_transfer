import socket
import sys
import os
import signal
from lib.parser import parse_server_args
from lib.udp import send_package, receive_package,  reject_connection, close_connection, send_ack, send_confirmation
from lib.udp import ClientConnection, Connection, UDPFlags, UDPHeader
from lib.constants import TIMEOUT, FRAGMENT_SIZE
from lib.constants import HOST, PORT, TIMEOUT, STORAGE


# > python start - server -h
# usage : start - server [ - h ] [ - v | -q ] [ - H ADDR ] [ - p PORT ] [- s DIRPATH ]
# < command description >
# optional arguments :
# -h , -- help show this help message and exit
# -v , -- verbose increase output verbosity
# -q , -- quiet decrease output verbosity
# -H , -- host service IP address
# -p , -- port service port
# -s , -- storage storage dir path


connections = {}


def limpiar_recursos(signum, frame):
	print(f"Recibiendo señal {signum}, limpiando recursos...")
	sys.exit(0)  # Salgo del programa con código 0 (éxito)



def start_server():
	# Parsear los argumentos usando la función importada
	args = parse_server_args()
	
	# Configurar la verbosidad (ejemplo de uso de verbosity)
	if args.verbose:
		print("Verbosity turned on")

	# Crear un socket UDP
	server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	server_address = (args.host, args.port)  # Usa los argumentos parseados
	server_storage = args.storage
	server_socket.bind(server_address)
	print(f"Servidor escuchando en {server_address} con almacenamiento en {server_storage}")
	try:
		while True:
			handle_connection(server_socket, server_storage)
	except KeyboardInterrupt:
		server_socket.close()
		print("\nInterrupción detectada. El programa ha sido detenido.")


def check_connection(server_socket, addr, header: UDPHeader, data: bytes):
	connection = ClientConnection(
		server_socket,
		addr,
		data.decode(),
		upload= not header.has_download(),
		download=header.has_download(),
	)

	print("Path: ", data.decode(), "| Upload: ", connection.upload, "| Download: ", connection.download)
	if header.has_start() and header.client_sequence == 0 and data.decode() != "":
		print("Mensaje Recibido: ", addr, " [Start]")
		connection.handle_handshake()
		if connection.is_active:
			connections[addr] = connection
			connection.start()
	else:
		reject_connection(server_socket, connection)



def handle_connection(server_socket, server_storage):
	try:
		addr, header, data = receive_package(server_socket)		

		if not connections.get(addr):
			check_connection(server_socket, addr, header, data)
			return None
		
		connection = connections.get(addr)
		# No se inicializo la conexion y se recibio un paquete de datos
		if header.has_flag(UDPFlags.DATA) and not connection.is_active:
			connection.is_active = False
			connection.join()
			close_connection(server_socket, connection)
			connections.pop(addr)
		# Se recibio un paquete de cierre
		elif header.has_flag(UDPFlags.CLOSE):
			print("Mensaje Recibido: ", addr, " [Close]")
			connection.is_active = False
			connection.join()
			connections.pop(addr)
			# TODO Habria que cerrar desde el server?
			print("Cliente Desconectado: ", addr)
		elif header.has_flag(UDPFlags.END):
			print("Mensaje Recibido: ", addr, " [End]")
			print("Cliente: ", addr, " recepcion archivo completada.")
			connection.storage = server_storage
			connection.save_file()
		else:
			print("Mensaje Recibido: ", addr)
			message = {"addr": addr, "header": header, "data": data}
			connection.put_message(message)

	except ConnectionResetError:
		print("Error: Conexión rechazada por el cliente.")



if __name__ == '__main__':
	# Capturo señales de interrupción
	signal.signal(signal.SIGINT, limpiar_recursos)  # Ctrl+C
	signal.signal(signal.SIGTERM, limpiar_recursos)  # kill
	signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
	if os.name != 'nt':  # Windows 
		signal.signal(signal.SIGQUIT, limpiar_recursos)  # Ctrl+\
		signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
		signal.signal(signal.SIGHUP, limpiar_recursos)  # hangup
	
	start_server()


