import time
import socket
import threading
import queue
import os
import select
import logging

from lib.constants import (
    TIMEOUT,
    TIMEOUT_SACK,
    FRAGMENT_SIZE,
    PACKAGE_SIZE,
    MAX_RETRIES,
    SACK_WINDOW_SIZE,
    SEND_WINDOW_SIZE,
    PACKAGE_SEND_DELAY,
    MAX_SAC_DIF,
)
from lib.udp import UDPHeader, UDPFlags, UDPPackage

logger = logging.getLogger("app_logger")


class BaseConnection:
    """Clase base que contiene atributos y comportamientos comunes de conexiones."""

    def __init__(
        self, addr, path=None, sequence=0, download=False, protocol="stop_and_wait"
    ):
        self.addr = addr
        self.path = path
        self.sequence = sequence
        self.is_active = False
        self.download = download
        self.upload = not download
        self.protocol = protocol
        self.fragments = {}
        self.received_out_of_order = []
        self.window_sents = 0
        self.retries = 0

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
                    self.fragments[i + 1] = fragment
            logger.info(f"Fragments listos para enviar [{len(self.fragments)}]")
        except FileNotFoundError:
            logger.error(f"Error: Archivo {self.path} no encontrado.")
            self.is_active = False
            if hasattr(self, "socket"):
                close_connection(self.socket, self, "Archivo no encontrado.")

    def send_end_confirmation(self):
        send_end_confirmation(self.socket, self)
        self.save_file()
        self.is_active = False


class ClientConnection(BaseConnection, threading.Thread):
    def __init__(
        self,
        socket: socket.socket,
        addr,
        path,
        download=False,
        protocol="stop_and_wait",
    ):
        super().__init__(addr, path, download=download, protocol=protocol)
        threading.Thread.__init__(self)
        self.socket = socket
        self.message_queue = queue.Queue()

    def run(self):
        if self.download:
            self.get_fragments()
            self.send_data()

        while self.is_active:
            try:
                message = self.message_queue.get(timeout=TIMEOUT)

                if self.upload:
                    if message["header"].has_data():
                        self.retries = 0
                        self.receive_data(message)
                    elif message["header"].has_end():
                        self.send_end_confirmation()
                else:
                    self.send_data(message)

            except queue.Empty:
                logger.warning(f"Cliente {self.addr} no ha enviado mensajes recientes.")
                if self.retries > MAX_RETRIES:
                    logger.warning(
                        f"Cliente {self.addr} inactivo por {MAX_RETRIES} intentos."
                    )
                    self.is_active = False
                else:
                    if self.upload:
                        send_ack(self.socket, self)
                    else:
                        self.send_data()

                self.retries += 1
            except Exception as e:
                logger.error(f"Error con {self.addr}: {e}")
                self.is_active = False

    def put_message(self, message):
        """Agrega un mensaje a la cola para ser procesado por el hilo."""
        self.message_queue.put(message)

    def receive_data(self, message):
        if message["header"].sequence in self.fragments:
            send_ack(self.socket, self, message["header"].sequence)
            return

        self.sequence = message["header"].sequence
        logger.info(f"Mensaje Recibido: {self.addr} [DATA] - Frag Seq: {self.sequence}")
        self.fragments[self.sequence] = message["data"]
        send_ack(self.socket, self)

    def send_data(self, message=None):
        if message and message["header"].has_ack():
            self.retries = 0
            sequence = message["header"].sequence
            logger.info(f"Mensaje Recibido: {self.addr} [ACK] Seq: {sequence}")
            if sequence in self.fragments:
                self.fragments.pop(sequence)
        if self.fragments:
            key = next(iter(self.fragments))
            data = self.fragments[key]
            send_data(self.socket, self, data, sequence=key)
            logger.info(f"Enviando paquete {self.addr}: {key}")
        else:
            send_end(self.socket, self)
            self.is_active = False


