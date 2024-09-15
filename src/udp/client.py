import socket
import signal
import sys

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Dirección y puerto del servidor
server_address = ('10.0.0.1', 8087)

def limpiar_recursos(signum, frame):
    """Función para manejar señales y limpiar recursos"""
    print(f"Recibiendo señal {signum}, limpiando recursos...")
    client_socket.close()  # Cerrar el socket
    sys.exit(0)  # Salir del programa con código 0 (éxito)

# Capturar señales de interrupción (Ctrl+C) y suspensión (Ctrl+Z)
signal.signal(signal.SIGINT, limpiar_recursos)  # Ctrl+C
signal.signal(signal.SIGTERM, limpiar_recursos)  # kill
signal.signal(signal.SIGQUIT, limpiar_recursos)  # Ctrl+\
signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
signal.signal(signal.SIGHUP, limpiar_recursos)  # hangup

try:
    while True:
        # Solicitar entrada del usuario
        message = input("Ingrese el mensaje para enviar al servidor (escriba 'exit' para salir): ")
        
        if message.lower() == 'exit':
            print("Saliendo...")
            break
        
        # Enviar datos al servidor
        client_socket.sendto(message.encode(), server_address)
        
        # Recibir respuesta del servidor
        data, addr = client_socket.recvfrom(1024)
        print(f"Recibido del servidor: {data.decode()}")

finally:
    client_socket.close()
