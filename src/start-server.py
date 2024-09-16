import argparse
import socket

# > python start - server -h
# usage : start - server [ - h ] [ - v | -q ] [ - H ADDR ] [ - p PORT ] [- s DIRPATH ]
# < command description >
# optional arguments :
# -h , -- help show this help message and exit
# -v , -- verbose increase output verbosity
# -q , -- quiet decrease output verbosity
# -H , -- host service IP address
# -p , -- port service port
# -s , -- storage storage dir path




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-h", "--help", help="show this help message and exit", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")
    parser.add_argument("-q", "--quiet", action="store_true", help="decrease output verbosity")
    parser.add_argument("-H", "--host", type=str, help="service IP address")
    parser.add_argument("-p", "--port", type=int, help="service port")
    parser.add_argument("-s", "--storage", type=str, help="storage dir path")
    args = parser.parse_args()

    if args.help:
        parser.print_help()
    if args.verbose:
        print("verbosity turned on")

    # Creo un socket UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('10.0.0.1', 8087)
    server_socket.bind(server_address)
    while True:
        data, addr = server_socket.recvfrom(1024)
        #muchas mas cosas aca
    return

if __name__ == "__main__":
    main()
