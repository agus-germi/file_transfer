import socket

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Enviar datos al servidor
client_socket.sendto(b"Hola Servidor", ('localhost', 8087))
client_socket.sendto(b"Hola Servidor2", ('localhost', 8087))
client_socket.sendto(b"Hola Servidor3", ('localhost', 8087))

# Recibir respuesta del servidor
#data, addr = client_socket.recvfrom(1024)
#print(f"Recibido del servidor: {data.decode()}")

client_socket.close()