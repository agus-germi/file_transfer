import struct
import socket
import threading
import queue
import os
import traceback

from lib.constants import TIMEOUT, FRAGMENT_SIZE, PACKAGE_SIZE, MAX_RETRIES, WINDOW_SIZE
from lib.udp import UDPHeader, UDPFlags, UDPPackage
from lib.logger import setup_logger

logger = setup_logger(verbose=False, quiet=False)

#0-10  [010]
#(10   [111])
# 10   [100]

class BaseConnection:
	"""Clase base que contiene atributos y comportamientos comunes de conexiones."""

	def __init__(self, addr, path=None, sequence=0, download=False):
		self.addr = addr
		self.path = path
		self.sequence = sequence
		self.is_active = False
		self.download = download
		self.upload = not download
		self.fragments = {}
		self.retrys = 0
		
		#sack implementation
		self.buffer = set() #Ventana donde bufferear los sack
		self.last_acumulated_secuence = -1


	def __repr__(self):
		return f"Cliente ({self.addr})"


	def save_file(self):
		output_path = self.path
		dir = self.path.split("/")[0]
		if not os.path.exists(dir):
			os.makedirs(dir)

		with open(output_path, "wb") as f:
			for i in sorted(self.fragments.keys()):
				f.write(self.fragments[i])
		print(f"Archivo guardado en {output_path}")


	def get_fragments(self):
		try:
			with open(self.path, "rb") as f:
				for i, fragment in enumerate(iter(lambda: f.read(FRAGMENT_SIZE), b"")):
					self.fragments[i] = fragment
			print("Fragments listos para enviar ", len(self.fragments))
		except FileNotFoundError:
			logger.error(f"Error: Archivo {self.path} no encontrado.")
			self.is_active = False
			close_connection(self.socket, self, "Archivo no encontrado.")



class ClientConnection(BaseConnection, threading.Thread):
	"""Clase que maneja la conexión y comunicación con un cliente específico en UDP."""
	
	def __init__(self, socket: socket.socket, addr, path, download=False, protocol=""):
		super().__init__(addr, path, download=download)
		threading.Thread.__init__(self)
		self.socket = socket
		self.message_queue = queue.Queue()
		self.ttl = 0


	def run(self):
		if self.download:
			self.get_fragments()
			self.send_data()

		while self.is_active:
			try:
				message = self.message_queue.get(timeout=2)

				if self.upload:
					header = message["header"] 
					if header.has_data():
						if header.has_sack():
							#recibo de datos sack
							self.receive_data_sack(message)
						else:
							#recibo de datos s a w
							self.receive_data_stop_wait(message)

					elif message["header"].has_end():
						send_end_confirmation(self.socket, self)
						self.save_file()
						self.is_active = False
				else:
					self.send_data(message)

			except queue.Empty:
				logger.warning(f"Cliente {self.addr} no ha enviado mensajes recientes.")
				if self.ttl >= 10:
					logger.warning(f"Cliente {self.addr} inactivo por 5 intentos.")
					self.is_active = False
				elif self.ttl <= MAX_RETRIES and self.download:
					self.send_data()

				self.ttl += 1
			except Exception as e:
				logger.error(f"Error con {self.addr}: {e}")
				logger.error("Traceback info:\n" + traceback.format_exc())
				self.is_active = False


	def put_message(self, message):
		"""Agrega un mensaje a la cola para ser procesado por el hilo."""
		self.message_queue.put(message)


	def receive_data_stop_wait(self, message):
		if message["header"].sequence in self.fragments:
			send_ack(self.socket, self, message["header"].sequence)
			return

		self.sequence = message["header"].sequence
		logger.info(f"Recibido desde {self}: [{self.sequence}]")
		self.fragments[self.sequence] = message["data"]
		send_ack(self.socket, self)


	def receive_data_sack(self, message):
		msg_secuence = message["header"].sequence
		logger.info(f"Recibido desde {self}: [{msg_secuence}]")
		
		if msg_secuence not in self.fragments:
			self.fragments[msg_secuence] = message["data"]
		
		primer_paquete_faltante = self.last_acumulated_secuence + 1
		if msg_secuence == primer_paquete_faltante:
			#borr0 toda la tanda de paquetes que ya estan en el buffer
			self.last_acumulated_secuence = msg_secuence
			index_buff_secuence = self.last_acumulated_secuence + 1
			while index_buff_secuence in self.buffer:
				self.last_acumulated_secuence = index_buff_secuence 
				self.buffer.discard(index_buff_secuence)
				index_buff_secuence += 1
				if len(self.buffer) > WINDOW_SIZE:
					raise Exception("Buffer lleno")
				
		elif msg_secuence > primer_paquete_faltante:
			logger.warning(f"Fragmento {msg_secuence} recibido fuera de orden.")
			self.buffer.add(msg_secuence) 

		buffer_to_list = list(self.buffer)
		sack_list = convert_to_sack(self.last_acumulated_secuence, buffer_to_list) #TODO si pasa test, no lo mandamos ordenado
		logger.info(f"sack list {format(sack_list, '032b')}, buffer {buffer_to_list}")
		
		logger.info(f"Le digo que tengo hasta {self.last_acumulated_secuence} y ademas {buffer_to_list}")
		msg_secuence = self.last_acumulated_secuence
		send_ack_sack(self.socket, self, msg_secuence, sack_list)




	def send_data(self, message=None):
		if message and message["header"].has_ack():
			sequence = message["header"].sequence
			logger.info(f"ACK {sequence} recibido desde {self}")
			if sequence in self.fragments:
				self.fragments.pop(sequence)
		if self.fragments:
			key = next(iter(self.fragments))
			data = self.fragments[key]
			send_data(self.socket, self, data, sequence=key)
		else:
			send_end(self.socket, self)
			self.is_active = False



