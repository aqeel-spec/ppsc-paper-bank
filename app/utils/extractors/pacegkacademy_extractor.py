"""
PaceGKAcademy.com MCQ Extractor

Handles extraction of MCQs from PaceGKAcademy.com website structure.
"""

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.models import AnswerOption

logger = logging.getLogger("scrape")


def crawl_pages_pacegkacademy(start_url: str, max_pages: int = None) -> List[str]:
    """
    Crawl PaceGKAcademy pages with pagination detection.
    
    Args:
        start_url: The starting URL to crawl from
        max_pages: Maximum number of pages to crawl (None = unlimited)
    
    Returns:
        List of page URLs
    """
    pages = []
    current_url = start_url
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    logger.info(f"[pacegkacademy] starting crawl at {start_url} (max_pages: {max_pages or 'unlimited'})")
    visited = set()
    
    while current_url and current_url not in visited:
        # Check if we've reached the max_pages limit
        if max_pages and len(pages) >= max_pages:
            logger.info(f"[pacegkacademy] reached max_pages limit of {max_pages}")
            break
        
        logger.info(f"[pacegkacademy] crawling page {len(pages) + 1}: {current_url}")
        pages.append(current_url)
        visited.add(current_url)
        
        try:
            resp = requests.get(current_url, headers=headers, timeout=30)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Look for next page link (adjust selector based on actual website structure)
            next_link = soup.select_one('a.next') or soup.select_one('a.page-numbers.next') or soup.select_one('a[rel="next"]')
            
            if next_link and next_link.get("href"):
                current_url = urljoin(start_url, next_link["href"])
            else:
                logger.info(f"[pacegkacademy] no more pages found")
                break
                
        except Exception as e:
            logger.error(f"[pacegkacademy] Error fetching page {current_url}: {e}", exc_info=True)
            break
    
    logger.info(f"[pacegkacademy] crawl complete - found {len(pages)} pages")
    return pages


def _scrape_mcq_explanation(detail_url: str) -> Optional[str]:
    """
    Scrape detailed explanation from an individual MCQ detail page.
    
    Args:
        detail_url: URL of the MCQ detail page
    
    Returns:
        Explanation text in Markdown format, or None if not found
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }
        
        resp = requests.get(detail_url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Find the explanation content (adjust selector based on actual website structure)
        explanation_div = soup.select_one("div.explanation") or soup.select_one("div.mcq-explanation")
        
        if not explanation_div:
            logger.warning(f"[pacegkacademy] No explanation found at {detail_url}")
            return None
        
        # Remove unwanted elements (ads, related content, etc.)
        for unwanted in explanation_div.select("div.ad, div.advertisement, ins.adsbygoogle, div.related-posts"):
            unwanted.decompose()
        
        # Convert to markdown
        explanation_md = md(str(explanation_div), heading_style="ATX")
        explanation_md = explanation_md.strip()
        
        logger.info(f"[pacegkacademy] Scraped explanation ({len(explanation_md)} chars) from {detail_url}")
        return explanation_md
        
    except Exception as e:
        logger.error(f"[pacegkacademy] Error scraping explanation from {detail_url}: {e}", exc_info=True)
        return None


def extract_mcqs_pacegkacademy(soup: BeautifulSoup, scrape_explanations: bool = False) -> List[dict]:
    """
    Extract MCQs from PaceGKAcademy.com website structure.
    
    Structure:
    <div class="courses-item content">
      <div class="quizStatement">Question text</div>
      <div class="mcqOptions">
        <ol type="A">
          <li style='color: #21A7D0; font-weight: 600'>Correct option</li>
          <li>Wrong option</li>
        </ol>
      </div>
    </div>
    
    Args:
        soup: BeautifulSoup object of the page
        scrape_explanations: If True, follow detail links and scrape explanations
    
    Returns:
        List of MCQ dictionaries
    """
    mcqs = []
    
    # Find all MCQ containers
    mcq_containers = soup.select("div.courses-item.content")
    
    logger.info(f"[pacegkacademy] Found {len(mcq_containers)} MCQ containers on page")
    
    for container in mcq_containers:
        try:
            mcq_data = _extract_single_mcq(container, scrape_explanations)
            if mcq_data:
                mcqs.append(mcq_data)
        except Exception as e:
            logger.warning(f"[pacegkacademy] Failed to extract MCQ: {e}")
            continue
    
    logger.info(f"[pacegkacademy] Successfully extracted {len(mcqs)} MCQs from page")
    return mcqs


def _extract_single_mcq(container: BeautifulSoup, scrape_explanations: bool = False) -> Optional[dict]:
    """
    Extract a single MCQ from a container element.
    
    Args:
        container: BeautifulSoup element containing the MCQ (div.courses-item.content)
        scrape_explanations: If True, follow detail link and scrape explanation
    
    Returns:
        MCQ dictionary or None if extraction fails
    """
    # Extract question text from div.quizStatement
    question_elem = container.select_one("div.quizStatement")
    if not question_elem:
        return None
    
    # Get question text from the <a> tag inside, or fallback to div text
    question_link = question_elem.find("a")
    if question_link:
        question_text = question_link.get_text(strip=True)
        # Remove question number (e.g., "Q.70")
        question_text = re.sub(r'^Q\.\d+\s*', '', question_text)
        detail_url = question_link.get("href")
        if detail_url:
            detail_url = urljoin("https://www.pacegkacademy.com", detail_url)
    else:
        question_text = question_elem.get_text(strip=True)
        detail_url = None
    
    # Extract options from div.mcqOptions > ol
    mcq_options_div = container.select_one("div.mcqOptions")
    if not mcq_options_div:
        return None
    
    ol = mcq_options_div.find("ol")
    if not ol:
        return None
    
    option_elements = ol.find_all("li", recursive=False)
    
    if len(option_elements) < 4:
        logger.warning(f"[pacegkacademy] Not enough options found for question: {question_text[:50]}")
        return None
    
    options = {}
    correct_answer = None
    option_labels = ['a', 'b', 'c', 'd', 'e', 'f']  # Support up to 6 options
    
    for idx, option_elem in enumerate(option_elements[:6]):  # Max 6 options
        if idx >= len(option_labels):
            break
        
        # Get option text from label inside
        label = option_elem.find("label")
        if label:
            option_text = label.get_text(strip=True)
        else:
            option_text = option_elem.get_text(strip=True)
        
        option_key = f"option_{option_labels[idx]}"
        options[option_key] = option_text
        
        # Check if this is the correct answer by checking for style attribute
        # Correct answer has: style='color: #21A7D0; font-weight: 600'
        style = option_elem.get("style", "")
        if "#21A7D0" in style or "#21a7d0" in style.lower():
            correct_answer = AnswerOption(option_key)
    
    # If we don't have at least 4 options, skip this MCQ
    if len(options) < 4:
        return None
    
    if not correct_answer:
        logger.warning(f"[pacegkacademy] No correct answer found for question: {question_text[:50]}")
        return None
    
    mcq_data = {
        "question_text": question_text,
        **options,
        "correct_answer": correct_answer,
    }
    
    # Add detail URL if available
    if detail_url:
        mcq_data["detail_url"] = detail_url
        
        # Scrape explanation if requested
        if scrape_explanations:
            explanation = _scrape_mcq_explanation(detail_url)
            if explanation:
                mcq_data["explanation"] = explanation
    
    return mcq_data
