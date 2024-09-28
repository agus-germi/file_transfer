import socket
import sys
import os
import signal
from lib.parser import parse_download_args
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.connection import Connection, CloseConnectionException, send_package, receive_package, close_connection, send_end, send_ack, confirm_endfile
from lib.udp import UDPFlags, UDPHeader
from lib.constants import MAX_RETRIES, TIMEOUT, FRAGMENT_SIZE


UPLOAD = False
DOWNLOAD = True

# TODO: poner todo esto en otro lado
args = parse_download_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)


# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
	addr=(args.host, args.port),  # Usa los argumentos parseados
	sequence=0,
	download=DOWNLOAD,
	path = args.name
)


def connect_server():
	header = UDPHeader(0, connection.sequence, 0)
	header.set_flag(UDPFlags.START)
	if DOWNLOAD:
		header.set_flag(UDPFlags.DOWNLOAD)
	try:
		send_package(client_socket, connection, header, connection.path.encode())
		addr, header, data = receive_package(client_socket)

		if header.has_ack() and header.has_start() and header.sequence == 0:
			header.set_flag(UDPFlags.ACK)
			send_package(client_socket, connection, header, b"")
			logger.info("Conexión establecida con el servidor.")
			return True
		else:
			logger.error("Error: No se pudo establecer conexión con el servidor.")
			return False
	except ConnectionResetError:
		logger.error("Error: Conexión rechazada por el servidor.")
		return False
	except socket.timeout:
		logger.error("Error: No se pudo establecer conexión con el servidor.")
		return False


def download_stop_and_wait():
	connection.is_active  = True

	while connection.is_active:
		try:
			addr, header, data = receive_package(client_socket)
			if header.has_data():
				if header.sequence not in connection.fragments:
					connection.fragments[header.sequence] = data
					connection.sequence = header.sequence
					print(f"Fragmento {header.sequence} recibido del servidor.")
				else:
					print(f"Fragmento {header.sequence} ya recibido.")
											
				send_ack(client_socket, connection, sequence=header.sequence)
				print("Se envio ACK ", header.sequence)

			# Se recibio por completo el archivo
			elif header.has_end():
				connection.is_active = False
				connection.save_file()
				# TODO Enviar confirmacion de fin de archivo
			
			# Se cierra conexion desde el servidor
			elif header.has_close():
				connection.is_active = False
				if len(data) > 0:
					print(f"Cierre del servidor: [{data.decode()}]")
					raise ValueError(f"Archivo inexistente en Servidor")
		except ConnectionResetError:
			logger.error("Error: Conexion perdida")
		except socket.timeout:
			send_ack(client_socket, connection, sequence=header.sequence)
			logger.warning(f"Reenviando ACK {header.sequence}")
			if connection.retrys > MAX_RETRIES:
				# TODO Nunca se sube el retries
				return False

def download_with_sack():
    connection.is_active = True
    expected_sequence = 0
    received_out_of_order = {}

    while connection.is_active:
        try:
            addr, header, data = receive_package(client_socket)
            
            if header.has_data():
                if header.sequence == expected_sequence:
                    # Procesar el fragmento esperado
                    connection.fragments[header.sequence] = data
                    print(f"Fragmento {header.sequence} recibido del servidor.")
                    
                    # Actualizar el número de secuencia esperado
                    expected_sequence += 1
                    
                    # Procesar fragmentos almacenados fuera de orden
                    while expected_sequence in received_out_of_order:
                        connection.fragments[expected_sequence] = received_out_of_order.pop(expected_sequence)
                        expected_sequence += 1
                
                elif header.sequence > expected_sequence:
                    # Almacenar fragmento fuera de orden
                    received_out_of_order[header.sequence] = data
                    print(f"Fragmento {header.sequence} recibido fuera de orden.")
                
                # Preparar y enviar SACK al servidor
                sack_header = UDPHeader(0, expected_sequence - 1, 0)
                sack_header.set_flag(UDPFlags.ACK)
                sack_header.set_flag(UDPFlags.SACK)
                
                # Configurar el campo SACK de 32 bits
                for i in range(32):
                    if (expected_sequence + i) in received_out_of_order:
                        sack_header.sack |= (1 << (31 - i))
                
                send_package(client_socket, connection, sack_header, b"")
                print(f"SACK enviado. Último ACK: {expected_sequence - 1}, SACK: {bin(sack_header.sack)[2:].zfill(32)}")

            elif header.has_end():
                connection.is_active = False
                connection.save_file()
                send_end_confirmation(client_socket, connection)
                print("Archivo recibido completamente.")
            
            elif header.has_close():
                connection.is_active = False
                if data:
                    print(f"Cierre del servidor: [{data.decode()}]")
                    raise ValueError("Archivo inexistente en Servidor")

        except socket.timeout:
            # Manejo de tiempo de espera: reenviar el último SACK
            sack_header = UDPHeader(0, expected_sequence - 1, 0)
            sack_header.set_flag(UDPFlags.ACK)
            sack_header.set_flag(UDPFlags.SACK)
            
            for i in range(32):
                if (expected_sequence + i) in received_out_of_order:
                    sack_header.sack |= (1 << (31 - i))
            
            send_package(client_socket, connection, sack_header, b"")
            print(f"Timeout. Reenviando SACK. Último ACK: {expected_sequence - 1}, SACK: {bin(sack_header.sack)[2:].zfill(32)}")
            
            connection.retrys += 1
            if connection.retrys > MAX_RETRIES:
                print("Número máximo de reintentos alcanzado. Cerrando conexión.")
                return False

    return True




def handle_download(protocol):
	if protocol == "stop_and_wait":
		download_stop_and_wait()
	elif protocol == "sack":
		download_with_sack()
	else:
		logger.error(f"Protocolo no soportado: {protocol}")
		raise ValueError(f"Protocolo no soportado: {protocol}")

	#confirm_endfile(client_socket, connection)
	logger.info("Archivo recibido exitosamente.")
	
	try:
		pass
	except Exception as e:
		logger.error(f"Error durante el download: {e}")
	finally:
		close_connection(client_socket, connection)


if __name__ == "__main__":
	setup_signal_handling()
	try:
		if connect_server():
			connection.path = f"{args.dst}/{args.name}"
			handle_download(args.protocol)
	except ValueError as e:
		logger.error(e)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		client_socket.close()
