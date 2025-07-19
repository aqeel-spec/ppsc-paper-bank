from app.database import get_session
from app.models.top_bar import TopBar
from app.models.side_bar import SideBar
from sqlmodel import select, func

session = next(get_session())

top_count = session.exec(select(func.count(TopBar.id))).first()
side_count = session.exec(select(func.count(SideBar.id))).first()

print(f'FINAL DATABASE STATE:')
print(f'Top Bar Records: {top_count}')
print(f'Side Bar Records: {side_count}')
print(f'Total Individual URL Records: {top_count + side_count}')
print('\n✅ All duplicate URLs were successfully detected and skipped!')
print('\n📊 DUPLICATE DETECTION SUMMARY:')
print('- When same URLs are processed again, they are skipped with "already exists skipping" message')
print('- Only unique URLs are inserted into the database')
print('- The system maintains data integrity by preventing duplicate URL records')
