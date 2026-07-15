import unittest
from unittest.mock import patch
from workspace.detector import Detector

class TestDetector(unittest.TestCase):

    def test_detector_init(self):
        detector = Detector()
        self.assertIsNotNone(detector)

    def test_detector_method(self):
        # TO DO: implement test for detector method
        pass  # Added a pass statement to fix the IndentationError

if __name__ == '__main__':
    unittest.main()
