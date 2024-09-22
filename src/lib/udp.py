import struct
import socket
import threading
import queue


class UDPHeader:
	HEADER_FORMAT = '!B I I I'
	HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Size of the header in bytes

	def __init__(self, flags, client_sequence, server_sequence, data_length):
		self.flags = flags  # Flags (1 byte)
		self.client_sequence = client_sequence  # Sequence number (4 bytes)
		self.server_sequence = server_sequence  # Sequence number (4 bytes)
		self.data_length = data_length  # Length of the data (4 bytes)

	def pack(self):
		"""Pack the header into binary format."""
		return struct.pack(self.HEADER_FORMAT, self.flags, self.client_sequence, self.server_sequence, self.data_length)

	@classmethod
	def unpack(cls, binary_header):
		"""Unpack the binary header and return an instance of ProtocolHeader."""
		flags, client_sequence, server_sequence, data_length = struct.unpack(cls.HEADER_FORMAT, binary_header)
		return cls(flags, client_sequence, server_sequence, data_length)
	
	def has_flag(self, flag):
		"""Checks if the flag is set."""
		return (self.flags & flag) != 0

	def set_flag(self, flag):
		"""Sets a flag."""
		self.flags |= flag

	def clear_flag(self, flag):
		"""Clears a flag."""
		self.flags &= ~flag

	def has_ack(self):
		return self.has_flag(UDPFlags.ACK)
	
	def has_start(self):
		return self.has_flag(UDPFlags.START)
	
	def has_close(self):
		return self.has_flag(UDPFlags.CLOSE)
	
	def has_download(self):
		"""Check if the download flag is set. If not set, it is an upload."""
		return self.has_flag(UDPFlags.DOWNLOAD)
	
	def has_protocol(self):
		return self.has_flag(UDPFlags.PROTOCOL)


class UDPPackage:
	def __init__(self, data=None):
		self.data = data

	def unpack(self):
		"""Unpack the data into ProtocolHeader and remaining data."""
		# Ensure there is enough data to unpack the header
		if len(self.data) < UDPHeader.HEADER_SIZE:
			raise ValueError("Data is smaller than header size")

		# Extract header and remaining data
		binary_header = self.data[:UDPHeader.HEADER_SIZE]
		header = UDPHeader.unpack(binary_header)
		remaining_data = self.data[UDPHeader.HEADER_SIZE:]

		return remaining_data, header

	def pack(self, header: UDPHeader, data):
		"""Pack the header and data into a single binary format."""
		return header.pack() + data


class UDPFlags:
	START = 0b00000001
	DATA = 0b00000010
	ACK = 0b00000100
	END = 0b00001000
	CLOSE = 0b00010000
	PROTOCOL = 0b10000000
	DOWNLOAD = 0b01000000


## Quedo a medias
class ClientConnection(threading.Thread):
	"""Clase que maneja la conexión y comunicación con un cliente específico en UDP."""
	def __init__(self, server_socket, addr):
		super().__init__()
		self.server_socket = server_socket
		self.ip = addr[0]
		self.port = addr[1]
		self.addr = addr
		self.message_queue = queue.Queue()
		self.is_active = True

	def __repr__(self):
		return f"Cliente ({self.addr})"

	def run(self):
		"""Método principal del hilo: Maneja la comunicación con el cliente."""
		while self.is_active:
			try:
				# Obtener mensaje del cliente desde su cola
				message = self.message_queue.get(timeout=10)
				
				if message == b'END':
					print(f"Cliente {self} finalizó la conexión.")
					self.is_active = False
					break
				
				# Procesar y responder al cliente
				print(f"Recibido desde {self}: {message.decode()}")
				self.server_socket.sendto(b'ACK', (self.ip, self.port))
			
			except queue.Empty:
				print(f"Cliente {self.addr} no ha enviado mensajes recientes.")
				continue
			except ConnectionResetError as e:
				print(f"Error de conexión con {self.addr}: {e}")
				self.is_active = False
			except Exception as e:
				print(f"Error inesperado con {self.addr}: {e}")
				self.is_active = False
	


class Connection:
	def __init__(self, addr, client_sequence=None, server_sequence=None, upload = False, download = False, path=None):
		self.addr = addr
		self.client_sequence = client_sequence
		self.server_sequence = server_sequence
		self.started = False
		self.upload = upload
		self.download = download
		self.path = path


class CloseConnectionException(Exception):
	def __init__(self, mensaje, codigo_error):
		super().__init__(mensaje)
		self.codigo_error = codigo_error


def send_package(socket: socket.socket, connection: Connection, header, data):
	package = UDPPackage().pack(header, data)
	socket.sendto(package, connection.addr)


def send_ack(socket: socket.socket, connection: Connection):
	header = UDPHeader(0, connection.client_sequence, 0, 0)
	header.set_flag(UDPFlags.ACK)
	package = UDPPackage().pack(header, b"")
	socket.sendto(package, connection.addr)


def receive_package(socket: socket.socket):
	data, addr = socket.recvfrom(1024)
	data, header = UDPPackage(data).unpack()
	return addr, header, data


def close_connection(socket: socket.socket, connection: Connection):
	header = UDPHeader(0, 0, 0, 0)
	header.set_flag(UDPFlags.CLOSE)
	print("Enviando paquete de cierre ", connection.addr)
	send_package(socket, connection, header, b"")


def reject_connection(socket: socket.socket, connection: Connection):
	"""Intenta cerrar la conexión y manejar cualquier error."""
	try:
		close_connection(socket, connection)
	except Exception:
		pass
	finally:
		print(f"Cliente Rechazado: {connection.addr}")
