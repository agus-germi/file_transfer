
import struct
import socket
import sys


TIMEOUT = 2  # Timeout in seconds
MAX_RETRIES = 3 # Numero maximo de reintentos


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
        return self.has_flag(UDPFlags.DOWNLOAD)
    
    def has_upload(self):
        return self.has_flag(UDPFlags.UPLOAD)


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
    UPLOAD = 0b10000000
    DOWNLOAD = 0b01000000


class Connection:
    def __init__(self, ip="", socket=None, client_sequence=None, server_sequence=None, upload = False, download = False):
        self.ip = ip
        self.socket = socket
        self.client_sequence = client_sequence
        self.server_sequence = server_sequence
        self.started = False
        self.upload = upload
        self.download = download
        self.path = ""


class CloseConnectionException(Exception):
    def __init__(self, mensaje, codigo_error):
        super().__init__(mensaje)
        self.codigo_error = codigo_error


def send_package(socket: socket.socket, connection: Connection, header, data):
    package = UDPPackage().pack(header, data)
    socket.sendto(package, (connection.ip, connection.socket))


def receive_package(socket: socket.socket):
    data, addr = socket.recvfrom(1024)
    data, header = UDPPackage(data).unpack()
    return addr, header, data


def close_connection(socket: socket.socket, connection: Connection):
    header = UDPHeader(0, 0, 0, 0)
    header.set_flag(UDPFlags.CLOSE)
    print("Enviando paquete de cierre ", connection.ip, "-", connection.socket)
    send_package(socket, connection, header, b"")
