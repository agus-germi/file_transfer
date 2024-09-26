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

    def __init__(self, flags, sequence, data_length = 0):
        self.flags = flags  # Flags (1 byte)
        self.sequence = sequence  # Sequence number (4 bytes)
        self.data_length = data_length  # Length of the data (4 bytes)

    def pack(self):
        """Pack the header into binary format."""
        return struct.pack(
            self.HEADER_FORMAT, self.flags, self.sequence, self.data_length
        )

    @classmethod
    def unpack(cls, binary_header):
        """Unpack the binary header and return an instance of ProtocolHeader."""
        flags, sequence, data_length = struct.unpack(cls.HEADER_FORMAT, binary_header)
        return cls(flags, sequence, data_length)

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
    SACK = 0b00100000  # TODO: VER !
    END = 0b00001000
    CLOSE = 0b00010000
    PROTOCOL = 0b10000000
    DOWNLOAD = 0b01000000

