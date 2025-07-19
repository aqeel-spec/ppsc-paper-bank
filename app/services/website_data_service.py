from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlparse
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.models.websites import Websites, WebsitesCreate, WebsitesUpdate, WebsitesRead
from app.models.category import Category
from app.models.top_bar import TopBar, TopBarCreate, TopBarUpdate
from app.services.scrapper.top_urls import WebsiteTopService


class WebsiteDataService:
    """
    Service for managing website data, categories, and top bar records.
    Provides functionality to collect URLs from websites and create related database records.
    """
    
    def __init__(self):
        self.url_service = WebsiteTopService()
    
    def create_website_entry(self, websites_data: WebsitesCreate) -> WebsitesRead:
        """
        Create a new website entry.
        
        Args:
            websites_data: Website data to create
            
        Returns:
            Created website record
        """
        try:
            with Session(get_engine()) as session:
                db_website = Websites(**websites_data.model_dump())
                session.add(db_website)
                session.commit()
                session.refresh(db_website)
                return WebsitesRead.from_orm(db_website)
        except SQLAlchemyError as e:
            raise Exception(f"Failed to create website entry: {str(e)}")
    
    def update_website_entry(self, website_id: int, websites_data: WebsitesUpdate) -> WebsitesRead:
        """
        Update an existing website entry.
        
        Args:
            website_id: ID of website to update
            websites_data: Updated website data
            
        Returns:
            Updated website record
        """
        try:
            with Session(get_engine()) as session:
                statement = select(Websites).where(Websites.id == website_id)
                db_website = session.exec(statement).first()
                
                if not db_website:
                    raise Exception(f"Website with ID {website_id} not found")
                
                update_data = websites_data.dict(exclude_unset=True)
                for field, value in update_data.items():
                    setattr(db_website, field, value)
                
                db_website.updated_at = datetime.now()
                session.add(db_website)
                session.commit()
                session.refresh(db_website)
                return WebsitesRead.from_orm(db_website)
        except SQLAlchemyError as e:
            raise Exception(f"Failed to update website entry: {str(e)}")
    
    def get_website_by_id(self, website_id: int) -> Optional[WebsitesRead]:
        """Get website by ID."""
        try:
            with Session(get_engine()) as session:
                statement = select(Websites).where(Websites.id == website_id)
                db_website = session.exec(statement).first()
                return WebsitesRead.from_orm(db_website) if db_website else None
        except SQLAlchemyError as e:
            raise Exception(f"Failed to get website: {str(e)}")
    
    def get_all_websites(self) -> List[WebsitesRead]:
        """Get all website entries."""
        try:
            with Session(get_engine()) as session:
                statement = select(Websites)
                websites = session.exec(statement).all()
                return [WebsitesRead.from_orm(website) for website in websites]
        except SQLAlchemyError as e:
            raise Exception(f"Failed to get websites: {str(e)}")
    
    def get_or_create_website(self, website_name: str, base_url: str, website_type: str) -> WebsitesRead:
        """
        Get existing website or create new one if it doesn't exist.
        
        Args:
            website_name: Name of the website
            base_url: Base URL of the website
            website_type: Type of website
            
        Returns:
            Existing or newly created website record
        """
        try:
            with Session(get_engine()) as session:
                # Check if website already exists
                statement = select(Websites).where(
                    Websites.website_name == website_name,
                    Websites.base_url == base_url
                )
                existing_website = session.exec(statement).first()
                
                if existing_website:
                    return WebsitesRead.from_orm(existing_website)
                
                # Create new website if it doesn't exist
                website_data = WebsitesCreate(
                    website_name=website_name,
                    base_url=base_url,
                    website_type=website_type,
                    description=f"Website for {website_name}",
                    is_active=True
                )
                
                db_website = Websites(**website_data.dict())
                session.add(db_website)
                session.commit()
                session.refresh(db_website)
                return WebsitesRead.from_orm(db_website)
                
        except SQLAlchemyError as e:
            raise Exception(f"Failed to get or create website: {str(e)}")
    
    def collect_and_store_website_data(self, website_url: str, website_name: str) -> Dict[str, Any]:
        """
        Collect URLs from a website and store the website information.
        
        Args:
            website_url: URL of the website to scrape
            website_name: Name for the website
            
        Returns:
            Dictionary with collection results and website ID
        """
        try:
            # Collect URLs from the website
            collection_result = self.url_service.extract_urls_and_title(website_url)
            
            if not collection_result['success']:
                return {
                    'success': False,
                    'error': f"Failed to collect URLs: {collection_result.get('error')}"
                }
            
            # Extract website information
            parsed_url = urlparse(website_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Get or create website record (avoid duplicates)
            website_record = self.get_or_create_website(
                website_name=website_name,
                base_url=base_url,
                website_type=collection_result['website_type']
            )
            
            return {
                'success': True,
                'website_id': website_record.id,
                'website_name': website_name,
                'total_urls_collected': len(collection_result['urls']),
                'website_type': collection_result['website_type'],
                'page_title': collection_result.get('title', 'Unknown Title'),
                'collected_urls': collection_result['urls']  # Store the URLs for category creation
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_categories_from_website_data(self, website_id: int, urls_data: List[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Create category records from website data.
        
        Args:
            website_id: ID of the website to create categories from
            urls_data: List of URL data with 'url' and 'title' keys
            
        Returns:
            List of created category records
        """
        try:
            # Get website data to verify it exists
            website = self.get_website_by_id(website_id)
            if not website:
                raise Exception(f"Website with ID {website_id} not found")
            
            if not urls_data:
                raise Exception("No URLs data provided for category creation")
            
            created_categories = []
            
            with Session(get_engine()) as session:
                for url_item in urls_data:
                    name = url_item['title']
                    url = url_item['url']
                    
                    # Check if category already exists
                    existing_statement = select(Category).where(Category.name == name)
                    existing_category = session.exec(existing_statement).first()
                    
                    if not existing_category:
                        # Create new category with auto-generated slug
                        category = Category.create_with_auto_slug(name, session)
                        
                        created_categories.append({
                            'id': category.id,
                            'name': category.name,
                            'slug': category.slug
                        })
                    else:
                        # Add existing category to the list
                        created_categories.append({
                            'id': existing_category.id,
                            'name': existing_category.name,
                            'slug': existing_category.slug,
                            'existed': True
                        })
            
            return created_categories
            
        except Exception as e:
            raise Exception(f"Failed to create categories: {str(e)}")
    
    def create_top_bar_from_website_data(self, website_id: int, title: str = "Top Bar", urls_data: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Create top bar record from website data.
        
        Args:
            website_id: ID of the website to create top bar from
            title: Title for the top bar
            urls_data: List of URL data with 'url' and 'title' keys
            
        Returns:
            Dictionary with creation results
        """
        try:
            # Get website data to verify it exists
            website = self.get_website_by_id(website_id)
            if not website:
                return {
                    'success': False,
                    'error': f"Website with ID {website_id} not found"
                }
            
            if not urls_data:
                return {
                    'success': False,
                    'error': "No URLs data provided for top bar creation"
                }
            
            # Extract names and URLs from the data
            names = [item['title'] for item in urls_data]
            urls = [item['url'] for item in urls_data]
            
            # Create top bar data
            top_bar_data = TopBarCreate(
                title=title,
                names=names,
                urls=urls
            )
            
            with Session(get_engine()) as session:
                db_top_bar = TopBar(**top_bar_data.dict())
                session.add(db_top_bar)
                session.commit()
                session.refresh(db_top_bar)
                
                return {
                    'success': True,
                    'top_bar_id': db_top_bar.id,
                    'title': db_top_bar.title,
                    'total_items': len(db_top_bar.names) if db_top_bar.names else 0,
                    'website_id': website_id
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def setup_complete_website_data(self, website_url: str, website_name: str, 
                                   create_categories: bool = True, 
                                   create_top_bar: bool = True) -> Dict[str, Any]:
        """
        Complete workflow to setup website data with categories and top bar.
        
        Args:
            website_url: URL of the website to setup
            website_name: Name for the website
            create_categories: Whether to create categories from the data
            create_top_bar: Whether to create top bar from the data
            
        Returns:
            Dictionary with complete setup results
        """
        try:
            # Step 1: Collect and store website data
            collection_result = self.collect_and_store_website_data(website_url, website_name)
            
            if not collection_result['success']:
                return collection_result
            
            website_id = collection_result['website_id']
            urls_data = collection_result.get('collected_urls', [])
            
            setup_results = {
                'website_collection': collection_result
            }
            
            # Step 2: Create categories if requested
            if create_categories:
                try:
                    categories = self.create_categories_from_website_data(website_id, urls_data)
                    setup_results['categories_created'] = categories
                except Exception as e:
                    setup_results['categories_error'] = str(e)
            
            # Step 3: Create top bar if requested
            if create_top_bar:
                try:
                    top_bar_result = self.create_top_bar_from_website_data(
                        website_id, 
                        title=f"{website_name} Navigation",
                        urls_data=urls_data
                    )
                    setup_results['top_bar_created'] = top_bar_result
                except Exception as e:
                    setup_results['top_bar_error'] = str(e)
            
            return {
                'success': True,
                'website_id': website_id,
                'website_name': website_name,
                'setup_results': setup_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


# Predefined websites for batch setup
PREDEFINED_WEBSITES = [
    {
        'name': 'PakMcqs',
        'url': 'https://pakmcqs.com/category/english-mcqs',
        'category': 'English MCQs'
    },
    {
        'name': 'PakMcqs',
        'url': 'https://pakmcqs.com/category/pak-study-mcqs',
        'category': 'Pakistan Studies'
    },
    {
        'name': 'PakMcqs',
        'url': 'https://pakmcqs.com/category/islamiat-mcqs',
        'category': 'Islamic Studies'
    },
    {
        'name': 'PakMcqs',
        'url': 'https://pakmcqs.com/category/general-knowledge-mcqs',
        'category': 'General Knowledge'
    },
    {
        'name': 'TestPoint',
        'url': 'https://testpoint.pk/papers/ppsc',
        'category': 'PPSC Papers'
    },
    {
        'name': 'TestPoint',
        'url': 'https://testpoint.pk/papers/fpsc',
        'category': 'FPSC Papers'
    }
]


def setup_all_predefined_websites() -> Dict[str, Any]:
    """
    Setup all predefined websites with complete workflow.
    
    Returns:
        Dictionary with batch setup results
    """
    service = WebsiteDataService()
    results = []
    successful_setups = 0
    
    for site_info in PREDEFINED_WEBSITES:
        category_name = site_info.get('category', 'Unknown Category')
        print(f"Setting up: {site_info['name']} - {category_name}...")
        
        result = service.setup_complete_website_data(
            website_url=site_info['url'],
            website_name=site_info['name'],  # This will be "PakMcqs" or "TestPoint"
            create_categories=True,
            create_top_bar=True
        )
        
        results.append({
            'site_name': f"{site_info['name']} - {category_name}",
            'site_url': site_info['url'],
            'result': result
        })
        
        if result['success']:
            successful_setups += 1
            print(f"✅ {site_info['name']} - {category_name} setup completed")
        else:
            print(f"❌ {site_info['name']} - {category_name} setup failed: {result.get('error')}")
    
    return {
        'total_sites_processed': len(PREDEFINED_WEBSITES),
        'successful_setups': successful_setups,
        'results': results
    }