class ClientConnectionSACK(BaseConnection, threading.Thread):
    def __init__(
        self, socket: socket.socket, addr, path, download=False, protocol="sack"
    ):
        super().__init__(addr, path, download=download, protocol=protocol)
        threading.Thread.__init__(self)
        self.socket = socket
        self.message_queue = queue.Queue()

    def run(self):
        if self.download:
            self.get_fragments()
            self.send_data_sack()

        while self.is_active:
            try:
                message = self.message_queue.get(timeout=TIMEOUT_SACK)

                if self.upload:
                    if message["header"].has_data():
                        self.retries = 0
                        # print("RECIBI DATA ", message["header"].sequence)
                        self.receive_data(message)
                    elif message["header"].has_end():
                        logger.info(f"Mensaje Recibido: {self.addr} [END]")
                        self.send_end_confirmation()
                else:
                    self.handle_sack_ack(message)
                    while not self.message_queue.empty():
                        message = self.message_queue.get(timeout=TIMEOUT_SACK)
                        self.handle_sack_ack(message)
                    self.send_data_sack()
                    # Para que el cliente no sature al servidor con el envio de paquetes
                    time.sleep(PACKAGE_SEND_DELAY)

            except queue.Empty:
                logger.warning(f"Cliente {self.addr} no ha enviado mensajes recientes.")
                if self.retries > MAX_RETRIES:
                    logger.warning(
                        f"Cliente {self.addr} inactivo por {MAX_RETRIES} intentos."
                    )
                    self.is_active = False
                else:
                    if self.upload:
                        send_sack_ack(
                            self.socket, self, self.sequence, self.received_out_of_order
                        )
                    else:
                        self.send_data_sack()

                self.retries += 1
            except ValueError as e:
                logger.error(f"Error con {self.addr}: {e}")
                self.is_active = False

    def send_data_sack(self):
        for seq, (key, data) in enumerate(self.fragments.items()):
            if (
                seq >= SACK_WINDOW_SIZE or self.window_sents > SEND_WINDOW_SIZE
            ):  # Solo mandamos los primeros 8 elementos
                break
            if key > self.sequence + MAX_SAC_DIF:
                break

            send_data(self.socket, self, data, sequence=key)
            self.window_sents += 1
            logger.info(f"Enviando paquete {self.addr}: {key} - Seq: {self.sequence}")

        if not self.fragments:
            send_end(self.socket, self)
            self.is_active = False

    def receive_data(self, message):
        if message["header"].sequence not in self.fragments:
            self.fragments[message["header"].sequence] = message["data"]
            logger.info(
                f"Mensaje Recibido: {self.addr} [DATA] - Frag Seq: {message['header'].sequence}"
            )

        if message["header"].sequence == self.sequence + 1:
            self.sequence = message["header"].sequence
            # send_sack_ack(self.socket, self, self.sequence)
            self.received_out_of_order.sort()
            received_out_of_order = list(self.received_out_of_order)
            for i in received_out_of_order:
                logger.info(
                    f"Recibidos OutOrder:  {self.received_out_of_order} - Borrando: {i}"
                )
                if i == self.sequence + 1:
                    self.sequence = i
                    # send_sack_ack(self.socket, self, self.sequence)
                    self.received_out_of_order.remove(i)
                else:
                    break
            send_sack_ack(self.socket, self, self.sequence, self.received_out_of_order)

        elif message["header"].sequence > self.sequence + 1:
            logger.warning(
                f"Fragmento {message['header'].sequence} recibido fuera de orden."
            )
            if message["header"].sequence not in self.received_out_of_order:
                self.received_out_of_order.append(message["header"].sequence)

        send_sack_ack(self.socket, self, self.sequence, self.received_out_of_order)
        # time.sleep(0.05)

    def handle_sack_ack(self, message):
        if message["header"].has_ack():
            self.window_sents -= 1
            if message["header"].sequence > self.sequence:
                self.window_sents -= message["header"].sequence - self.sequence
                seq = self.sequence
                self.sequence = message["header"].sequence

                for i in range(seq, message["header"].sequence + 1):
                    self.sequence = i
                    if i in self.fragments:
                        self.window_sents -= 1
                        logger.info(f"Borrando fragmento {i}")
                        del self.fragments[i]

            else:
                sack = message["header"].get_sequences()[1]
                for i in sack:
                    if i in self.fragments:
                        self.window_sents -= 1
                        del self.fragments[i]

    def put_message(self, message):
        """Agrega un mensaje a la cola para ser procesado por el hilo."""
        self.message_queue.put(message)


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
    header = UDPHeader(seq)
    header.set_flag(UDPFlags.DATA)
    package = UDPPackage().pack(header, data)
    socket.sendto(package, connection.addr)