class Connection(BaseConnection):
	"""Clase que maneja conexiones genéricas."""

	def __init__(self, addr, sequence=None, download=False, path=None):
		super().__init__(addr, path, sequence, download)


class CloseConnectionException(Exception):
	def __init__(self, mensaje, codigo_error):
		super().__init__(mensaje)
		self.codigo_error = codigo_error



def send_package(socket: socket.socket, connection: Connection, header, data):
	package = UDPPackage().pack(header, data)
	socket.sendto(package, connection.addr)


def send_data(
	socket: socket.socket, connection: Connection, data: bytes, sequence=None, is_sack=False
):
	seq = sequence if sequence else connection.sequence
	header = UDPHeader(0, seq, 0)
	header.set_flag(UDPFlags.DATA)
	if is_sack: header.set_flag(UDPFlags.SACK)
	package = UDPPackage().pack(header, data)
	socket.sendto(package, connection.addr)


def send_ack(socket: socket.socket, connection: Connection, sequence=None):
	seq = sequence if sequence else connection.sequence
	header = UDPHeader(0, seq, 0)
	header.set_flag(UDPFlags.ACK)
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def send_ack_sack(socket: socket.socket, connection: Connection, sequence, sack):
	
	# header = UDPHeader(0, connection.sequence, 0)
	# header.set_flag(UDPFlags.ACK)
	# #header.set_flag(UDPFlags.SACK)

	# package = UDPPackage().pack(header, b"")
	# socket.sendto(package, connection.addr)
	seq = sequence if sequence else connection.sequence
	header = UDPHeader(0, seq, 0)
	header.set_flag(UDPFlags.ACK)
	header.set_flag(UDPFlags.SACK)
	
	header.sack = sack
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def send_end(socket: socket.socket, connection: Connection):
	header = UDPHeader(0, connection.sequence, 0)
	header.set_flag(UDPFlags.END)
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def send_end_confirmation(socket: socket.socket, connection: Connection):
	header = UDPHeader(0, connection.sequence, 0)
	header.set_flag(UDPFlags.END)
	header.set_flag(UDPFlags.ACK)
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def send_start_confirmation(socket: socket.socket, connection: Connection):
	header = UDPHeader(0, 0, 0)
	header.set_flag(UDPFlags.START)
	header.set_flag(UDPFlags.ACK)
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def receive_package(socket: socket.socket):

	data, addr = socket.recvfrom(PACKAGE_SIZE)
	data, header = UDPPackage(data).unpack()
	return addr, header, data


def close_connection(socket: socket.socket, connection: Connection, data=""):
	header = UDPHeader(0, 0, 0)
	header.set_flag(UDPFlags.CLOSE)
	logger.info("Enviando paquete de cierre ")
	send_package(socket, connection, header, data.encode())


def reject_connection(socket: socket.socket, connection: Connection):
	"""Intenta cerrar la conexión y manejar cualquier error."""
	try:
		close_connection(socket, connection)
	except Exception:
		pass
	finally:
		logger.info(f"Cliente Rechazado: {connection.addr}")
		

# Commont to clients
def confirm_endfile(socket, connection):
	for i in range(3):
		try:
			send_end(socket, connection)
			addr, header, data = receive_package(socket)
			if header.has_end() and header.has_ack():
				break
		except TimeoutError:
			logger.warning(
				"Tiempo de espera agotado al confirmar el final del archivo."
			)

def convert_to_sack(last_complete_seq, packet_sequences):
	sack_mask = 0  
	for packet_sequence in packet_sequences:
		if packet_sequence == 0:
			continue  

		sequence = packet_sequence - last_complete_seq
		if 1 <= sequence < 32:  
			sack_mask |= 1 << (31 - sequence)  
	return sack_mask
