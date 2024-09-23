import socket
import sys
import os
import signal
from lib.utils import setup_signal_handling, limpiar_recursos
from lib.logger import setup_logger
from lib.parser import parse_server_args
from lib.udp import send_package, receive_package,  reject_connection, close_connection, send_ack, send_confirmation
from lib.udp import ClientConnection, Connection, UDPFlags, UDPHeader
from lib.constants import TIMEOUT, FRAGMENT_SIZE
from lib.constants import HOST, PORT, TIMEOUT, STORAGE



connections = {}


def check_connection(server_socket, addr, header: UDPHeader, data: bytes, storage_dir: str):
	connection = ClientConnection(
		server_socket,
		addr,
		f"{storage_dir}/{data.decode()}",
		download=header.has_download(),
	)

	print("Path: ", data.decode(), "| Upload: ", connection.upload, "| Download: ", connection.download)
	if header.has_start() and header.sequence == 0 and data.decode() != "":
		print("Mensaje Recibido: ", addr, " [Start]")
		connection.handle_handshake()
		if connection.is_active:
			connections[addr] = connection
			connection.start()
	else:
		reject_connection(server_socket, connection)



def handle_connection(server_socket, storage_dir, logger):
	try:
		addr, header, data = receive_package(server_socket)		

		if not connections.get(addr):
			check_connection(server_socket, addr, header, data, storage_dir)
			return None
		
		connection = connections.get(addr)
		# No se inicializo la conexion y se recibio un paquete de datos
		if header.has_flag(UDPFlags.DATA) and not connection.is_active:
			connection.is_active = False
			connection.join() # Para cerrar el thread de la conexion
			close_connection(server_socket, connection)
			connections.pop(addr)

		# Se recibio un paquete de cierre
		elif header.has_flag(UDPFlags.CLOSE):
			print("Mensaje Recibido: ", addr, " [Close]")
			connection.is_active = False
			connection.join()
			connections.pop(addr)
			# TODO Habria que cerrar desde el server?
			# Si se pierde el paquete este -> El server por ttl sabe que tiene que cerrar esta conexion
			print("Cliente Desconectado: ", addr)
		elif header.has_flag(UDPFlags.END):
			print("Mensaje Recibido: ", addr, " [End]")
			connection.save_file()
		else:
			print("Mensaje Recibido: ", addr)
			message = {"addr": addr, "header": header, "data": data}
			connection.put_message(message)

	except ConnectionResetError:
		print("Error: Conexión rechazada por el cliente.")

def start_server():
    args = parse_server_args()  # Parse arguments
    logger = setup_logger(verbose=args.verbose, quiet=args.quiet)  # Pass verbosity options

    # Crear un socket UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (args.host, args.port)
    logger.info(f"Servidor escuchando en {server_address}")
    server_socket.bind(server_address)

    try:
        while True:
            handle_connection(server_socket, args.storage, logger)
    except KeyboardInterrupt:
        server_socket.close()
        logger.info("\nInterrupción detectada. El programa ha sido detenido.")

if __name__ == '__main__':
	setup_signal_handling()
	# TODO Si no existe el archivo habria que avisarle al cliente
	start_server()


