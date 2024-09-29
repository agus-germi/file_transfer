import struct
import socket
import threading
import queue
import os

from lib.constants import TIMEOUT, FRAGMENT_SIZE, PACKAGE_SIZE, MAX_RETRIES, SACK_WINDOW_SIZE
from lib.udp import UDPHeader, UDPFlags, UDPPackage
from lib.logger import setup_logger

logger = setup_logger(verbose=False, quiet=False)



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
		logger.info(f"Archivo guardado en {output_path}")


	def get_fragments(self):
		try:
			with open(self.path, "rb") as f:
				for i, fragment in enumerate(iter(lambda: f.read(FRAGMENT_SIZE), b"")):
					self.fragments[i+1] = fragment
			print("Fragments listos para enviar ", len(self.fragments))
		except FileNotFoundError:
			logger.error(f"Error: Archivo {self.path} no encontrado.")
			self.is_active = False
			close_connection(self.socket, self, "Archivo no encontrado.")



class ClientConnection(BaseConnection, threading.Thread):
	def __init__(self, socket: socket.socket, addr, path, download=False, protocol=""):
		super().__init__(addr, path, download=download)
		threading.Thread.__init__(self)
		self.socket = socket
		self.message_queue = queue.Queue()
		self.ttl = 0
		self.protocol = protocol
		self.window_start = 0
		self.window_end = SACK_WINDOW_SIZE
		self.unacked_packets = {}
		self.sents = 0

	def run(self):
		if self.download:
			self.get_fragments()
			if self.protocol == "sack":
				self.send_data_sack()
			else:
				self.send_data()

		while self.is_active:
			try:
				message = self.message_queue.get(timeout=2)

				if self.upload:
					if message["header"].has_data():
						self.receive_data(message)
					elif message["header"].has_end():
						send_end_confirmation(self.socket, self)
						self.save_file()
						self.is_active = False
				else:
					if self.protocol == "sack":
						self.handle_sack_ack(message)
						while not self.message_queue.empty():
							message = self.message_queue.get(timeout=2)
							self.handle_sack_ack(message)							
							print("Jorge")
						self.send_data_sack()
					else:
						self.send_data(message)

			except queue.Empty:
				logger.warning(f"Cliente {self.addr} no ha enviado mensajes recientes.")
				if self.ttl >= 10:
					logger.warning(f"Cliente {self.addr} inactivo por 5 intentos.")
					self.is_active = False
				elif self.ttl <= MAX_RETRIES and self.download:
					if self.protocol == "sack":
						self.send_data_sack()
					else:
						self.send_data()

				self.ttl += 1
			except Exception as e:
				logger.error(f"Error con {self.addr}: {e}")
				self.is_active = False


	def send_data_sack(self):
		#for seq in range(self.window_start, min(self.window_end, len(self.fragments))):
			#if seq not in self.unacked_packets:
		for seq, (key, data) in enumerate(self.fragments.items()):
			if seq >= SACK_WINDOW_SIZE or self.sents > SACK_WINDOW_SIZE:  # Solo mandamos los primeros 8 elementos
				break
			if key > self.sequence + 30:
				break
			if len(self.fragments) < 10:
				print("FRAG: ", self.fragments.keys())


			send_data(self.socket, self, data, sequence=key)
			if int(key) == 11:
				send_data(self.socket, self, data, sequence=14)
			self.sents += 1
			print("Enviando paquete ", key)
		
		if not self.fragments:
			send_end(self.socket, self)
			self.is_active = False


	def handle_sack_ack(self, message):
		if message["header"].has_ack():
			if message["header"].sequence > self.sequence:
				self.sents -= message["header"].sequence - self.sequence
				self.sequence = message["header"].sequence				
				print("ACK recibido ", message["header"].sequence, " Nuevo sequence: ", self.sequence)
				# TODO VERR
				for i in range(self.sequence, message["header"].sequence +1):
					if i in self.fragments:
						print("Borrando fragmento ", i)
						del self.fragments[i]
				
			else:
				sack = message["header"].get_sequences()[1]
				for i in sack:
					print("Borrando fragmento SACK", i, " sequence: ", self.sequence, " header " , message["header"].sequence)
					self.sents -= 1
					if i in self.fragments:
						del self.fragments[i]

			#logger.info(f"SACK enviado. Último ACK: {ack_seq - 1}, SACK: {bin(sack_bits)[2:].zfill(32)}")
			#print(f"Unacked packets despues de procesar el SACK: {self.unacked_packets.keys()}")


	def put_message(self, message):
		"""Agrega un mensaje a la cola para ser procesado por el hilo."""
		self.message_queue.put(message)


	def receive_data(self, message):
		if message["header"].sequence in self.fragments:
			send_ack(self.socket, self, message["header"].sequence)
			return

		self.sequence = message["header"].sequence
		logger.info(f"Recibido desde {self}: [{self.sequence}]")
		self.fragments[self.sequence] = message["data"]
		send_ack(self.socket, self)


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
	socket: socket.socket, connection: Connection, data: bytes, sequence=None
):
	seq = sequence if sequence else connection.sequence
	header = UDPHeader(0, seq, 0)
	header.set_flag(UDPFlags.DATA)
	package = UDPPackage().pack(header, data)
	socket.sendto(package, connection.addr)


def send_ack(socket: socket.socket, connection: Connection, sequence=None):
	seq = sequence if sequence else connection.sequence
	header = UDPHeader(0, seq, 0)
	header.set_flag(UDPFlags.ACK)
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def send_sack_ack(socket: socket.socket, connection: Connection, sequence=None, sack_packages=[]):
	seq = sequence if sequence else connection.sequence
	header = UDPHeader(0, connection.sequence, 0)
	header.set_flag(UDPFlags.ACK)
	header.set_flag(UDPFlags.SACK)
	header.set_sack(sack_packages)
	if sack_packages:
		print("Sack: ", format(header.sack, f'0{32}b'))
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
	#header.set_sack([11,15])
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