import socket
import sys
import os
import signal
from utils.udp import Connection, UDPPackage, UDPFlags, UDPHeader

STORAGE_PATH = 'storage'

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


def check_connection(server_socket, addr, header: UDPHeader, data):
    conn_key = f"{addr[0]}-{addr[1]}"
    if header.has_start() and header.client_sequence == 0:
        connections[conn_key] = Connection(
            ip=addr,
            socket=server_socket,
            client_sequence=header.client_sequence,
            server_sequence=0
        )
        header = UDPHeader(0, header.client_sequence, 0, 0)
        header.set_flag(UDPFlags.START)
        header.set_flag(UDPFlags.ACK)
        data_to_send = UDPPackage().pack(header, b"")
        server_socket.sendto(data_to_send, addr)
        print("Cliente Aceptado: ", conn_key)
    else:
        print("Cliente Rechazado: ", conn_key)



def handle_connection(server_socket):
    fragment_size = 1020  # Tamaño del fragmento en bytes
    data, addr = server_socket.recvfrom(fragment_size + 4)
    data, header = UDPPackage(data).unpack()
    conn_key = f"{addr[0]}-{addr[1]}"
    print("Cliente Recibido: ", conn_key)

    if not connections.get(conn_key):
        check_connection(server_socket, addr, header, data)
    else:
        # TODO Hasta aca se ha establecido la conexión, manejar el resto de las cosas
        pass
    #recibir_archivo(server_socket, output_path)


def start_server():
    # Creo un socket UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('localhost', 8088)
    server_socket.bind(server_address)
    print(f"Servidor escuchando en {server_address}")
    try:
        while True:
            handle_connection(server_socket)
    except KeyboardInterrupt:
        server_socket.close()
        print("\nInterrupción detectada. El programa ha sido detenido.")


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
        

