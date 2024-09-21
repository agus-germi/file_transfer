import socket
import sys
import os
import signal
from lib.parser import parse_upload_args
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package, close_connection
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


def send_data_stop_and_wait():
    for i in range(1, 6):
        data = f"Mensaje {i}".encode()
        header = UDPHeader(0, connection.client_sequence, 0, len(data))
        header.set_flag(UDPFlags.DATA)

        ack_received = False
        retry_count = 0

        while not ack_received and retry_count < MAX_RETRIES:
            try:
                send_package(client_socket, connection, header, data)
                print(f"Mensaje {i} enviado al servidor. Intento {retry_count + 1}.")
                addr, header, data = receive_package(client_socket)

                if header.has_close():
                    raise CloseConnectionException("El servidor cerró la conexión.", 1)
                # Verificar si se recibió el ACK
                if header.has_ack() and header.client_sequence == connection.client_sequence:
                    connection.client_sequence += 1
                    print(f"ACK {i} recibido del servidor.")
                    ack_received = True  # Salir del bucle si se recibió el ACK
                else:
                    print(f"Error: ACK {i} no recibido correctamente.")
                    retry_count += 1

            except socket.timeout:
                # Si no se recibe el ACK dentro del timeout
                retry_count += 1
                print(f"Timeout: No se recibió ACK {i}, reintentando ({retry_count}/{MAX_RETRIES})...")
        
        if not ack_received:
            print(f"Error: ACK {i} no se recibió después de {MAX_RETRIES} intentos.")
            close_connection(client_socket, connection)
            break  # Terminar el bucle si no se recibe el ACK después de varios intentos


def send_data():
    for i in range(1, 6):
        data = f"Mensaje {i}".encode()
        header = UDPHeader(0, connection.client_sequence, 0, len(data))
        header.set_flag(UDPFlags.DATA)
        send_package(client_socket, connection, header, data)
        print(f"Mensaje {i} enviado al servidor.")
        addr, header, data = receive_package(client_socket)
        if header.has_ack() and header.client_sequence == connection.client_sequence:
            connection.client_sequence += 1
            print(f"ACK {i} recibido del servidor.")
        else:
            print(f"Error: ACK {i} no recibido del servidor.")
            break

def enviar_archivo(client_socket, archivo_path, server_address):
    """Envía un archivo al servidor en fragmentos usando UDP."""
    fragment_size = FRAGMENT_SIZE  # Tamaño del fragmento en bytes
    
    connection.client_sequence = 0
    with open(archivo_path, 'rb') as f:
        while True:
            fragment = f.read(fragment_size)
            if not fragment:
                break

            # Enviar fragmento de tamaño definido con su número de secuencia
            header = UDPHeader(0, connection.client_sequence, 0, len(fragment))
            header.set_flag(UDPFlags.DATA)

            send_package(client_socket, connection, header, fragment)
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
        
        header.set_flag(UDPFlags.END)
        header.clear_flag(UDPFlags.DATA)
        send_package(client_socket, connection, header, fragment)
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
                enviar_archivo(client_socket, args.src, connection.addr)
        except CloseConnectionException as e:
            print(e)
        finally:
            client_socket.close()
            