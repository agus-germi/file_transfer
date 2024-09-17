import argparse  # https://docs.python.org/es/3/library/argparse.html
from src.lib.logger import setup_logger

def configure_logging(args):
    logger = setup_logger(verbose=args.verbose, quiet=args.quiet)
    return logger

def add_verbosity_args(parser):
    group = parser.add_mutually_exclusive_group()  # either one or the other not both
    group.add_argument(
        '-v', '--verbose', action='store_true', help='increase output verbosity'
    )
    group.add_argument(
        '-q', '--quiet', action='store_true', help='decrease output verbosity'
    )


def add_network_args(parser):
    parser.add_argument(
        '-H', '--host', required=True, help='server IP address'
    )
    parser.add_argument(
        '-p', '--port', type=int, required=True, help='server port'
    )

def parse_upload_args():
    parser = argparse.ArgumentParser(
        prog='Upload',
        description='Upload a file to the server.'
    )
    
    add_verbosity_args(parser)
    add_network_args(parser)

    parser.add_argument(
        '-s', '--src', required=True, help='source file path to upload'
    )
    parser.add_argument(
        '-n', '--name', required=True, help='file name to store on the server'
    )

    return parser.parse_args()


def parse_download_args():
    parser = argparse.ArgumentParser(
        prog='Download', description='Download a file from the server.'
    )

    add_verbosity_args(parser)
    add_network_args(parser)

    parser.add_argument(
        '-d', '--dst', required=True, help='destination file path to save the file'
    )
    parser.add_argument(
        '-n', '--name', required=True, help='file name to download from the server'
    )

    return parser.parse_args()


def parse_server_args():
    parser = argparse.ArgumentParser(
        prog='Server', description='Start the file server.'
    )

    add_verbosity_args(parser)
    add_network_args(parser)

    parser.add_argument(
        '-s', '--storage', required=True, help='storage directory path'
    )

    return parser.parse_args()
