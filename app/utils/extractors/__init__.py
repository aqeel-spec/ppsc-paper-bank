"""
Extractor utilities for scraping MCQs from different websites.
Each website has its own extraction logic based on HTML structure.
"""

from .testpoint_extractor import extract_mcqs_testpoint, crawl_pages_testpoint
from .pakmcqs_extractor import extract_mcqs_pakmcqs, crawl_pages_pakmcqs
from .pacegkacademy_extractor import extract_mcqs_pacegkacademy, crawl_pages_pacegkacademy

__all__ = [
    'extract_mcqs_testpoint',
    'crawl_pages_testpoint',
    'extract_mcqs_pakmcqs',
    'crawl_pages_pakmcqs',
    'extract_mcqs_pacegkacademy',
    'crawl_pages_pacegkacademy',
]
