import struct
import socket
import threading
import queue
import os

from lib.constants import TIMEOUT, FRAGMENT_SIZE, PACKAGE_SIZE
from lib.logger import setup_logger
from lib.parser import parse_upload_args


# TODO: poner todo esto en otro lado
args = parse_upload_args()
logger = setup_logger(verbose=args.verbose, quiet=args.quiet)
class UDPHeader:
    HEADER_FORMAT = "!B I I"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Size of the header in bytes

    def __init__(self, flags, sequence, data_length):
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


class ClientConnection(threading.Thread):
    """Clase que maneja la conexión y comunicación con un cliente específico en UDP."""

    def __init__(self, socket: socket.socket, addr, path, download=False, protocol=""):
        super().__init__()
        self.socket = socket
        self.is_active = False
        self.addr = addr
        self.path = path
        self.message_queue = queue.Queue()
        self.sequence = 0
        self.download = download
        self.upload = not download
        self.fragments = {}
        self.ttl = 0

    def __repr__(self):
        return f"Cliente ({self.addr})"

    def run(self):
        if self.download:
            self.get_fragments()

        while self.is_active:
            try:
                # Obtener mensaje del cliente desde su cola
                message = self.message_queue.get(timeout=5)

                if self.upload:
                    if message["header"].has_data():
                        self.receive_data(message)
                    elif message["header"].has_end():
                        send_end_confirmation(self.socket, self)
                        self.save_file()
                        self.is_active = False
                else:
                    self.send_data(message)

            except queue.Empty:
                logger.warning(f"Cliente {self.addr} no ha enviado mensajes recientes.")
                if self.ttl >= 5:
                    # TODO Join de thread
                    logger.warning(f"Cliente {self.addr} inactivo por 5 intentos.")
                    self.is_active = False
                self.ttl += 1
                continue
            except ConnectionResetError as e:
                logger.error(f"Error de conexión con {self.addr}: {e}")
                self.is_active = False
            except Exception as e:
                logger.error(f"Error inesperado con {self.addr}: {e}")
                self.is_active = False

    def receive_data(self, message):
        # Verificar si el fragmento ya fue recibido
        if message["header"].sequence in self.fragments:
            logger.info(f"Fragmento {message["header"].sequence} ya recibido.")
            send_ack(self.socket, self, message["header"].sequence)
            return None

        # Fragmento NUEVO
        self.sequence = message["header"].sequence
        logger.info(f"Recibido desde {self}: [{self.sequence}]")
        self.fragments[self.sequence] = message["data"]
        send_ack(self.socket, self)

    def send_data(self, message):
        if message["header"].has_ack():
            sequence = message["header"].sequence
            logger.info(f"ACK {sequence} recibido desde {self}")
            self.fragments.pop(sequence)
        if len(self.fragments) > 0:
            key = next(iter(self.fragments))
            data = self.fragments[
                key
            ].encode()  # TODO Si es una imagen, ya viene en bytes?
            send_data(self.socket, self, data, sequence=key)
            logger.info("Send data ", key)
        else:
            send_end(self.socket, self)
            self.is_active = False
            # TODO Que pasa si se pierde el paquete de end?

    def get_fragments(self):
        i = 0
        try:
            with open(self.path, "rb") as f:
                for i, fragment in enumerate(iter(lambda: f.read(FRAGMENT_SIZE), b"")):
                    self.fragments[i] = fragment
        except FileNotFoundError:
            logger.error(f"Archivo {self.path} no encontrado.")
            self.is_active = False
            close_connection(self.socket, self, "Archivo no encontrado.")

    def put_message(self, message):
        """Agrega un mensaje a la cola para que sea procesado por el hilo."""
        self.message_queue.put(message)
        logger.info(f"Mensaje enviado a {self.addr}: {message}")

    def save_file(self):
        output_path = self.path
        dir = self.path.split("/")[0]
        if not os.path.exists(dir):
            os.makedirs(dir)

        with open(output_path, "wb") as f:
            for i in sorted(self.fragments.keys()):
                f.write(self.fragments[i])
        logger.info("Archivo recibido y guardado exitosamente. ", self.path)


class Connection:
    def __init__(self, addr, sequence=None, upload=False, download=False, path=None):
        self.addr = addr
        self.sequence = sequence
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
    header = UDPHeader(0, connection.sequence, 0)
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
    logger.info("Enviando paquete de cierre ", connection.addr)
    send_package(socket, connection, header, data.encode())


def reject_connection(socket: socket.socket, connection: Connection):
    """Intenta cerrar la conexión y manejar cualquier error."""
    try:
        close_connection(socket, connection)
    except Exception:
        pass # TODO: Verificar si es necesario
    finally:
        logger.info(f"Cliente Rechazado: {connection.addr}")
