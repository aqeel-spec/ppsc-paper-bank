import os
import sys

# Add current dir to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.routes.scrape import _requests_get_html_with_retries
from bs4 import BeautifulSoup

html = _requests_get_html_with_retries("https://pakmcqs.com/category/computer-mcqs")
soup = BeautifulSoup(html, "html.parser")

print("Checking Computer MCQs page structure for subcategories...")

# Check for table-container
tables = soup.select(".table-container table")
print(f"Table-Containers found: {len(tables)}")

# Often PakMCQs categories with subcategories use <ul class="category-list"> or just have headers.
# Let's dump all headings that contain links
headers = soup.find_all(['h1', 'h2', 'h3', 'h4'])
for h in headers:
    link = h.find('a')
    if link and "mcqs" in link.get('href', '').lower():
        text = h.text.strip()
        # Ensure it's not simply the article titles which all contain MCQs
        if len(text) < 40:
            print(f"Found Heading Link ({h.name}): {text} -> {link['href']}")

# Are there any lists of links near the top?
for ul in soup.find_all('ul'):
    links = ul.find_all('a')
    valid_links = [l for l in links if "mcq" in l.get('href', '').lower() and len(l.text.strip()) > 2]
    if len(valid_links) > 2 and len(valid_links) < 50:
        print(f"Found UL with {len(valid_links)} MCQ links. Classes: {ul.get('class')}")
        for l in valid_links[:3]:
            print("  - ", l.text.strip(), l.get('href'))

with open("computer_mcqs_dump.html", "w", encoding="utf-8") as f:
    f.write(html)
