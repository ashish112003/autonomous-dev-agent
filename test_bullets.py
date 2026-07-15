import unittest
from workspace.bullets import parse_bullets

class TestBullets(unittest.TestCase):
    def test_valid_input(self):
        bullets_str = """1. Statement 1
2. Statement 2
3. Statement 3"""
        expected_output = [{'number': 1, 'statement': 'Statement 1'}, 
                           {'number': 2, 'statement': 'Statement 2'}, 
                           {'number': 3, 'statement': 'Statement 3'}]
        self.assertEqual(parse_bullets(bullets_str), expected_output)

    def test_invalid_input(self):
        bullets_str = """a. Statement 1
2. Statement 2
3. Statement 3"""
        expected_output = [{'number': 2, 'statement': 'Statement 2'}, 
                           {'number': 3, 'statement': 'Statement 3'}]
        self.assertEqual(parse_bullets(bullets_str), expected_output)

    def test_empty_input(self):
        bullets_str = ""
        expected_output = []
        self.assertEqual(parse_bullets(bullets_str), expected_output)

    def test_parse_bulleted_statements(self):
        text = """1. Statement 1
2. Statement 2
3. Statement 3"""
        expected_output = [{'number': 1, 'statement': 'Statement 1'}, 
                           {'number': 2, 'statement': 'Statement 2'}, 
                           {'number': 3, 'statement': 'Statement 3'}]
        from workspace.bullets import parse_bulleted_statements
        self.assertEqual(parse_bulleted_statements(text), expected_output)

if __name__ == "__main__":
    unittest.main()
