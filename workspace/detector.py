import re
import requests
import os
import json


def parse_bullets(text):
    bullets = []
    for line in text.split('\n'):
        match = re.match(r'(\d+)\. (.*)', line)
        if match:
            bullets.append({"id": int(match.group(1)), "text": match.group(2)})
    return bullets


def detect(text):
    try:
        api_key = os.environ["GROQ_API_KEY"]
    except KeyError:
        raise ValueError("GROQ_API_KEY environment variable is missing")
    if not text.strip():
        return {"duplicates": [], "contradictions": []}
    bullets = parse_bullets(text)
    prompt = "DUPLICATES = statements that mean the same thing in different words.\nCONTRADICTIONS = statements on the same subject with conflicting values.\nGiven the following statements:\n" + ",\n".join([str(bullet['id']) + ". " + bullet['text'] for bullet in bullets]) + "\nRespond with ONLY a JSON object, no other text, in exactly this shape: {\"duplicates\": [[id1, id2]], \"contradictions\": [[id1, id2]]}"
    try:
        response = requests.post('https://api.groq.com/openai/v1/chat/completions', headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}, json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0})
        raw = response.json()["choices"][0]["message"]["content"]
        result = re.search(r"{.*}", raw, re.DOTALL)
        if result:
            try:
                return json.loads(result.group())
            except json.JSONDecodeError:
                return {"duplicates": [], "contradictions": []}
        else:
            return {"duplicates": [], "contradictions": []}
    except requests.exceptions.RequestException:
        return {"duplicates": [], "contradictions": []}
