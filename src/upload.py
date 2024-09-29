import socket
import traceback
from lib.logger import setup_logger
from lib.utils import setup_signal_handling
from lib.parser import parse_upload_args
from lib.connection import (
	Connection,
	send_package,
	receive_package,
	close_connection,
	send_data,
	send_end,
	confirm_send,
	is_data_available,
)
from lib.udp import UDPFlags, UDPHeader
from lib.constants import TIMEOUT, FRAGMENT_SIZE, SACK_WINDOW_SIZE

from collections import deque

UPLOAD = True
DOWNLOAD = False

# TODO: poner todo esto en otro lado
args = parse_upload_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)

# Crear un socket UDP
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(TIMEOUT)

connection = Connection(
	addr=(args.host, args.port),  # Usa los argumentos parseados
	sequence=0,
	download=DOWNLOAD,
	path=args.name,
)


def connect_server(protocol):
	header = UDPHeader(0, connection.sequence, 0)
	header.set_flag(UDPFlags.START)
	if DOWNLOAD:
		header.set_flag(UDPFlags.DOWNLOAD)
	if protocol == "stop_and_wait":
		header.clear_flag(UDPFlags.PROTOCOL)
	elif protocol == "sack":
		header.set_flag(UDPFlags.PROTOCOL)

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


def upload_file(dir, name):
	"""Envía un archivo al servidor en fragmentos usando UDP."""
	file_dir = f"{dir}/{name}"
	connection.sequence = 0
	with open(file_dir, "rb") as f:
		while True:
			fragment = f.read(FRAGMENT_SIZE)
			if not fragment:
				break

			send_data(client_socket, connection, fragment, sequence=connection.sequence)
			logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

			addr, header, data = receive_package(client_socket)

			if header.has_ack() and header.sequence == connection.sequence:
				logger.info(f"ACK {connection.sequence} recibido del servidor.")
				connection.sequence += 1
			else:
				logger.error(
					f"Error: ACK {connection.sequence} no recibido del servidor."
				)
				break

		send_end(client_socket, connection)
		close_connection(client_socket, connection)
		logger.info("Archivo enviado exitosamente.")


def upload_stop_and_wait(dir, name):
	"""Envía un archivo al servidor en fragmentos usando UDP."""
	file_dir = f"{dir}/{name}"

	with open(file_dir, "rb") as file:
		connection.sequence = 0
		while True:
			fragment = file.read(FRAGMENT_SIZE)
			if not fragment:
				break

			send_data(client_socket, connection, fragment, sequence=connection.sequence)
			logger.info(f"Fragmento {connection.sequence} enviado al servidor.")

			while True:
				try:
					addr, header, data = receive_package(client_socket)
					if header.has_ack() and header.sequence == connection.sequence:
						logger.info(f"ACK {connection.sequence} recibido del servidor.")
						connection.sequence += 1
						break
					else:
						logger.error(
							f"Received ACK {header.sequence} is not {connection.sequence} "
						)

				except TimeoutError:
					logger.error(
						f"ACK {connection.sequence} no recibido del servidor. Reenviando."
					)
					send_data(
						client_socket,
						connection,
						fragment,
						sequence=connection.sequence,
					)
		


def send_sack_data():
	for seq, (key, data) in enumerate(connection.fragments.items()):
		if seq >= SACK_WINDOW_SIZE or connection.window_sents > SACK_WINDOW_SIZE*2:  # Solo mandamos los primeros 8 elementos
			break
		if key > connection.sequence + 30: # Nunca haya tanta difrencia entre el puntero del server y el mio
			break

		# Print saber que segmentos quedan cuando quedan pocos
		if len(connection.fragments) < 10:
			print("FRAG: ", connection.fragments.keys())

		send_data(client_socket, connection, data, sequence=key)
		connection.window_sents += 1
		print("Enviando paquete ", key)
	
	if not connection.fragments:
		send_end(client_socket, connection)
		connection.is_active = False


