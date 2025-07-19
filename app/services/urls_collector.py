from dataclasses import dataclass
from typing import TypeVar, Generic,ClassVar

from app.services.scrapper.top_urls import WebsiteTopService

T = TypeVar('T')



@dataclass
class URLCollector(Generic[T]):
    # collect urls from a specific website
    url : str
    urls_collected : list[T] = []
    
    
    

    