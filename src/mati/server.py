import socket

STORAGE_PATH = 'storage'

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




def handle_connection(server_socket):
    fragment_size = 1020  # Tamaño del fragmento en bytes
    received_fragments = {}
    output_path = 'received_file.txt'  # Ruta del archivo a guardar
    data, addr = server_socket.recvfrom(fragment_size + 4)
    print("Cliente conectado.")
    print(f"Recibido del cliente: {data.decode()}")
    print(f"Recibido del cliente: {addr}")

    #recibir_archivo(server_socket, output_path)


def start_server():
    # Creo un socket UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('localhost', 8087)
    server_socket.bind(server_address)
    print(f"Servidor escuchando en {server_address}")
    try:
        while True:
            handle_connection(server_socket)
    except KeyboardInterrupt:
        server_socket.close()
        print("\nInterrupción detectada. El programa ha sido detenido.")


if __name__ == '__main__':
        start_server()
        

"""
Init del cliente:
Protocolo
Accion (Download - Upload)

Encabezado:
ID para identificar el cliente? O con la IP es suficiente? DUDA
Numero de secuencia
ACK
Data





"""