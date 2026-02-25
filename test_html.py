import urllib.request
import re

url = "https://pakmcqs.com/category/computer-mcqs"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    response = urllib.request.urlopen(req, timeout=10)
    html = response.read().decode('utf-8')
    print("Fetched successfully. Subcats found:", len(re.findall(r'href="[^"]+mcqs[^"]*"', html)))
    with open("computer_mcqs.html", "w", encoding="utf-8") as f:
        f.write(html)
except Exception as e:
    print(f"Error fetching URL: {e}")
