import socket

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


# Creo un socket UDP
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = ('10.0.0.1', 8087)
server_socket.bind(server_address)
output_path = 'received_file.txt'  # Ruta del archivo a guardar

try:
    recibir_archivo(server_socket, output_path)
finally:
    server_socket.close()