def handle_ack_sack(header: UDPHeader):
	if header.has_ack():
		if header.sequence > connection.sequence:
			connection.window_sents -= header.sequence - connection.sequence
			seq = connection.sequence
			connection.sequence = header.sequence
			print("ACK recibido ", header.sequence, " Nuevo sequence: ", connection.sequence)

			for i in range(seq, header.sequence +1):
				if i in connection.fragments:
					print("Borrando fragmento ", i)
					del connection.fragments[i]
			
		else:
			sack = header.get_sequences()[1]
			for i in sack:
				print("Borrando fragmento SACK", i, " sequence: ", connection.sequence, " header " , header.sequence)
				if i in connection.fragments:
					connection.window_sents -= 1
					del connection.fragments[i]



def upload_with_sack_mati(dir, name):
	try: 
		connection.sequence = 1  # Inicia el número de secuencia en 1
		connection.path = f"{dir}/{name}"
		connection.get_fragments()
		connection.is_active = True

		send_sack_data()
		while connection.is_active:
			addr, header, data = receive_package(client_socket)
			handle_ack_sack(header)
			while is_data_available(client_socket):
				addr, header, data = receive_package(client_socket)
				handle_ack_sack(header)

			send_sack_data()
		

	except TimeoutError:
		logger.error("TIMEOUT")
	except:
		logger.error("Traceback info:\n" + traceback.format_exc())



def upload_with_sack(dir, name):
	try: 
		connection.sequence = 0  # Inicia el número de secuencia en 0
		
		file_dir = f"{dir}/{name}"
		unacked_packets, sec_num_last_packet = get_fragments_sack(file_dir)  # Diccionario para almacenar los paquetes no reconocidos <- TOTAL DE PAQUETES

		window = deque()
		
		while len(window) < SACK_WINDOW_SIZE: # Envio la cantidad que la windowSize me pe
			packet_to_send = unacked_packets[connection.sequence]
			send_data(
					client_socket,
					connection,
					packet_to_send,
					sequence=connection.sequence,
				)
			window.append(connection.sequence)
			connection.sequence += 1	

		while unacked_packets: # Mientras tengamos paquetes sin ACK (no enviados correctamente)
			client_socket.settimeout(TIMEOUT)
			try:
				_, header, _ = receive_package(client_socket)
				last_complete_secuence, sack = header.get_sequences()
				#borrar los sack correspondientes
				
				#borrar todo lo previo a last_complete 
				# index_from = 0 if last_complete_secuence < WINDOW_SIZE else last_complete_secuence - WINDOW_SIZE #esto puede ser *2
				# for i in range(index_from, last_complete_secuence):
				# 	unacked_packets.remove(i)
				

				
				#Borrar aquellos que recibi fuera de orden
				# for selected_ack in sack:
				# 	unacked_packets.remove(selected_ack)
				
				## aca recibe el paquete y tenemos que ver como hacer para enviar el siguiente moviendo la ventana acorde
				elemento_recibido = window.popleft()
				logger.info(f"elemento_recibido = {elemento_recibido}")
				logger.info(f"last_complete_secuence = {last_complete_secuence}")
				logger.info(f"WINDOW state after popping {elemento_recibido}= {window}")

				#borramos del buffer el elemento con ack
				del unacked_packets[elemento_recibido]
				
				
				if connection.sequence < sec_num_last_packet:
					#quedan elementos, mando el siguiente
					connection.sequence += 1
					window.append(connection.sequence)
					elemento_a_enviar = unacked_packets[connection.sequence]
					send_data(
						client_socket,
						connection,
						elemento_a_enviar,
						sequence=connection.sequence,
					)
				else:
					if len(window) == 0:
						return
					logger.info("No quedan elementos, esperando los ack restantes")

			except TimeoutError:
				logger.error("TIMEOUT")
				
	except:
		logger.error("Traceback info:\n" + traceback.format_exc())



def get_fragments_sack(file_dir) -> tuple:
		frag = {}
		contador = 0
		try:
			with open(file_dir, "rb") as f:
				for i, fragment in enumerate(iter(lambda: f.read(FRAGMENT_SIZE), b"")):
					frag[i] = fragment
					contador = i
		except FileNotFoundError:
			logger.error(f"Error: Archivo {file_dir} no encontrado.")
		return frag, contador
		