def send_ack(socket: socket.socket, connection: Connection, sequence=None):
    seq = sequence if sequence else connection.sequence
    header = UDPHeader(seq)
    header.set_flag(UDPFlags.ACK)
    package = UDPPackage().pack(header, b"")
    socket.sendto(package, connection.addr)


def send_sack_ack(
    socket: socket.socket, connection: Connection, sequence=None, sack_packages=[]
):
    sequence if sequence else connection.sequence
    header = UDPHeader(connection.sequence)
    header.set_flag(UDPFlags.ACK)
    header.set_flag(UDPFlags.SACK)
    header.set_sack(sack_packages)
    # if sack_packages:
    # 	print("Sack: ", format(header.sack, f'0{32}b'))
    package = UDPPackage().pack(header, b"")
    socket.sendto(package, connection.addr)


def send_end(socket: socket.socket, connection: Connection):
    header = UDPHeader(connection.sequence)
    header.set_flag(UDPFlags.END)
    package = UDPPackage().pack(header, b"")
    socket.sendto(package, connection.addr)


def send_end_confirmation(socket: socket.socket, connection: Connection):
    header = UDPHeader(connection.sequence)
    header.set_flag(UDPFlags.END)
    header.set_flag(UDPFlags.ACK)
    package = UDPPackage().pack(header, b"")
    socket.sendto(package, connection.addr)


def send_start_confirmation(socket: socket.socket, connection: Connection):
    header = UDPHeader(0)
    # header.set_sack([11,15])
    header.set_flag(UDPFlags.START)
    header.set_flag(UDPFlags.ACK)
    package = UDPPackage().pack(header, b"")
    socket.sendto(package, connection.addr)


def receive_package(socket: socket.socket):

    data, addr = socket.recvfrom(PACKAGE_SIZE)
    data, header = UDPPackage(data).unpack()
    return addr, header, data


def close_connection(socket: socket.socket, connection: Connection, data=""):
    header = UDPHeader(0)
    header.set_flag(UDPFlags.CLOSE)
    send_package(socket, connection, header, data.encode())


def reject_connection(socket: socket.socket, connection: Connection):
    """Intenta cerrar la conexión y manejar cualquier error."""
    try:
        close_connection(socket, connection)
    except Exception:
        pass
    finally:
        logger.info(f"Cliente Rechazado: {connection.addr}")


def is_data_available(socket: socket.socket, timeout=0.0):
    ready = select.select([socket], [], [], timeout)
    return bool(ready[0])


###################
# Common to clients
def force_send_end(socket: socket.socket, connection: Connection, function):
    for i in range(3):
        try:
            function(socket, connection)
            addr, header, data = receive_package(socket)
            if header.has_end():
                break
        except TimeoutError:
            pass


def force_send_close(socket: socket.socket, connection: Connection, function):
    logger.info("Enviando paquete de cierre ")
    for i in range(3):
        try:
            function(socket, connection)
            addr, header, data = receive_package(socket)
            if header.has_close():
                break
        except TimeoutError:
            pass


def connect_server(
    client_socket: socket.socket, connection: Connection, DOWNLOAD: bool, args
):
    header = UDPHeader(connection.sequence)
    header.set_flag(UDPFlags.START)
    if DOWNLOAD:
        header.set_flag(UDPFlags.DOWNLOAD)
    if args.protocol == "stop_and_wait":
        header.clear_flag(UDPFlags.PROTOCOL)
    elif args.protocol == "sack":
        header.set_flag(UDPFlags.PROTOCOL)

    try:
        send_package(client_socket, connection, header, connection.path.encode())
        addr, header, data = receive_package(client_socket)

        if header.has_ack() and header.has_start() and header.sequence == 0:
            header.set_flag(UDPFlags.ACK)
            send_package(client_socket, connection, header, b"")
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
