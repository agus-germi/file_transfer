import socket
import sys
import os
import signal
from lib.parser import parse_download_args
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package, close_connection, send_end, send_ack
from lib.udp import CloseConnectionException
from lib.constants import MAX_RETRIES, TIMEOUT, FRAGMENT_SIZE

# > python download -h
# usage : download [ - h ] [ - v | -q ] [ - H ADDR ] [ - p PORT ] [ - d FILEPATH ] [ - n FILENAME ]
# < command description >
# optional arguments :
# -h , -- help show this help message and exit
# -v , -- verbose increase output verbosity
# -q , -- quiet decrease output verbosity
# -H , -- host server IP address
# -p , -- port server port
# -d , -- dst destination file path
# -n , -- name file name

UPLOAD = False
DOWNLOAD = True

# Parsear los argumentos usando la función importada
args = parse_download_args()

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
    path = args.name
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


def download_file():
    fragments = {}
    is_running = True

    while is_running:
        addr, header, data = receive_package(client_socket)
        if header.has_data() and header.sequence == connection.sequence:
            if header.sequence not in fragments:
                fragments[header.sequence] = data
                connection.sequence += 1
                print(f"Fragmento {header.sequence} recibido del servidor.")
            else:
                 print(f"Fragmento {header.sequence} ya recibido.")
                        
            send_ack(client_socket, connection, sequence=header.sequence)

        elif header.has_end():
            is_running = False
        elif header.has_close():
            is_running = False
            if len(data) > 0:
                print(f"Cierre del servidor: [{data.decode()}]")



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
            download_file()
            close_connection(client_socket, connection)
        except CloseConnectionException as e:
            print(e)
        finally:
            client_socket.close()