def handle_upload(dir, name, protocol):
	try:
		if protocol == "stop_and_wait":
			upload_stop_and_wait(dir, name)
		elif protocol == "sack":
			upload_with_sack_mati(dir, name)
		else:
			logger.error(f"Protocolo no soportado: {protocol}")
			raise ValueError(f"Protocolo no soportado: {protocol}")
		
		confirm_send(client_socket, connection, send_end)
		logger.info("Archivo enviado exitosamente.")
	except Exception as e:
		logger.error(f"Error durante el upload: {e}")
	finally:
		close_connection(client_socket, connection)


if __name__ == "__main__":
	setup_signal_handling()
	try:
		if connect_server(args.protocol):
			handle_upload(args.src, args.name, args.protocol)
	except Exception as e:
		logger.error(f"Error en main: {e}")
	finally:
		client_socket.close()

"""""
import socket
import os
import struct
import time

# Constants
PACKET_SIZE = 1024    # Adjust based on MTU
TIMEOUT = 2           # Timeout for receiving ACKs/SACKs in seconds
WINDOW_SIZE = 5       # Sliding window size (number of in-flight packets)

# Helper function to divide file into packets
def divide_file_into_packets(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    packets = [data[i:i + PACKET_SIZE] for i in range(0, len(data), PACKET_SIZE)]
    return packets

# Upload function using SACK with a sliding window
def upload_file_sack(sock, server_address, file_path):
    # Step 1: Divide the file into packets
    packets = divide_file_into_packets(file_path)
    total_packets = len(packets)
    
    # Step 2: Send the file size and total packets info to the server
    file_size = os.path.getsize(file_path)
    sock.sendto(struct.pack("!Q", file_size), server_address)
    
    print(f"Uploading '{file_path}' ({file_size} bytes) using SACK with sliding window")
    
    # Step 3: Initialize sequence number, sliding window, and ack tracking
    base = 0  # Start of the window (seq number)
    next_seq_num = 0  # Next sequence number to send
    unacked_packets = set(range(total_packets))  # Packets that haven't been acknowledged
    
    # Step 4: Set socket timeout
    sock.settimeout(TIMEOUT)
    
    # Step 5: Upload loop
    while unacked_packets:
        # Step 6: Send packets within the window
        while next_seq_num < base + WINDOW_SIZE and next_seq_num < total_packets:
            if next_seq_num in unacked_packets:
                packet_data = packets[next_seq_num]
                packet = struct.pack("!I", next_seq_num) + packet_data
                sock.sendto(packet, server_address)
                print(f"Sent packet {next_seq_num}")
            next_seq_num += 1
        
        # Step 7: Wait for SACK response or timeout
        try:
            response, _ = sock.recvfrom(1024)
            ack_type, = struct.unpack("!B", response[:1])
            
            if ack_type == 1:  # SACK response
                sack_ranges = struct.unpack("!I" * ((len(response) - 1) // 4), response[1:])
                print(f"Received SACK: {sack_ranges}")
                
                # Remove acknowledged packets from the unacked set
                for sack_num in sack_ranges:
                    if sack_num in unacked_packets:
                        unacked_packets.remove(sack_num)
                
                # Update the window base to the lowest unacknowledged packet
                if unacked_packets:
                    base = min(unacked_packets)
                else:
                    base = total_packets  # All packets acknowledged
            
        except socket.timeout:
            print("Timeout waiting for SACK, retransmitting unacknowledged packets in the window...")
            # On timeout, reset the next_seq_num to the base to resend unacknowledged packets in the window
            next_seq_num = base
    
    print("File upload complete.")

# Example usage
if __name__ == "__main__":
    server_ip = '127.0.0.1'
    server_port = 9000
    file_to_upload = 'example_file.txt'
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        server_addr = (server_ip, server_port)
        upload_file_sack(sock, server_addr, file_to_upload)
"""