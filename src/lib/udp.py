import struct
import socket
import threading
import queue
import os

from lib.constants import TIMEOUT, FRAGMENT_SIZE, PACKAGE_SIZE
from lib.logger import setup_logger

logger = setup_logger(verbose=False, quiet=False)


class UDPHeader:
	HEADER_FORMAT = "!B I I"
	HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Size of the header in bytes

	def __init__(self, flags, sequence, sack):
		self.flags = flags  # Flags (1 byte)
		self.sequence = sequence  # Sequence number (4 bytes) #10
		self.sack = sack # Ver que sea todo 0
		
		
		#00000000 0000000 00000000
		
		# No recibi: 11

	def pack(self):
		"""Pack the header into binary format."""
		return struct.pack(
			self.HEADER_FORMAT, self.flags, self.sequence, self.sack
		)
	
	def get_sequences(self):
		sequences = []

		bits_total = 32
		for i in range(bits_total - 1, -1, -1):
			if (self.sack >> i) & 1:  
				sequence_number = self.sequence + (bits_total - i)
				sequences.append(sequence_number-1)
		return (self.sequence, sequences)

	@classmethod
	def unpack(cls, binary_header):
		"""Unpack the binary header and return an instance of ProtocolHeader."""
		flags, sequence, sack = struct.unpack(cls.HEADER_FORMAT, binary_header)
		return cls(flags, sequence, sack)

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

	def has_sack(self):
		"""0 =stop and wait ^ 1 = sack"""
		return self.has_flag(UDPFlags.SACK)


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
	START =    0b00000001
	DATA =     0b00000010
	ACK =      0b00000100
	END =      0b00001000
	CLOSE =    0b00010000
	DOWNLOAD = 0b01000000
	SACK =     0b10000000






