#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin

BASE_LIST_URL = "https://testpoint.pk/past-papers-mcqs/ppsc-5-years-past-papers-subject-wise-(solved-with-details)"
HEADERS = {"User-Agent": "MCQ-Scraper/1.0"}

def get_category_links():
    """
    Scrape the landing page and return list of dicts:
      { slug: str, title: str, url: str }
    """
    resp = requests.get(BASE_LIST_URL, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.select_one("table.section-hide-show")
    if not table:
        raise RuntimeError("Couldn't find the categories table on the landing page")
    cats = []
    for a in table.select("tr td a[href]"):
        title = a.get_text(strip=True)
        href  = urljoin(BASE_LIST_URL, a["href"])
        # build a machine-safe slug, e.g. "ppsc_all_mcqs_2025"
        slug  = re.sub(r'\W+', '_',
                       title.lower().split("of")[-1]
                      ).strip('_')
        cats.append({"slug": slug, "title": title, "url": href})
    return cats

def crawl_pages(start_url):
    """
    Follow the “next” link in pagination until exhausted.
    Returns a list of every page URL for that category.
    """
    urls = []
    next_url = start_url
    while True:
        urls.append(next_url)
        resp = requests.get(next_url, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
        if not nxt:
            break
        next_url = urljoin(start_url, nxt["href"])
    return urls

def extract_mcqs(soup, category_slug):
    """
    From a single page’s soup, extract all MCQs in that category.
    Includes the hidden “explanation” block.
    """
    out = []
    container = soup.select_one("#content")
    if not container:
        return out

    for block in container.find_all("div", recursive=False):
        # question link
        h5 = block.find("h5")
        if not (h5 and (qa := h5.find("a", class_="theme-color"))):
            continue

        # the four A–D options
        ol = block.find("ol", {"type": "A"})
        if not ol:
            continue
        items = ol.find_all("li", recursive=False)
        if len(items) < 4:
            continue

        opts = [li.get_text(strip=True) for li in items]
        correct_idx = next(
            (i for i,li in enumerate(items) if "correct" in li.get("class", [])),
            None
        )
        if correct_idx is None:
            continue

        # hidden explanation (still in the DOM)
        expl_div = block.find("div", class_="question-explanation")
        explanation = expl_div.get_text(" ", strip=True) if expl_div else ""

        out.append({
            "question_text":  qa.get_text(strip=True),
            "option_a":       opts[0],
            "option_b":       opts[1],
            "option_c":       opts[2],
            "option_d":       opts[3],
            "correct_answer": f"option_{chr(ord('a') + correct_idx)}",
            "explanation":    explanation,
            "category":       category_slug
        })

    return out

def main():
    # 1) categories
    cats = get_category_links()
    print(f"Found {len(cats)} categories.\n")

    # 2) walk each category, scrape its MCQs
    all_mcqs = []
    for cat in cats:
        slug, url = cat["slug"], cat["url"]
        print(f"> Scraping category «{slug}» → {url}")
        for page_url in crawl_pages(url):
            print(f"  • fetching {page_url}")
            r = requests.get(page_url, headers=HEADERS)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            page_mcqs = extract_mcqs(soup, slug)
            print(f"     → {len(page_mcqs)} questions")
            all_mcqs.extend(page_mcqs)

    # 3) dump everything in one file
    payload = {
        "categories": cats,
        "mcqs":       all_mcqs
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n✅  Done! Scraped {len(all_mcqs)} MCQs across {len(cats)} categories.")
    print("    Output written to data.json")

if __name__ == "__main__":
    main()



# #!/usr/bin/env python3
# import requests
# from bs4 import BeautifulSoup
# import json
# import re
# from urllib.parse import urljoin

# BASE_LIST_URL = "https://testpoint.pk/past-papers-mcqs/ppsc-5-years-past-papers-subject-wise-(solved-with-details)"
# HEADERS = {"User-Agent": "MCQ-Scraper/1.0"}

# def get_category_links():
#     resp = requests.get(BASE_LIST_URL, headers=HEADERS)
#     resp.raise_for_status()
#     soup = BeautifulSoup(resp.text, "lxml")
#     table = soup.select_one("table.section-hide-show")
#     cats = []
#     for a in table.select("tr td a"):
#         title = a.get_text(strip=True)
#         href  = urljoin(BASE_LIST_URL, a["href"])
#         key   = re.sub(r'\W+', '_', title.lower().split("of")[-1]).strip('_')
#         cats.append((key, href))
#     return cats

# def crawl_pages(start_url):
#     urls = []
#     next_url = start_url
#     while True:
#         urls.append(next_url)
#         resp = requests.get(next_url, headers=HEADERS); resp.raise_for_status()
#         soup = BeautifulSoup(resp.text, "lxml")
#         nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
#         if not nxt: break
#         next_url = urljoin(start_url, nxt["href"])
#     return urls

# def extract_mcqs(soup, category):
#     out = []
#     container = soup.select_one("#content")
#     if not container:
#         return out

#     for block in container.find_all("div", recursive=False):
#         # question link
#         h5 = block.find("h5")
#         if not (h5 and (qa := h5.find("a", class_="theme-color"))):
#             continue

#         # options
#         ol = block.find("ol", {"type": "A"})
#         if not ol:
#             continue
#         items = ol.find_all("li", recursive=False)
#         if len(items) < 4:
#             continue

#         opts = [li.get_text(strip=True) for li in items]
#         correct_idx = next(
#             (i for i,li in enumerate(items) if "correct" in li.get("class", [])),
#             None
#         )
#         if correct_idx is None:
#             continue

#         # **new**: grab the explanation block (it’s hidden via CSS but in the DOM)
#         expl_div = block.find("div", class_="question-explanation")
#         explanation = ""
#         if expl_div:
#             # you can choose .get_text() or .decode_contents() for HTML
#             explanation = expl_div.get_text(" ", strip=True)

#         out.append({
#             "question_text":  qa.get_text(strip=True),
#             "option_a":       opts[0],
#             "option_b":       opts[1],
#             "option_c":       opts[2],
#             "option_d":       opts[3],
#             "correct_answer": f"option_{chr(ord('a') + correct_idx)}",
#             "explanation":    explanation,
#             "category":       category
#         })

#     return out

# def main():
#     cats = get_category_links()
#     print(f"Found {len(cats)} categories.\n")

#     # single‐category mode (comment out if you want to loop them all)
#     cat_key, cat_url = cats[0]
#     print(f"> Scraping category «{cat_key}» → {cat_url}")

#     all_mcqs = []
#     for page_url in crawl_pages(cat_url):
#         print(f"  • fetching {page_url}")
#         r = requests.get(page_url, headers=HEADERS); r.raise_for_status()
#         soup = BeautifulSoup(r.text, "lxml")
#         page_mcqs = extract_mcqs(soup, cat_key)
#         print(f"     → {len(page_mcqs)} questions")
#         all_mcqs.extend(page_mcqs)

#     print(f"\nTotal MCQs scraped: {len(all_mcqs)}")
#     with open("mcqs.json", "w", encoding="utf-8") as f:
#         json.dump({"mcqs": all_mcqs}, f, ensure_ascii=False, indent=2)
#     print("✅  Written mcqs.json")

# if __name__ == "__main__":
#     main()




# #!/usr/bin/env python3
# import requests
# from bs4 import BeautifulSoup
# import json
# import re
# from urllib.parse import urljoin, urlparse, parse_qs

# BASE_LIST_URL = "https://testpoint.pk/past-papers-mcqs/ppsc-5-years-past-papers-subject-wise-(solved-with-details)"
# HEADERS = {"User-Agent": "MCQ-Scraper/1.0"}

# def get_category_links():
#     """Returns list of (category_name, category_url)"""
#     r    = requests.get(BASE_LIST_URL, headers=HEADERS); r.raise_for_status()
#     soup = BeautifulSoup(r.text, "lxml")
#     table = soup.select_one("table.section-hide-show")
#     cats = []
#     for a in table.select("tr td a"):
#         title = a.get_text(strip=True)
#         href  = urljoin(BASE_LIST_URL, a["href"])
#         # normalize to snake_case key
#         key = title.lower().split("of")[-1].strip().replace(" ", "_").replace("&", "and")
#         cats.append((key, href))
#     return cats

# def list_pages(first_url):
#     """Scan the pagination nav on first_url and return a sorted list of every page URL."""
#     r    = requests.get(first_url, headers=HEADERS); r.raise_for_status()
#     soup = BeautifulSoup(r.text, "lxml")

#     # collect all page-links
#     pages = { first_url }
#     nav = soup.select_one("ul.pagination")
#     if nav:
#         for a in nav.select("a.page-link[href]"):
#             href = urljoin(first_url, a["href"])
#             pages.add(href)

#     # sort by ?page=N (default page=1 if missing)
#     def page_num(u):
#         q = parse_qs(urlparse(u).query).get("page", ["1"])[0]
#         return int(q)
#     return sorted(pages, key=page_num)

# def extract_mcqs(soup, category):
#     """
#     Each direct <div> child of #content is one MCQ block:
#       - <h5><a class="theme-color">…question…</a></h5>
#       - followed by an <ol type="A"> with 4 <li> (one has class 'correct')
#     """
#     out = []
#     container = soup.select_one("#content")
#     if not container:
#         return out

#     for block in container.find_all("div", recursive=False):
#         h5 = block.find("h5")
#         if not h5: 
#             continue
#         a = h5.find("a", class_="theme-color")
#         if not a:
#             continue

#         q_text = a.get_text(strip=True)
#         ol     = block.find("ol", {"type": "A"})
#         if not ol:
#             continue

#         lis = ol.find_all("li", recursive=False)
#         if len(lis) < 4:
#             continue

#         opts = [li.get_text(strip=True) for li in lis]
#         correct_idx = next(
#             (i for i,li in enumerate(lis) if "correct" in li.get("class", [])),
#             None
#         )
#         if correct_idx is None:
#             continue

#         out.append({
#             "question_text":  q_text,
#             "option_a":       opts[0],
#             "option_b":       opts[1],
#             "option_c":       opts[2],
#             "option_d":       opts[3],
#             "correct_answer": f"option_{chr(ord('a') + correct_idx)}",
#             "category":       category
#         })

#     return out

# def main():
#     all_mcqs = []
#     cats = get_category_links()
#     print(f"Found {len(cats)} categories, scraping…\n")

#     for cat_key, cat_url in cats:
#         print(f"> Category «{cat_key}» → {cat_url}")
#         pages = list_pages(cat_url)
#         for page_url in pages:
#             print(f"   • fetching page {page_url}")
#             r    = requests.get(page_url, headers=HEADERS); r.raise_for_status()
#             soup = BeautifulSoup(r.text, "lxml")

#             page_mcqs = extract_mcqs(soup, cat_key)
#             print(f"      → {len(page_mcqs)} questions")
#             all_mcqs.extend(page_mcqs)

#     print(f"\nTotal MCQs scraped: {len(all_mcqs)}")
#     with open("mcqs.json", "w", encoding="utf-8") as f:
#         json.dump({"mcqs": all_mcqs}, f, ensure_ascii=False, indent=2)
#     print("✅ Wrote mcqs.json")

# if __name__ == "__main__":
#     main()
