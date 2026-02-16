"""
PakMCQs.com MCQ Extractor

Handles extraction of MCQs from PakMCQs.com website structure.
PakMCQs uses a paragraph-based format with inline options.
"""

import logging
import re
import html
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.models import AnswerOption

logger = logging.getLogger("scrape")


def crawl_pages_pakmcqs(start_url: str, max_pages: int = None) -> List[str]:
    """
    Crawl PakMCQs pages with pagination detection.
    
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
    
    logger.info(f"[pakmcqs] starting crawl at {start_url} (max_pages: {max_pages or 'unlimited'})")
    visited = set()
    
    while current_url and current_url not in visited:
        # Check if we've reached the max_pages limit
        if max_pages and len(pages) >= max_pages:
            logger.info(f"[pakmcqs] reached max_pages limit of {max_pages}")
            break
        
        logger.info(f"[pakmcqs] crawling page {len(pages) + 1}: {current_url}")
        pages.append(current_url)
        visited.add(current_url)
        
        try:
            resp = requests.get(current_url, headers=headers, timeout=30)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Look for next page link
            next_link = soup.select_one('a.next') or soup.select_one('a.page-numbers.next')
            
            if next_link and next_link.get("href"):
                current_url = urljoin(start_url, next_link["href"])
            else:
                logger.info(f"[pakmcqs] no more pages found")
                break
                
        except Exception as e:
            logger.error(f"[pakmcqs] Error fetching page {current_url}: {e}", exc_info=True)
            break
    
    logger.info(f"[pakmcqs] crawl complete - found {len(pages)} pages")
    return pages


def extract_mcqs_pakmcqs(soup: BeautifulSoup, scrape_explanations: bool = False) -> List[dict]:
    """
    Extract MCQs from PakMCQs.com website structure.
    
    PakMCQs uses article-based structure:
    <article>
      <div class="content">
        <h2 class="post-title"><a>Question text?</a></h2>
        <div class="excerpt">
          <p>A. Option A<br/>
          <strong>B. Correct Option</strong><br/>  <!-- Correct answer is in <strong> -->
          C. Option C<br/>
          D. Option D</p>
        </div>
      </div>
    </article>
    
    Args:
        soup: BeautifulSoup object of the page
        scrape_explanations: If True, follow detail links and scrape explanations
    """
    out: List[dict] = []
    
    # Find all article elements containing MCQs
    articles = soup.find_all('article')
    logger.info(f"[pakmcqs] Found {len(articles)} articles")
    
    for idx, article in enumerate(articles):
        try:
            mcq_data = _extract_single_mcq_from_article(article, scrape_explanations=scrape_explanations)
            if mcq_data:
                out.append(mcq_data)
                logger.info(f"[pakmcqs] Extracted MCQ {idx + 1}: {mcq_data['question_text'][:60]}...")
            else:
                logger.debug(f"[pakmcqs] Skipped article {idx + 1} - not a valid MCQ")
                
        except Exception as e:
            logger.warning(f"[pakmcqs] Error extracting MCQ from article {idx + 1}: {e}", exc_info=True)
            continue
    
    logger.info(f"[pakmcqs] Extracted {len(out)} MCQs total")
    return out


def _extract_single_mcq_from_article(article, scrape_explanations: bool = False) -> Optional[dict]:
    """
    Extract a single MCQ from an article element.
    
    Structure:
    <article>
      <h2 class="post-title"><a>Question?</a></h2>
      <div class="excerpt">
        <p>A. Option<br/>
        <strong>B. Correct</strong><br/>
        C. Option<br/>
        D. Option</p>
        <a href="..." class="read-more-link">Read More Details about this Mcq:</a>
      </div>
    </article>
    
    The correct answer is marked with <strong> tag.
    
    Args:
        article: BeautifulSoup article element
        scrape_explanations: If True, follow detail link and scrape explanation
    """
    # Extract question text
    title = article.select_one('h2.post-title a') or article.select_one('h2 a') or article.select_one('h2')
    if not title:
        return None
    
    question_text = title.get_text(strip=True)
    
    # Decode HTML entities
    question_text = html.unescape(question_text)
    
    # Remove trailing "?" and question numbers if present
    question_text = re.sub(r'^Q\.?\s*\d+[\.:)\s]*', '', question_text).strip()
    
    if len(question_text) < 5:
        return None
    
    # Extract options from excerpt div
    excerpt = article.select_one('div.excerpt') or article.select_one('div.content')
    if not excerpt:
        return None
    
    # Get the paragraph containing options
    options_p = excerpt.find('p')
    if not options_p:
        return None
    
    # Get HTML to preserve structure and identify correct answer
    html_content = str(options_p)
    
    # Split by <br> or <br/> tags
    parts = re.split(r'<br\s*/?>', html_content, flags=re.IGNORECASE)
    
    options = {}
    correct_answer = None
    
    for part in parts:
        # Clean HTML tags but check for <strong> first
        is_correct = '<strong>' in part.lower() or '<b>' in part.lower()
        
        # Remove all HTML tags
        clean_text = re.sub(r'<[^>]+>', '', part).strip()
        
        # Decode HTML entities (&amp; -> &, &gt; -> >, etc.)
        clean_text = html.unescape(clean_text)
        
        # Parse option: "A. text" or "A) text"
        match = re.match(r'^([A-E])[\.)]\s*(.+)$', clean_text, re.IGNORECASE)
        if match:
            letter = match.group(1).upper()
            text = match.group(2).strip()
            
            options[letter] = text
            
            if is_correct:
                correct_answer = f"option_{letter.lower()}"
    
    # Validate we have at least 4 options
    if len(options) < 4:
        logger.debug(f"[pakmcqs] Insufficient options found: {len(options)} for question: {question_text[:50]}...")
        return None
    
    # If no correct answer found via <strong>, try to infer from text patterns
    if not correct_answer:
        # Sometimes the correct answer might be in a separate element
        # For now, log a warning
        logger.warning(f"[pakmcqs] No correct answer identified for: {question_text[:50]}...")
        return None
    
    # Extract detail URL from "Read More Details" link
    detail_url = None
    read_more_link = article.select_one('a.read-more-link') or article.select_one('a[href*="pakmcqs.com"]')
    if read_more_link and read_more_link.get('href'):
        detail_url = read_more_link['href']
    
    # Scrape explanation if requested and URL available
    explanation = None
    if scrape_explanations and detail_url:
        explanation = _scrape_mcq_explanation(detail_url)
    
    # Build MCQ data
    mcq_data = {
        "question_text": question_text,
        "option_a": options.get('A', ''),
        "option_b": options.get('B', ''),
        "option_c": options.get('C', ''),
        "option_d": options.get('D', ''),
        "option_e": options.get('E') if 'E' in options else None,
        "correct_answer": AnswerOption(correct_answer),
        "explanation": explanation,
    }
    
    return mcq_data


def _scrape_mcq_explanation(detail_url: str) -> Optional[str]:
    """
    Scrape detailed explanation from individual MCQ page.
    
    Extracts explanation content from:
    <article>
      <div class="post-content">
        <p>Options with <br> tags</p>
        <p>Submitted by: ...</p>
        <!-- Ads -->
        <p>Explanation text here...</p>
        <p>More explanation...</p>
        <div class="yarpp yarpp-related">Related Mcqs: ...</div>
        <div class="correct-answer">The correct answer...</div>
      </div>
    </article>
    
    Returns explanation content as markdown (excluding ads, related MCQs, etc.)
    
    Args:
        detail_url: URL of the individual MCQ page
        
    Returns:
        Markdown-formatted explanation or None if not found
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",  # Avoid brotli compression
        }
        
        resp = requests.get(detail_url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Find the article with post-content
        article = soup.select_one('article')
        if not article:
            logger.warning(f"[pakmcqs] No article found in {detail_url}")
            return None
        
        post_content = article.select_one('div.post-content')
        if not post_content:
            logger.warning(f"[pakmcqs] No post-content found in {detail_url}")
            return None
        
        # Remove unwanted elements
        # 1. Remove ads (a-wrap, adsbygoogle, etc.)
        for ad in post_content.select('div.a-wrap, ins.adsbygoogle, script'):
            ad.decompose()
        
        # 2. Remove related MCQs section
        for related in post_content.select('div.yarpp'):
            related.decompose()
        
        # 3. Remove the "correct answer" confirmation div
        for answer_div in post_content.select('div.correct-answer'):
            answer_div.decompose()
        
        # 4. Remove schema.org JSON-LD script
        for script in post_content.select('script[type="application/ld+json"]'):
            script.decompose()
        
        # Get all paragraphs
        paragraphs = post_content.find_all('p')
        
        if len(paragraphs) < 2:
            logger.debug(f"[pakmcqs] Not enough content in {detail_url}")
            return None
        
        # Skip first paragraph (options) and second (submitted by)
        # Extract explanation from remaining paragraphs
        explanation_parts = []
        
        for i, p in enumerate(paragraphs):
            text = p.get_text(strip=True)
            
            # Skip empty paragraphs
            if not text:
                continue
            
            # Skip "Submitted by:" paragraph
            if 'submitted by:' in text.lower():
                continue
            
            # Skip if it looks like options (A. B. C. D.)
            if re.match(r'^[A-E]\.', text):
                continue
            
            # Add to explanation
            # Convert HTML to markdown for better formatting
            explanation_parts.append(md(str(p)))
        
        if not explanation_parts:
            logger.debug(f"[pakmcqs] No explanation content found in {detail_url}")
            return None
        
        # Join with double newlines for markdown paragraphs
        explanation = '\n\n'.join(explanation_parts).strip()
        
        logger.info(f"[pakmcqs] Scraped explanation from {detail_url} ({len(explanation)} chars)")
        return explanation
        
    except Exception as e:
        logger.error(f"[pakmcqs] Error scraping explanation from {detail_url}: {e}", exc_info=True)
        return None

