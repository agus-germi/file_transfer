import socket
import sys
import os
import signal
from utils.udp import Connection, UDPPackage, UDPFlags, UDPHeader

HOST = 'localhost'
PORT = 8088

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
connection = Connection(
    ip=HOST,
    socket=PORT,
    client_sequence=0,
    server_sequence=0
)


def connect_server():
    header = UDPHeader(0, connection.client_sequence, 0, 0)
    header.set_flag(UDPFlags.START)
    data = UDPPackage().pack(header, b"")

    # Enviar datos al servidor
    client_socket.sendto(data, ('localhost', PORT))

    # Recibir respuesta del servidor
    data, addr = client_socket.recvfrom(1024)
    data, header = UDPPackage(data).unpack()
    if header.has_ack() and header.has_start() and header.server_sequence == 0:
        print("Conexión establecida con el servidor.")
    else:
        print("Error: No se pudo establecer conexión con el servidor.")
        client_socket.close()


    


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
    
    connect_server()
        