import argparse
import socket

def limpiar_recursos(signum, frame):
    print(f"Recibiendo señal {signum}, limpiando recursos...")
    sys.exit(0)  # Salgo del programa con código 0 (éxito)

def handle_handshake(server_socket: socket.socket, connection: Connection):
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
            connections[connection.addr] = connection
            print("Cliente Aceptado: ", connection.addr)
            # TODO Deberia cerrar conexion si no?
    except:
        print("Cliente Rechazado: ", connection.addr)
    finally:
        server_socket.settimeout(None)

def check_connection(server_socket, addr, header: UDPHeader, data: bytes):
    connection = Connection(
            addr=addr,
            client_sequence=header.client_sequence,
            server_sequence=0,
            upload= not header.has_download(),
            download=header.has_download(),
            path=data.decode()
        )
    print("Path: ", data.decode())
    # TODO Set path
    if header.has_start() and header.client_sequence == 0 and data.decode() != "":
        handle_handshake(server_socket, connection)
    else:
        reject_connection(server_socket, connection)


connections = {}

def handle_connection(server_socket):
    try:
        addr, header, data = receive_package(server_socket)
        print("Cliente Recibido: ", addr)

        # si no hay conexion, hace el chequeo
        if not connections.get(addr):
            check_connection(server_socket, addr, header, data)
            return None
        connection = connections.get(addr)

        # No se inicializo la conexion y se recibio un paquete de datos
        if header.has_flag(UDPFlags.DATA) and not connection.started: 
            header = UDPHeader(0, header.client_sequence, 0, 0)
            header.set_flag(UDPFlags.CLOSE)
            send_package(server_socket, connections.get(addr), header, b"")
            print("Cliente Desconectado: ", addr)

        # Se recibio un paquete de cierre
        elif header.has_flag(UDPFlags.CLOSE):
            connections.remove(addr)
            # TODO Habria que cerrar desde el server?
            print("Cliente Desconectado: ", addr)
        else:
            print(data)
            header = UDPHeader(0, header.client_sequence, 0, 0)
            header.set_flag(UDPFlags.ACK)
            send_package(server_socket, connections.get(addr), header, b"")
            # TODO Hasta aca se ha establecido la conexión, manejar el resto de las cosas
            pass
        #recibir_archivo(server_socket, output_path)
    except ConnectionResetError:
        print("Error: Conexión rechazada por el cliente.")



def start_server():
    # Creo un socket UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (HOST, PORT)
    server_socket.bind(server_address)
    print(f"Servidor escuchando en {server_address}")
    try:
        while True:
            handle_connection(server_socket)
    except KeyboardInterrupt:
        server_socket.close()
        print("\nInterrupción detectada. El programa ha sido detenido.")



def main():
    # Capturo señales de interrupción
    signal.signal(signal.SIGINT, limpiar_recursos)  # Ctrl+C
    signal.signal(signal.SIGTERM, limpiar_recursos)  # kill
    signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
    if os.name != 'nt':  # Windows 
        signal.signal(signal.SIGQUIT, limpiar_recursos)  # Ctrl+\
        signal.signal(signal.SIGABRT, limpiar_recursos)  # abort
        signal.signal(signal.SIGHUP, limpiar_recursos)  # hangup
    
    args = parse_server_args()
    logger = configure_logging(args)
    logger.info(f"Starting server {args.host}:{args.port}")
    
    start_server()


if __name__ == "__main__":
    main()




