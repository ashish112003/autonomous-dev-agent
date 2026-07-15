import pytest
from detector import detect
import os
import json

@pytest.fixture
def mock_api_key():
    os.environ["GROQ_API_KEY"] = 'test_api_key'

def test_detect_duplicates(mock_api_key, monkeypatch):
    def mock_post(requests, headers, json):
        class MockResponse:
            def __init__(self):
                self.status_code = 200
                self.json_return_value = {"choices": [{"text": "{\"duplicates\": [[1, 2]], \"contradictions\": []}"}]}
            def json(self):
                return self.json_return_value
            def raise_for_status(self):
                pass
        return MockResponse()
    monkeypatch.setattr('requests.post', mock_post)
    text = "1. statement 1\n2. statement 1"
    result = detect(text)
    assert result["duplicates"] == [[1, 2]]
    assert result["contradictions"] == []

def test_detect_contradictions(mock_api_key, monkeypatch):
    def mock_post(requests, headers, json):
        class MockResponse:
            def __init__(self):
                self.status_code = 200
                self.json_return_value = {"choices": [{"text": "{\"duplicates\": [], \"contradictions\": [[1, 2]]}"}]}
            def json(self):
                return self.json_return_value
            def raise_for_status(self):
                pass
        return MockResponse()
    monkeypatch.setattr('requests.post', mock_post)
    text = "1. statement 1\n2. statement 2 is false"
    result = detect(text)
    assert result["duplicates"] == []
    assert result["contradictions"] == [[1, 2]]

def test_detect_empty_input(mock_api_key, monkeypatch):
    def mock_post(requests, headers, json):
        class MockResponse:
            def __init__(self):
                self.status_code = 200
                self.json_return_value = {"choices": [{"text": "{\"duplicates\": [], \"contradictions\": []}"}]}
            def json(self):
                return self.json_return_value
            def raise_for_status(self):
                pass
        return MockResponse()
    monkeypatch.setattr('requests.post', mock_post)
    text = ""
    result = detect(text)
    assert result["duplicates"] == []
    assert result["contradictions"] == []

def test_detect_api_error(mock_api_key, monkeypatch):
    def mock_post(requests, headers, json):
        class MockResponse:
            def __init__(self):
                self.status_code = 500
                self.json_return_value = {}
            def json(self):
                return self.json_return_value
            def raise_for_status(self):
                raise Exception("Mock HTTP Error")
        return MockResponse()
    monkeypatch.setattr('requests.post', mock_post)
    text = "1. statement 1\n2. statement 2"
    result = detect(text)
    assert result["duplicates"] == []
    assert result["contradictions"] == []
