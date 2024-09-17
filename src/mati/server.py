import socket
import sys
import os
import signal
from utils.udp import Connection, UDPFlags, UDPHeader, TIMEOUT, send_package, receive_package,  reject_connection

STORAGE = 'storage'

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


def handle_handshake(server_socket: socket.socket, connection: Connection, conn_key):
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
            connections[conn_key] = connection
            print("Cliente Aceptado: ", conn_key)
            # TODO Deberia cerrar conexion si no?
    except:
        print("Cliente Rechazado: ", conn_key)
    finally:
        server_socket.settimeout(None)


def check_connection(server_socket, addr, header: UDPHeader, data):
    conn_key = f"{addr[0]}-{addr[1]}"
    connection = Connection(
            ip=addr[0],
            socket=addr[1],
            client_sequence=header.client_sequence,
            server_sequence=0,
            upload=header.has_upload(),
            download=header.has_download(),
        )
    # TODO Set path
    if header.has_start() and header.client_sequence == 0:
        handle_handshake(server_socket, connection, conn_key)
    else:
        reject_connection(server_socket, connection, conn_key)



def handle_connection(server_socket):
    try:
        addr, header, data = receive_package(server_socket)
        conn_key = f"{addr[0]}-{addr[1]}"
        print("Cliente Recibido: ", conn_key)

        if not connections.get(conn_key):
            check_connection(server_socket, addr, header, data)
            return None
        
        connection = connections.get(conn_key)
        # No se inicializo la conexion y se recibio un paquete de datos
        if header.has_flag(UDPFlags.DATA) and not connection.started:
            header = UDPHeader(0, header.client_sequence, 0, 0)
            header.set_flag(UDPFlags.CLOSE)
            send_package(server_socket, connections.get(conn_key), header, b"")
            print("Cliente Desconectado: ", conn_key)
        # Se recibio un paquete de cierre
        elif header.has_flag(UDPFlags.CLOSE):
            connections.remove(conn_key)
            # TODO Habria que cerrar desde el server?
            print("Cliente Desconectado: ", conn_key)
        else:
            print(data)
            header = UDPHeader(0, header.client_sequence, 0, 0)
            header.set_flag(UDPFlags.ACK)
            send_package(server_socket, connections.get(conn_key), header, b"")
            # TODO Hasta aca se ha establecido la conexión, manejar el resto de las cosas
            pass
        #recibir_archivo(server_socket, output_path)
    except ConnectionResetError:
        print("Error: Conexión rechazada por el cliente.")


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
        

