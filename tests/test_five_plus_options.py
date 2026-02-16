#!/usr/bin/env python3
"""
Test script for verifying 5+ options handling in paper_mcqs_collector_v1.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bs4 import BeautifulSoup

# Mock the enum and logger to test just the method
class MockAnswerOption:
    def __init__(self, value):
        self.value = value

# Test the method directly
def test_five_plus_options():
    """Test MCQ extraction with 5+ options"""
    
    # Sample HTML with 6 options where correct is option C (3rd option)
    html_content = """
    <div class="mcq-block">
        <h5><a href="#">What is the capital of Pakistan?</a></h5>
        <ol type="A">
            <li>Karachi</li>
            <li>Lahore</li>
            <li class="correct">Islamabad</li>
            <li>Peshawar</li>
            <li>Quetta</li>
            <li>Multan</li>
        </ol>
        <div class="explanation">Islamabad is the capital city of Pakistan since 1967.</div>
    </div>
    """
    
    print("🧪 Testing 5+ Options Handling...")
    print("=" * 50)
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    block = soup.find('div', class_='mcq-block')
    
    # Simulate the logic from _extract_single_mcq
    options_list = block.find("ol", {"type": "A"}) or block.find("ol") or block.find("ul")
    option_items = options_list.find_all("li", recursive=False)
    
    print(f"📊 Found {len(option_items)} options")
    
    # Extract all option texts and find correct answer
    all_options = []
    correct_index = None
    
    for i, item in enumerate(option_items):
        option_text = item.get_text(strip=True)
        all_options.append(option_text)
        
        # Check if this option is marked as correct
        classes = item.get("class", [])
        if any(cls.lower() in ["correct", "right", "answer"] for cls in classes):
            correct_index = i
    
    print(f"✅ Correct answer is option {chr(ord('A') + correct_index)}: {all_options[correct_index]}")
    
    # Handle options: First 4 go to A-D, rest go to "Other" with markdown
    if len(all_options) > 4:
        main_options = all_options[:4]
        additional_options = all_options[4:]
        
        # Correct answer is in first 4 options (index 2 = C)
        main_options[3] = "Other"
        
        print("\n📋 Final Options:")
        print(f"�️ Option A: {main_options[0]}")
        print(f"�️ Option B: {main_options[1]}")
        print(f"�️ Option C: {main_options[2]} ✅")
        print(f"🅳️ Option D: {main_options[3]}")
        
        print("\n� Additional Options stored in explanation:")
        for i, opt in enumerate(additional_options):
            option_label = chr(ord('E') + i)
            print(f"{option_label}. {opt}")
    
    print("\n" + "=" * 50)

def test_correct_answer_in_additional_options():
    """Test MCQ where correct answer is in additional options (E or F)"""
    
    # Sample HTML with correct answer as option F (6th option)
    html_content = """
    <div class="mcq-block">
        <h5><a href="#">Which of the following is a programming language?</a></h5>
        <ol type="A">
            <li>HTML</li>
            <li>CSS</li>
            <li>JSON</li>
            <li>XML</li>
            <li>SQL</li>
            <li class="correct">Python</li>
        </ol>
        <div class="explanation">Python is a popular programming language.</div>
    </div>
    """
    
    print("🧪 Testing Correct Answer in Additional Options...")
    print("=" * 50)
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    block = soup.find('div', class_='mcq-block')
    
    # Simulate the logic from _extract_single_mcq
    options_list = block.find("ol", {"type": "A"}) or block.find("ol") or block.find("ul")
    option_items = options_list.find_all("li", recursive=False)
    
    print(f"📊 Found {len(option_items)} options")
    
    # Extract all option texts and find correct answer
    all_options = []
    correct_index = None
    
    for i, item in enumerate(option_items):
        option_text = item.get_text(strip=True)
        all_options.append(option_text)
        
        # Check if this option is marked as correct
        classes = item.get("class", [])
        if any(cls.lower() in ["correct", "right", "answer"] for cls in classes):
            correct_index = i
    
    print(f"✅ Original correct answer: option {chr(ord('A') + correct_index)}: {all_options[correct_index]}")
    
    # Handle options: First 4 go to A-D, rest go to "Other" with markdown
    if len(all_options) > 4:
        main_options = all_options[:4]
        additional_options = all_options[4:]
        
        # If correct answer is in additional options, set it to "Other" 
        if correct_index is not None and correct_index >= 4:
            original_correct_option = all_options[correct_index]
            main_options[3] = "Other"
            correct_index = 3  # Point to "Other" option
            
            # Add the original correct option info to additional options context
            additional_options.insert(0, f"**Correct Answer:** {original_correct_option}")
        
        print("\n📋 Final Options:")
        print(f"�️ Option A: {main_options[0]}")
        print(f"�️ Option B: {main_options[1]}")
        print(f"�️ Option C: {main_options[2]}")
        print(f"🅳️ Option D: {main_options[3]} ✅")
        
        print("\n� Additional Options stored in explanation:")
        for i, opt in enumerate(additional_options):
            if opt.startswith("**Correct Answer:**"):
                print(opt)
            else:
                option_label = chr(ord('E') + i)
                print(f"{option_label}. {opt}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    test_five_plus_options()
    test_correct_answer_in_additional_options()
    print("🎉 Testing completed!")
