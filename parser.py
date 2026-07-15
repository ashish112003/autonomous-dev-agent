import re

def parse_input(data):
    result = []
    for line in data.split('\n'):
        match = re.match(r'^(\d+)\. (.*)$', line)
        if match:
            id = int(match.group(1))
            text = match.group(2)
            result.append({'id': id, 'text': text})
    return result
