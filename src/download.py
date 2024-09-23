import socket
import sys
import os
import signal
from lib.parser import parse_download_args, configure_logging
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package, close_connection, send_ack, send_end
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

args = parse_download_args()
logger = configure_logging(args)


# Configurar la verbosidad (ejemplo de uso de verbosity)
if args.verbose:
    print("Verbosity turned on")


# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)
connection = Connection(
    addr=(args.host, args.port),
    client_sequence=0,
    server_sequence=0,
    download=DOWNLOAD,
    upload=UPLOAD,
    path=args.name
)

def connect_server():
    header = UDPHeader(0, connection.client_sequence, 0, 0)
    header.set_flag(UDPFlags.START)
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

def download_file_stop_and_wait(dst_path, file_name):
    """Recibe un archivo del servidor usando Stop & Wait."""
    full_path = os.path.join(dst_path, file_name)
    connection.client_sequence = 0
    with open(full_path, 'wb') as f:
        while True:
            try:
                addr, header, data = receive_package(client_socket)
                if header.has_flag(UDPFlags.END):
                    print("OK.")
                    break
                if header.has_data() and header.client_sequence == connection.client_sequence:
                    print(f"Fragmento {header.client_sequence} recibido del servidor.")
                    f.write(data)
                    send_ack(client_socket, connection, sequence=header.client_sequence)
                    print(f"ACK {header.client_sequence} enviado al servidor.")
                    connection.client_sequence += 1
                else:
                    print(f"Fragmento fuera de orden o duplicado. Esperado: {connection.client_sequence}, Recibido: {header.client_sequence}")
                    send_ack(client_socket, connection, sequence=connection.client_sequence - 1)
            except socket.timeout:
                print("Timeout: No se recibió el siguiente fragmento.")
                send_ack(client_socket, connection, sequence=connection.client_sequence - 1)

    send_end(client_socket, connection)
    close_connection(client_socket, connection)
    print(f"Archivo guardado exitosamente en {full_path}.")

def download_file_tcp_sack(dst_path, file_name):
    """Recibe un archivo del servidor usando un mecanismo similar a TCP con SACK."""
    full_path = os.path.join(dst_path, file_name)
    connection.client_sequence = 0
    received_fragments = {}
    expected_sequence = 0
    window_size = 5  # Tamaño de la ventana deslizante

    with open(full_path, 'wb') as f:
        while True:
            try:
                for _ in range(window_size):
                    addr, header, data = receive_package(client_socket)
                    if header.has_flag(UDPFlags.END):
                        print("Recepción del archivo completada.")
                        break
                    if header.has_data():
                        print(f"Fragmento {header.client_sequence} recibido del servidor.")
                        received_fragments[header.client_sequence] = data

                # Procesar fragmentos en orden
                while expected_sequence in received_fragments:
                    f.write(received_fragments[expected_sequence])
                    del received_fragments[expected_sequence]
                    expected_sequence += 1

                # Enviar SACK
                sack = [seq for seq in received_fragments.keys() if seq > expected_sequence]
                send_sack(client_socket, connection, expected_sequence, sack)
                print(f"SACK enviado. Esperando: {expected_sequence}, Recibidos: {sack}")

            except socket.timeout:
                print("Timeout: No se recibieron todos los fragmentos esperados.")
                send_sack(client_socket, connection, expected_sequence, list(received_fragments.keys()))

        send_end(client_socket, connection)
        close_connection(client_socket, connection)
        print(f"Archivo guardado exitosamente en {full_path}.")

def send_sack(socket, connection, expected, received):
    """Envía un SACK (Selective Acknowledgment) al servidor."""
    header = UDPHeader(0, connection.client_sequence, 0, 0)
    header.set_flag(UDPFlags.ACK)
    sack_data = f"{expected},{','.join(map(str, received))}".encode()
    send_package(socket, connection, header, sack_data)

def limpiar_recursos(signum, frame):
    print(f"Recibiendo señal {signum}, limpiando recursos...")
    sys.exit(0)

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
            if DOWNLOAD:
                # Elegir entre Stop & Wait y TCP-like SACK
                use_tcp_sack = True  # Cambiar a False para usar Stop & Wait
                if use_tcp_sack:
                    download_file_tcp_sack(args.dst, args.name)
                else:
                    download_file_stop_and_wait(args.dst, args.name)
        except CloseConnectionException as e:
            print(e)
        finally:
            client_socket.close()