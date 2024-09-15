import socket

# Crear un socket UDP
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Enlazar el socket a una dirección IP y puerto
server_socket.bind(('10.0.0.1', 8087))
print("Esperando datos...")

while True:
    # Recibir datos
    data, addr = server_socket.recvfrom(1024)
    print(f"Recibido de {addr}: {data.decode()}")
    
    # Enviar una respuesta
    # server_socket.sendto(b"Hola Cliente", addr)
    server_socket.sendto(data.upper(), addr)
    
