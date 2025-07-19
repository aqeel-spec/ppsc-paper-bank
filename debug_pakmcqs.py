import requests
from bs4 import BeautifulSoup

url = 'https://pakmcqs.com/category/pakistan-current-affairs-mcqs'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

# Let's find the actual sidebar structure
print('Looking for sidebar containers:')
containers = ['div.inner', 'aside', 'div#secondary', 'div#sidebar', '.sidebar', '.widget-area']
for container in containers:
    found = soup.select(container)
    print(f'{container}: {len(found)} found')

# Let's find widgets
widgets = soup.find_all('div', class_='widget')
print(f'\nTotal widgets found: {len(widgets)}')

for i, widget in enumerate(widgets[:5]):  # Check first 5 widgets
    print(f'\nWidget {i+1}:')
    classes = widget.get('class', [])
    print(f'Classes: {classes}')
    title = widget.find('div', class_='widget-title')
    if title:
        h5 = title.find('h5', class_='heading')
        if h5:
            print(f'Title: {h5.get_text(strip=True)}')
    # Check for menus
    menus = widget.find_all('ul', class_='menu')
    print(f'Menus found: {len(menus)}')
    if menus:
        for j, menu in enumerate(menus):
            links = menu.find_all('a')
            print(f'  Menu {j+1}: {len(links)} links')
