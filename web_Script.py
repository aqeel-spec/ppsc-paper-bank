#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlmodel import select, Session

# models & session dependency
from app.models.mcq import (
    AnswerOption,
    Category,
    MCQ,
    ScrapeTask,
    CategoryCheckpoint,
    TaskStatus,
)
from app.database import get_session  # your FastAPI session dep

BASE_LIST_URL = "https://testpoint.pk/important-mcqs"
#"https://testpoint.pk/important-mcqs/general-knowledge"
#"https://testpoint.pk/subcategory-mcqs/100-most-repeated-gk-mcqs"
#"https://testpoint.pk/important-mcqs/urdu-mcqs"
#"https://testpoint.pk/subcategory-mcqs/100-most-repeated-mcqs-of-english-pdf"
#"https://testpoint.pk/paper-mcqs/5317/ppsc-junior-clerk-all-past-papers-2015-to-till-date"
#"https://testpoint.pk/past-papers-mcqs/ppsc-past-papers"
#"https://testpoint.pk/past-papers-mcqs/ppsc-5-years-past-papers-subject-wise-(solved-with-details)"
#"https://testpoint.pk/paper-mcqs/4834/ppsc-all-mcqs-2024"
HEADERS = {"User-Agent": "MCQ-Scraper/1.0"}


def slugify(text: str) -> str:
    return re.sub(r"\W+", "_", text.lower()).strip("_")


