import socket
import sys
import os
import signal
from utils.udp import Connection, UDPFlags, UDPHeader, MAX_RETRIES, TIMEOUT, send_package, receive_package, close_connection
from utils.udp import CloseConnectionException
from lib.constants import HOST, PORT

DOWNLOAD = True

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)
connection = Connection(
    ip=HOST,
    socket=PORT,
    client_sequence=0,
    server_sequence=0
)

def connect_server():
    header = UDPHeader(0, connection.client_sequence, 0, 0)
    header.set_flag(UDPFlags.START)
    header.set_flag(UDPFlags.DOWNLOAD if DOWNLOAD else UDPFlags.UPLOAD)

    try:
        send_package(client_socket, connection, header, b"")
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
            if DOWNLOAD:
                send_data_stop_and_wait()
        except CloseConnectionException as e:
            print(e)
        finally:
            client_socket.close()

        