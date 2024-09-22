import socket
import sys
import os
import signal
from lib.parser import parse_server_args
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package,  reject_connection, close_connection, send_ack
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

			

def recibir_archivo(server_socket, output_path):
	"""Recibe un archivo en fragmentos desde un cliente usando UDP."""
	fragment_size = 512  # Tamaño del fragmento en bytes
	received_fragments = {}
	
	while True:
		data, addr = server_socket.recvfrom(fragment_size + 4)
		
		if data == b'END':  # Señal de que el cliente completo el envio del archivo
			print("Recepción de archivo completada.")
			break
		
		sequence_number = int.from_bytes(data[:4], 'big')
		fragment = data[4:]
		
		if sequence_number in received_fragments:
			print(f"Fragmento {sequence_number} ya recibido.")
			continue
		
		# Guardo el fragmento en el diccionario
		received_fragments[sequence_number] = fragment
		
		# Envio confirmación al cliente
		server_socket.sendto(b'ACK', addr)

	# Escribo el archivo reconstruido
	with open(output_path, 'wb') as f:
		for i in sorted(received_fragments.keys()):
			f.write(received_fragments[i])
	print("Archivo recibido y guardado exitosamente.")


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



def handle_handshake(server_socket: socket.socket, connection: Connection):
	header = UDPHeader(0, connection.client_sequence, 0, 0)
	header.set_flag(UDPFlags.START)
	header.set_flag(UDPFlags.ACK)
	try:
		#time.sleep(3)
		send_package(server_socket, connection, header, b"")
		server_socket.settimeout(TIMEOUT)
		addr, header, data = receive_package(server_socket)
		if header.has_ack() and header.has_start():
			connection.started = True
			connections[connection.addr] = connection
			print("Cliente Aceptado: ", connection.addr)
			# TODO Deberia cerrar conexion si no?
	except:
		print("Cliente Rechazado: ", connection.addr)
	finally:
		server_socket.settimeout(None)


def check_connection(server_socket, addr, header: UDPHeader, data: bytes):
	connection = Connection(
			addr=addr,
			client_sequence=header.client_sequence,
			server_sequence=0,
			upload= not header.has_download(),
			download=header.has_download(),
			path=data.decode()
		)
	# Arriba no se guarda bien por algun motivo?
	connection.path = data

	print("Path: ", data.decode(), "| Upload: ", connection.upload, "| Download: ", connection.download)
	# TODO Set path
	if header.has_start() and header.client_sequence == 0 and data.decode() != "":
		handle_handshake(server_socket, connection)
	else:
		reject_connection(server_socket, connection)



def handle_connection(server_socket,server_storage):
	try:
		addr, header, data = receive_package(server_socket)
		print("Cliente Recibido: ", addr)

		if not connections.get(addr):
			check_connection(server_socket, addr, header, data)
			return None
		
		connection = connections.get(addr)
		# No se inicializo la conexion y se recibio un paquete de datos
		if header.has_flag(UDPFlags.DATA) and not connection.started:
			close_connection(server_socket, connection)
		# Se recibio un paquete de cierre
		elif header.has_flag(UDPFlags.CLOSE):
			connections.pop(addr)
			# TODO Habria que cerrar desde el server?
			print("Cliente Desconectado: ", addr)
		
		# Aquí es donde debes manejar el inicio de la recepción de datos
		elif connection.started and header.has_flag(UDPFlags.DATA):
			
			#TODO Modularizar en una funcion
			print("Entre a flujo de recibir")

			fragment_size = FRAGMENT_SIZE  # Tamaño del fragmento en bytes
			received_fragments = {}

			sequence_number = header.client_sequence
			print(f"Recibi paquete {sequence_number}")

			# Almacenar el fragmento
			received_fragments[sequence_number] = data
			print(f"Envio Ack {sequence_number}")
			send_ack(server_socket, connection)  # Enviar ACK después de almacenar
			
			while True:
				addr, header, data = receive_package(server_socket)

				sequence_number = header.client_sequence
				print(f"Recibi paquete {sequence_number}")
				header.client_sequence = sequence_number
				print(f"Envio Ack {sequence_number}")

				header.set_flag(UDPFlags.ACK)
				header.client_sequence = sequence_number
				send_package(server_socket, connection, header, b"")

				if sequence_number in received_fragments:
					print(f"Fragmento {sequence_number} ya recibido.")
					
					header.set_flag(UDPFlags.ACK)
					header.client_sequence = sequence_number
					return  # Salir para evitar procesar un fragmento ya recibido

				if header.has_flag(UDPFlags.END):  # Señal de que el cliente completo el envio del archivo
					print("Recepción de archivo completada.")
					break

				header.set_flag(UDPFlags.ACK)
				header.client_sequence = sequence_number
			
			
			# Escribir el archivo reconstruido
			output_path = os.path.join(server_storage + connection.path.decode())  # Define la ruta de salida
			print(connection.path)
			print(output_path)
			with open(output_path, 'wb') as f:
				for i in sorted(received_fragments.keys()):
					f.write(received_fragments[i])
			print("Archivo recibido y guardado exitosamente.")
		
		else:
			if header.has_flag(UDPFlags.DATA):
				connection.client_sequence = header.client_sequence
				send_ack(server_socket, connection)

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


