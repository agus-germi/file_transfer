import unittest
from unittest.mock import patch
from src.lib.parser import parse_download_args, parse_upload_args

class TestUploadParser(unittest.TestCase):
    
    @patch('sys.argv', ['upload.py', '-H', '127.0.0.1', '-p', '8000', '-s', 'file.txt', '-n', 'file_on_server.txt'])
    def test_upload_parser_valid(self):
        """Test valid arguments for the upload parser."""
        args = parse_upload_args()
        self.assertEqual(args.host, '127.0.0.1')
        self.assertEqual(args.port, 8000)
        self.assertEqual(args.src, 'file.txt')
        self.assertEqual(args.name, 'file_on_server.txt')

    @patch('sys.argv', ['upload.py', '-h'])
    def test_upload_parser_help(self):
        """Test if the help message is triggered correctly."""
        with self.assertRaises(SystemExit):  # argparse exits when help is called
            parse_upload_args()

    @patch('sys.argv', ['upload.py', '-H', '127.0.0.1', '-p', '8000'])
    def test_upload_parser_missing_args(self):
        """Test if required arguments trigger an error."""
        with self.assertRaises(SystemExit):  # argparse exits when required args are missing
            parse_upload_args()

class TestDownloadParser(unittest.TestCase):
    
    @patch('sys.argv', ['download.py', '-H', '127.0.0.1', '-p', '8000', '-d', 'destination.txt', '-n', 'file_on_server.txt'])
    def test_download_parser_valid(self):
        """Test valid arguments for the download parser."""
        args = parse_download_args()
        self.assertEqual(args.host, '127.0.0.1')
        self.assertEqual(args.port, 8000)
        self.assertEqual(args.dst, 'destination.txt')
        self.assertEqual(args.name, 'file_on_server.txt')

    @patch('sys.argv', ['download.py', '-h'])
    def test_download_parser_help(self):
        """Test if the help message is triggered correctly."""
        with self.assertRaises(SystemExit):  # argparse exits when help is called
            parse_download_args()

    @patch('sys.argv', ['download.py', '-H', '127.0.0.1', '-p', '8000'])
    def test_download_parser_missing_args(self):
        """Test if required arguments trigger an error."""
        with self.assertRaises(SystemExit):  # argparse exits when required args are missing
            parse_download_args()

if __name__ == '__main__':
    unittest.main()
