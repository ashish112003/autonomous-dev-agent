"""
run_detector.py
Runs detect() from detector.py against a real document with the real Groq API.
Merges overlapping pairs into groups for readable display (e.g. if 1-3 and
1-11 are both duplicates, shows them together as one group: 1, 3, 11).
Run from the project root: python run_detector.py
"""

from dotenv import load_dotenv
load_dotenv(".env")

import sys
sys.path.insert(0, "workspace")
from detector import detect, parse_bullets


def merge_pairs_into_groups(pairs):
    """Union-find: merge overlapping pairs like [1,3] and [1,11] into one
    group [1, 3, 11] for display, without changing detect()'s contract."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for pair in pairs:
        for item in pair:
            find(item)
        for i in range(1, len(pair)):
            union(pair[0], pair[i])

    groups = {}
    for item in parent:
        root = find(item)
        groups.setdefault(root, set()).add(item)

    return [sorted(g) for g in groups.values()]


def main():
    with open("fixtures/sample_procurement.txt", "r", encoding="utf-8") as f:
        text = f.read()

    bullets = {b["id"]: b["text"] for b in parse_bullets(text)}
    print(f"Parsed {len(bullets)} bullets.\n")

    result = detect(text)

    duplicate_groups = merge_pairs_into_groups(result.get("duplicates", []))
    contradiction_groups = merge_pairs_into_groups(result.get("contradictions", []))

    print("=== DUPLICATES ===")
    if not duplicate_groups:
        print("(none found)")
    for group in duplicate_groups:
        print(f"  Bullets {', '.join(str(g) for g in group)}")
        for bid in group:
            print(f"    {bid}. {bullets.get(str(bid), bullets.get(bid, '?'))}")
        print()

    print("=== CONTRADICTIONS ===")
    if not contradiction_groups:
        print("(none found)")
    for group in contradiction_groups:
        print(f"  Bullets {', '.join(str(g) for g in group)}")
        for bid in group:
            print(f"    {bid}. {bullets.get(str(bid), bullets.get(bid, '?'))}")
        print()


if __name__ == "__main__":
    main()