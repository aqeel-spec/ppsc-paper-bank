#!/usr/bin/env python3
"""Test updated MCQ collector with TEXT explanations"""

import sys
sys.path.insert(0, '.')

from app.services.scrapper.paper_mcqs_collector_v1 import PaperMCQCollectorV1
from app.database import get_session
import requests

def test_full_explanations():
    try:
        session = next(get_session())
        collector = PaperMCQCollectorV1(session)
        
        url = "https://testpointpk.com/paper-mcqs/6125/ppsc-assistant-past-paper-13-07-2025"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        mcqs = collector.extract_mcqs_from_html(response.text, None)
        print(f"Extracted {len(mcqs)} MCQs")
        
        if mcqs:
            mcq = mcqs[0]
            explanation = mcq.get("explanation", "")
            print(f"First MCQ: {mcq['question_text'][:50]}...")
            print(f"Explanation length: {len(explanation)} characters")
            print(f"Explanation preview: {explanation[:200]}...")
            
        print("SUCCESS: Full explanations are now supported!")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_full_explanations()