class MCQScraper:
    def __init__(self, task_name: str, session: Session):
        self.session: Session = session
        self.start_url = BASE_LIST_URL
        self.requests = requests.Session()
        self.requests.headers.update(HEADERS)

        # 1) create or resume ScrapeTask
        stmt = select(ScrapeTask).where(ScrapeTask.name == task_name)
        existing = self.session.exec(stmt).one_or_none()
        if existing:
            self.task = existing
            print(f"🔄 Resuming scrape task '{task_name}' (status={self.task.status})")
            self.task.status = TaskStatus.RUNNING
        else:
            self.task = ScrapeTask(name=task_name, status=TaskStatus.RUNNING)
            self.session.add(self.task)

        # commit/refresh once
        try:
            self.session.commit()
        except Exception as e:
            print(f"⚠️ Failed to initialize task: {e}")
            self.session.rollback()
        else:
            self.session.refresh(self.task)

    def get_category_links(self):
        resp = self.requests.get(self.start_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.select_one("table.section-hide-show")
        if not table:
            # if no categories table, we'll treat the start URL as a single category
            print("⚠️  Couldn't find categories table on page — scraping base URL as one category …")
            return [{"slug": slugify(self.start_url), "title": None, "url": self.start_url}]

        cats = []
        for a in table.select("tr td a[href]"):
            title = a.get_text(strip=True)
            url = urljoin(self.start_url, a["href"])
            slug = slugify(title)
            cats.append({"slug": slug, "title": title, "url": url})

        # store total_categories for progress
        self.task.total_categories = len(cats)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
        return cats

    def crawl_pages(self, url: str):
        pages = []
        next_url = url
        while next_url:
            pages.append(next_url)
            resp = self.requests.get(next_url); resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            nxt = soup.select_one('ul.pagination a.page-link[rel=next]')
            next_url = urljoin(url, nxt["href"]) if nxt else None
        return pages

    def extract_mcqs(self, html: str, cat_slug: str):
        soup = BeautifulSoup(html, "lxml")
        container = soup.select_one("#content")
        if not container:
            return []

        out = []
        for block in container.find_all("div", recursive=False):
            h5 = block.find("h5")
            a = h5 and h5.find("a", class_="theme-color")
            if not a:
                continue

            ol = block.find("ol", {"type": "A"})
            items = ol.find_all("li", recursive=False) if ol else []
            if len(items) < 4:
                continue

            opts = [li.get_text(strip=True) for li in items]
            idx = next(
                (i for i, li in enumerate(items)
                 if "correct" in (li.get("class") or [])),
                None
            )
            expl = block.find("div", class_="question-explanation")

            # --- FIX #1: map to enum.value, not enum.name ---
            correct_value = None
            if idx is not None:
                key = f"option_{chr(ord('a') + idx)}"
                try:
                    correct_value = AnswerOption(key).value
                except ValueError:
                    correct_value = None

            mcq = {
                "question_text": a.get_text(strip=True),
                "option_a": opts[0],
                "option_b": opts[1],
                "option_c": opts[2],
                "option_d": opts[3],
                "option_e": opts[4] if len(opts) > 4 else None,
                "correct_answer": correct_value,
                "explanation": expl.get_text(" ", strip=True) if expl else None,
                "category_slug": cat_slug,
            }
            out.append(mcq)
        return out

    def persist_mcq(self, data: dict):
        # skip if we never found a valid correct_answer
        if not data.get("correct_answer"):
            print(f"⚠️ Skipping MCQ (no valid correct_answer): {data['question_text']!r}")
            return

        # ensure category exists
        stmt = select(Category).where(Category.slug == data["category_slug"])
        cat = self.session.exec(stmt).one_or_none()
        if not cat:
            cat = Category(slug=data["category_slug"], name=data["category_slug"])
            self.session.add(cat)
            try:
                self.session.commit()
            except Exception as e:
                print(f"⚠️ Failed to insert category {cat.slug!r}: {e}")
                self.session.rollback()
                return
            self.session.refresh(cat)

        # dedupe by text+category
        stmt = select(MCQ).where(
            (MCQ.question_text == data["question_text"]) &
            (MCQ.category_id == cat.id)
        )
        if self.session.exec(stmt).first():
            return

        # build MCQ, handing .correct_answer as the raw string (Pydantic will cast it back to enum)
        mcq = MCQ(
            question_text=data["question_text"],
            option_a=data["option_a"],
            option_b=data["option_b"],
            option_c=data["option_c"],
            option_d=data["option_d"],
            option_e=data["option_e"],
            correct_answer=data["correct_answer"],
            explanation=data["explanation"],
            category_id=cat.id,
        )
        self.session.add(mcq)
        # --- FIX #2: commit in try/except and rollback on failure ---
        try:
            self.session.commit()
        except Exception as e:
            print(f"⚠️ DB commit failed for MCQ: {e}")
            self.session.rollback()

    def run(self):
        try:
            cats = self.get_category_links()
            print(f"🎉 Found {len(cats)} categories.")
        except Exception as e:
            print("❌", e)
            self.task.status = TaskStatus.FAILED
            try:
                self.session.commit()
            except:
                self.session.rollback()
            sys.exit(1)

        total = len(cats)
        for idx, cat in enumerate(cats, start=1):
            # update overall progress
            self.task.current_category_idx = idx - 1
            self.task.overall_progress = int(100 * (idx - 1) / total)
            try:
                self.session.commit()
            except:
                self.session.rollback()

            # load/create checkpoint
            stmt = select(CategoryCheckpoint).where(
                (CategoryCheckpoint.task_id == self.task.id) &
                (CategoryCheckpoint.category_slug == cat["slug"])
            )
            cp = self.session.exec(stmt).one_or_none()
            if not cp:
                cp = CategoryCheckpoint(
                    task_id=self.task.id,
                    category_slug=cat["slug"],
                    last_page=0,
                    status=TaskStatus.PENDING,
                )
                self.session.add(cp)
                try:
                    self.session.commit()
                except:
                    self.session.rollback()
                    continue
                self.session.refresh(cp)

            pages = self.crawl_pages(cat["url"])
            print(f"🔄 Cat {idx}/{total} '{cat['slug']}' → {len(pages)} pages")

            cp.status = TaskStatus.RUNNING
            try:
                self.session.commit()
            except:
                self.session.rollback()

            for pnum, page_url in enumerate(pages, start=1):
                if pnum <= cp.last_page:
                    continue
                print(f"   • Fetching page {pnum}/{len(pages)}")
                try:
                    r = self.requests.get(page_url); r.raise_for_status()
                    mcqs = self.extract_mcqs(r.text, cat["slug"])
                    for m in mcqs:
                        self.persist_mcq(m)
                    cp.last_page = pnum
                    try:
                        self.session.commit()
                    except:
                        self.session.rollback()
                except Exception as e:
                    print("❌", e)
                    cp.status = TaskStatus.FAILED
                    try:
                        self.session.commit()
                    except:
                        self.session.rollback()
                    break
            else:
                cp.status = TaskStatus.COMPLETED
                try:
                    self.session.commit()
                except:
                    self.session.rollback()

        # finalize task
        self.task.status = TaskStatus.COMPLETED
        self.task.overall_progress = 100
        self.task.updated_at = datetime.now(timezone.utc)
        try:
            self.session.commit()
        except:
            self.session.rollback()
        print("✅ Scrape completed!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-n", "--task-name",
        help="Name for this scrape task (defaults to timestamp)",
        default=f"ppsc_snapshot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    args = parser.parse_args()

    # pull in your FastAPI dependency
    session_gen = get_session()
    session = next(session_gen)

    try:
        scraper = MCQScraper(task_name=args.task_name, session=session)
        scraper.run()
    finally:
        # always close the DB session
        try:
            session_gen.close()
        except Exception:
            pass







# #!/usr/bin/env python3
# import argparse
# import re
# import sys
# from datetime import datetime, timezone
# from urllib.parse import urljoin

# import requests
# from bs4 import BeautifulSoup
# from sqlmodel import select, Session
# from sqlalchemy.exc import IntegrityError, DataError

# # your models & session helper
# from app.models.mcq import (
#     AnswerOption,
#     Category,
#     MCQ,
#     ScrapeTask,
#     CategoryCheckpoint,
#     TaskStatus,
# )
# from app.database import get_session

# BASE_LIST_URL = "https://testpoint.pk/paper-mcqs/4834/ppsc-all-mcqs-2024"
# #"https://testpoint.pk/past-papers-mcqs/ppsc-5-years-past-papers-subject-wise-(solved-with-details)"
# #"https://testpoint.pk/past-papers-mcqs/ppsc-past-papers"
# HEADERS = {"User-Agent": "MCQ-Scraper/1.0"}


# def slugify(text: str) -> str:
#     return re.sub(r"\W+", "_", text.lower()).strip("_")


# class MCQScraper:
#     def __init__(self, task_name: str, session: Session):
#         self.session = session
#         self.start_url = BASE_LIST_URL
#         self.requests = requests.Session()
#         self.requests.headers.update(HEADERS)

#         # Create or resume ScrapeTask
#         stmt = select(ScrapeTask).where(ScrapeTask.name == task_name)
#         existing = self.session.exec(stmt).one_or_none()
#         if existing:
#             self.task = existing
#             print(f"🔄 Resuming scrape task '{task_name}' (status={self.task.status})")
#             self.task.status = TaskStatus.RUNNING
#         else:
#             self.task = ScrapeTask(name=task_name, status=TaskStatus.RUNNING)
#             self.session.add(self.task)

#         self.session.commit()
#         self.session.refresh(self.task)

#     def get_category_links(self):
#         resp = self.requests.get(self.start_url)
#         resp.raise_for_status()
#         soup = BeautifulSoup(resp.text, "lxml")

#         table = soup.select_one("table.section-hide-show")
#         if not table:
#             # fallback: treat base URL as one “category”
#             print("⚠️  Couldn't find categories table on page — scraping base URL as one category …")
#             return [{
#                 "slug": slugify(self.start_url),
#                 "title": "base",
#                 "url": self.start_url
#             }]

#         cats = []
#         for a in table.select("tr td a[href]"):
#             title = a.get_text(strip=True)
#             url   = urljoin(self.start_url, a["href"])
#             slug  = slugify(title)
#             cats.append({"slug": slug, "title": title, "url": url})

#         # store total for progress
#         self.task.total_categories = len(cats)
#         self.session.commit()
#         return cats

#     def crawl_pages(self, url: str):
#         pages = []
#         nxt = url
#         while nxt:
#             pages.append(nxt)
#             r = self.requests.get(nxt)
#             r.raise_for_status()
#             soup = BeautifulSoup(r.text, "lxml")
#             link = soup.select_one('ul.pagination a.page-link[rel=next]')
#             nxt = urljoin(url, link["href"]) if link else None
#         return pages

#     def extract_mcqs(self, html: str, cat_slug: str):
#         soup = BeautifulSoup(html, "lxml")
#         container = soup.select_one("#content")
#         if not container:
#             return []

#         out = []
#         for block in container.find_all("div", recursive=False):
#             h5 = block.find("h5")
#             a  = h5 and h5.find("a", class_="theme-color")
#             if not a:
#                 continue

#             ol    = block.find("ol", {"type": "A"})
#             items = ol.find_all("li", recursive=False) if ol else []
#             if len(items) < 4:
#                 continue

#             opts = [li.get_text(strip=True) for li in items]
#             idx  = next((i for i, li in enumerate(items)
#                          if "correct" in (li.get("class") or [])),
#                         None)
#             expl = block.find("div", class_="question-explanation")

#             # build dict; correct_answer may be None if missing
#             ca = None
#             if idx is not None:
#                 # this yields a real AnswerOption, value is 'option_a'..'option_e'
#                 ca = AnswerOption(f"option_{chr(ord('a') + idx)}")

#             out.append({
#                 "question_text": a.get_text(strip=True),
#                 "option_a":      opts[0],
#                 "option_b":      opts[1],
#                 "option_c":      opts[2],
#                 "option_d":      opts[3],
#                 "option_e":      opts[4] if len(opts) > 4 else None,
#                 "correct_answer": ca,
#                 "explanation":    expl.get_text(" ", strip=True) if expl else None,
#                 "category_slug":  cat_slug,
#             })
#         return out

#     def persist_mcq(self, data: dict):
#         # ensure category exists
#         stmt = select(Category).where(Category.slug == data["category_slug"])
#         cat  = self.session.exec(stmt).one_or_none()
#         if not cat:
#             cat = Category(slug=data["category_slug"], name=data["category_slug"])
#             self.session.add(cat)
#             self.session.commit()
#             self.session.refresh(cat)

#         # dedupe by text + category
#         stmt = select(MCQ).where(
#             (MCQ.question_text == data["question_text"]) &
#             (MCQ.category_id   == cat.id)
#         )
#         if self.session.exec(stmt).first():
#             return

#         # always pass .value (lowercase) so Postgres enum sees 'option_e'
#         ans_val = (data["correct_answer"].value
#                    if isinstance(data["correct_answer"], AnswerOption)
#                    else None)
#         mcq = MCQ(
#             question_text  = data["question_text"],
#             option_a       = data["option_a"],
#             option_b       = data["option_b"],
#             option_c       = data["option_c"],
#             option_d       = data["option_d"],
#             option_e       = data["option_e"],
#             correct_answer = ans_val,
#             explanation    = data["explanation"],
#             category_id    = cat.id,
#         )
#         self.session.add(mcq)
#         try:
#             self.session.commit()
#         except (IntegrityError, DataError) as e:
#             self.session.rollback()
#             print(f"⚠️  Skipped MCQ due to DB error: {e.orig or e}")

#     def run(self):
#         try:
#             cats = self.get_category_links()
#             print(f"🎉 Found {len(cats)} categories.")
#         except Exception as e:
#             print("❌", e)
#             self.task.status = TaskStatus.FAILED
#             self.session.commit()
#             sys.exit(1)

#         total = len(cats)
#         for idx, cat in enumerate(cats, start=1):
#             # update overall progress
#             self.task.current_category_idx = idx - 1
#             self.task.overall_progress      = int(100 * (idx - 1) / total)
#             self.session.commit()

#             # checkpoint per category
#             stmt = select(CategoryCheckpoint).where(
#                 (CategoryCheckpoint.task_id       == self.task.id) &
#                 (CategoryCheckpoint.category_slug == cat["slug"])
#             )
#             cp = self.session.exec(stmt).one_or_none()
#             if not cp:
#                 cp = CategoryCheckpoint(
#                     task_id       = self.task.id,
#                     category_slug = cat["slug"],
#                     last_page     = 0,
#                     status        = TaskStatus.PENDING,
#                 )
#                 self.session.add(cp)
#                 self.session.commit()
#                 self.session.refresh(cp)

#             pages = self.crawl_pages(cat["url"])
#             print(f"🔄 Cat {idx}/{total} '{cat['slug']}' → {len(pages)} pages")

#             cp.status = TaskStatus.RUNNING
#             self.session.commit()

#             for pnum, page_url in enumerate(pages, start=1):
#                 if pnum <= cp.last_page:
#                     continue  # already done
#                 print(f"   • Fetching page {pnum}/{len(pages)}")

#                 try:
#                     r = self.requests.get(page_url); r.raise_for_status()
#                     for m in self.extract_mcqs(r.text, cat["slug"]):
#                         self.persist_mcq(m)
#                     cp.last_page = pnum
#                     self.session.commit()
#                 except Exception as e:
#                     print("❌", e)
#                     self.session.rollback()
#                     cp.status = TaskStatus.FAILED
#                     self.session.commit()
#                     break
#             else:
#                 cp.status = TaskStatus.COMPLETED
#                 self.session.commit()

#         # finalize task
#         self.task.status           = TaskStatus.COMPLETED
#         self.task.overall_progress = 100
#         self.task.updated_at       = datetime.now(timezone.utc)
#         self.session.commit()
#         print("✅ Scrape completed!")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument(
#         "-n", "--task-name",
#         help="Name for this scrape task",
#         default=f"ppsc_snapshot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
#     )
#     args = parser.parse_args()

#     # Pull a Session from your FastAPI dep
#     session_gen = get_session()
#     session     = next(session_gen)

#     try:
#         scraper = MCQScraper(task_name=args.task_name, session=session)
#         scraper.run()
#     finally:
#         # close the session generator
#         try:
#             session_gen.close()
#         except:
#             pass
