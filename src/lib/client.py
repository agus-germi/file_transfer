import socket
import sys
import os
import signal
from lib.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package, close_connection
from lib.udp import CloseConnectionException 
from lib.constants import TIMEOUT, HOST, PORT, PATH, MAX_RETRIES
from lib.parser import parse_upload_args, configure_logging

DOWNLOAD = True

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)
connection = Connection(
    addr=(HOST, PORT),
    sequence=0,
    download=DOWNLOAD,
    upload=not DOWNLOAD,
    path = PATH
)

# This function tries to establish a connection with the server.
def connect_server():
    # This function tries to establish a connection with the server.
    
    header = UDPHeader(0, connection.sequence, 0)
    header.set_flag(UDPFlags.START)
    if DOWNLOAD:
        header.set_flag(UDPFlags.DOWNLOAD)
    try:
        send_package(client_socket, connection, header, PATH.encode())
        addr, header, data = receive_package(client_socket)

        # si se recibio un header con ack, start y sequence = 0
        if header.has_ack() and header.has_start() and header.sequence == 0:
            #le mandamos un ack
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