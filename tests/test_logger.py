import unittest
import logging
from io import StringIO
from src.lib.logger import setup_logger

class TestLogger(unittest.TestCase):
    
    def setUp(self):
        """Create a logger for testing."""
        self.log_stream = StringIO()  # Capture logs in this stream
        self.handler = logging.StreamHandler(self.log_stream)
        self.formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.handler.setFormatter(self.formatter)
    
    def test_verbose_logging(self):
        """Test logger with verbose (DEBUG) level.
        Verify that the logger correctly outputs debug messages when the verbosity is set to verbose (DEBUG)."""
        
        logger = setup_logger(verbose=True)
        logger.addHandler(self.handler)
        
        logger.debug('This is a debug message.')
        self.handler.flush()  # Ensure the log message is written
        
        log_contents = self.log_stream.getvalue()
        self.assertIn('This is a debug message.', log_contents)
    
    def test_quiet_logging(self):
        """Test logger with quiet (ERROR) level.
        Verify that the logger only outputs error messages when the verbosity is set to quiet (ERROR)."""
        logger = setup_logger(quiet=True)
        logger.addHandler(self.handler)
        
        logger.debug('This debug message should not appear.')
        logger.error('This is an error message.')
        self.handler.flush()  # Ensure the log message is written
        
        log_contents = self.log_stream.getvalue()
        self.assertNotIn('This debug message should not appear.', log_contents)
        self.assertIn('This is an error message.', log_contents)
    
    def test_default_logging(self):
        """Test logger with default (INFO) level.
        Verify that the logger outputs info and warning messages at the default level (INFO)."""
        logger = setup_logger()
        logger.addHandler(self.handler)
        
        logger.info('This is an info message.')
        logger.warning('This is a warning message.')
        self.handler.flush()  # Ensure the log messages are written
        
        log_contents = self.log_stream.getvalue()
        self.assertIn('This is an info message.', log_contents)
        self.assertIn('This is a warning message.', log_contents)
        self.assertNotIn('This is a debug message.', log_contents)

if __name__ == '__main__':
    unittest.main()
