#!/usr/bin/env python3
"""
Quick test of the new weighted scoring classifier.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from inference.classifier import DefectClassifier


def test_classification():
    """Test classification with various synthetic defects."""
    classifier = DefectClassifier()
    
    print("=" * 80)
    print("WEIGHTED SCORING CLASSIFIER TEST")
    print("=" * 80)
    print()
    
    # Test cases designed to exercise different types
    test_cases = [
        {
            'name': 'Small square (likely Knot)',
            'detection': {'x': 10, 'y': 10, 'w': 64, 'h': 64, 'confidence': 85}
        },
        {
            'name': 'Very elongated (likely Broken Thread)',
            'detection': {'x': 10, 'y': 10, 'w': 32, 'h': 256, 'confidence': 90}
        },
        {
            'name': 'Large square (likely Stain)',
            'detection': {'x': 10, 'y': 10, 'w': 256, 'h': 256, 'confidence': 75}
        },
        {
            'name': 'Medium square (could be Hole or Double Knot)',
            'detection': {'x': 10, 'y': 10, 'w': 128, 'h': 128, 'confidence': 70}
        },
        {
            'name': 'Medium elongated (moderate aspect, likely Hole)',
            'detection': {'x': 10, 'y': 10, 'w': 96, 'h': 160, 'confidence': 65}
        },
        {
            'name': 'Very small (likely Knot or Unclassified)',
            'detection': {'x': 10, 'y': 10, 'w': 32, 'h': 32, 'confidence': 60}
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"  Box: {test_case['detection']['w']}x{test_case['detection']['h']}")
        
        # Classify
        defect_type, reason, diag = classifier.classify_with_diagnostics(test_case['detection'])
        
        print(f"  → Classified as: {defect_type.upper()}")
        print(f"  → Diagnostics:")
        print(f"      Patches: {diag['patch_count']}")
        print(f"      Aspect: {diag['aspect_ratio']}")
        print(f"      Circularity: {diag['circularity']}")
        print(f"  → Reasoning: {reason}")
    
    print()
    print("=" * 80)
    print("Test complete! Review classifications above.")
    print("=" * 80)


if __name__ == "__main__":
    test_classification()
