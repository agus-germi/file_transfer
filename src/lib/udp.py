import struct
import socket
import threading
import queue
import os
import logging

from lib.constants import TIMEOUT, FRAGMENT_SIZE, PACKAGE_SIZE

logger = logging.getLogger("app_logger")


class UDPHeader:
	HEADER_FORMAT = "!B I I"
	HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Size of the header in bytes

	def __init__(self, sequence, flags = 0, sack = 0):
		self.flags = flags  # Flags (1 byte)
		self.sequence = sequence  # Sequence number (4 bytes) 
		self.sack = sack # SACK Sequence (4 bytes) 
		

	def pack(self):
		"""Pack the header into binary format."""
		return struct.pack(
			self.HEADER_FORMAT, self.flags, self.sequence, self.sack
		)
	
	def get_sequences(self)-> tuple:
		try:
			""" Devuelve el primer elemento el num_sequence en el que esta y en el 2 elemento resto de los packetes recividos """
			one_bits = []
			sequences = []

			bits_total = 32
			for i in range(bits_total - 1, -1, -1):
				if (self.sack >> i) & 1:
					one_bits.append(bits_total - i)
					sequences.append(bits_total -i + self.sequence)
		
			# Borrar todos los paquetes con numero de sequencia < al primer elemento y los elementos del segundo elemento
			# Puede estar el caso border que si la diferencia entre lo que no recibio y el paquete que estoy mandando es mayor a 20. Me enfoco en mandar lo que no se recibio
			return (self.sequence, sequences)
		
		except Exception as e:
			logger.error(f"Error al obtener la secuencia: {e}")
	
	
	def set_sack(self, packages_secuence: list):
		bits = 0
		positions =  [x - self.sequence -1 for x in packages_secuence]
    
		# Iteramos sobre las posiciones dadas
		for n in positions:
			if 0 <= n < 32:  # Aseguramos que la posición no exceda los 32 bits
				# Desplazamos 1 a la izquierda por (31 - n) posiciones para establecer el bit
				bits |= (1 << (31 - n))
			else:
				logger.info(f"Posición {n} fuera de rango. Debe estar entre 0 y 31.")
		
		self.sack = bits


	@classmethod
	def unpack(cls, binary_header):
		"""Unpack the binary header and return an instance of ProtocolHeader."""
		flags, sequence, sack = struct.unpack(cls.HEADER_FORMAT, binary_header)
		return cls(sequence, flags=flags, sack=sack)

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

	def has_data(self):
		return self.has_flag(UDPFlags.DATA)

	def has_start(self):
		return self.has_flag(UDPFlags.START)

	def has_end(self):
		return self.has_flag(UDPFlags.END)

	def has_close(self):
		return self.has_flag(UDPFlags.CLOSE)

	def has_download(self):
		"""Check if the download flag is set. If not set, it is an upload."""
		return self.has_flag(UDPFlags.DOWNLOAD)

	def has_protocol(self):
		"""Check if the protocol flag is set. If not set, it is stop and wait, if set it is selective ack."""
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
		binary_header = self.data[: UDPHeader.HEADER_SIZE]
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
	SACK = 0b00100000
	END = 0b00001000
	CLOSE = 0b00010000
	PROTOCOL = 0b10000000
	DOWNLOAD = 0b01000000

