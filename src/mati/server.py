import socket
import sys
import os
import signal
from utils.udp import Connection, UDPFlags, UDPHeader, send_package, receive_package,  reject_connection
from constants import HOST, PORT, TIMEOUT, STORAGE


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




