from detector import DuplicateContradictionDetector

def test_detect_duplicates_and_contradictions():
    detector = DuplicateContradictionDetector()
    bullet_points = [("1", "This is the first point"), ("2", "This is the second point"), ("3", "This is the third point")]
    detector.detect_duplicates_and_contradictions(bullet_points)

test_detect_duplicates_and_contradictions()
