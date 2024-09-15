import socket
import signal
import sys
import os


# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Dirección y puerto del servidor
server_address = ('10.0.0.1', 8087)

def limpiar_recursos(signum, frame):
    """Función para manejar señales y limpiar recursos"""
    print(f"Recibiendo señal {signum}, limpiando recursos...")
    client_socket.close()  # Cerrar el socket
    sys.exit(0)  # Salgo del programa con código 0 (éxito)


def enviar_archivo(client_socket, archivo_path, server_address):
    """Envía un archivo al servidor en fragmentos usando UDP."""
    fragment_size = 512  # Tamaño del fragmento en bytes
    file_size = os.path.getsize(archivo_path)
    
    with open(archivo_path, 'rb') as f:
        sequence_number = 0
        while True:
            fragment = f.read(fragment_size)
            if not fragment:
                break
            # Envio fragmento de tamaño definido con su numero de secuencia
            client_socket.sendto(sequence_number.to_bytes(4, 'big') + fragment, server_address)
            sequence_number += 1
            # Espero confirmación del servidor
            ack, _ = client_socket.recvfrom(1024)
            if ack != b'ACK':
                print("Error: Confirmación no recibida.")
                break
            else: print(f'ACK {sequence_number - 1} recibido exitosamente')
        
        client_socket.sendto(b'END', server_address)
        print("Archivo enviado exitosamente.")


# Capturo señales de interrupción
signal.signal(signal.SIGINT, limpiar_recursos)  # Ctrl+C
signal.signal(signal.SIGTERM, limpiar_recursos)  # kill
signal.signal(signal.SIGQUIT, limpiar_recursos)  # Ctrl+\
signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
signal.signal(signal.SIGHUP, limpiar_recursos)  # hangup


# Creo un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = ('10.0.0.1', 8087)
archivo_path = 'archivo.txt'  # Ruta del archivo a enviar

try:
    enviar_archivo(client_socket, archivo_path, server_address)
finally:
    client_socket.close()