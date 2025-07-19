from app.database import get_session
from sqlalchemy import text

session = next(get_session())

print('🏗️ TOP_BAR TABLE STRUCTURE:')
result = session.execute(text('DESCRIBE top_bar'))
for row in result.fetchall():
    print(f'   {row[0]} ({row[1]})')

print('\n🏗️ SIDE_BAR TABLE STRUCTURE:')
result = session.execute(text('DESCRIBE side_bar'))
for row in result.fetchall():
    print(f'   {row[0]} ({row[1]})')

# Check if tables are empty
print('\n📊 TABLE RECORD COUNTS:')
top_count = session.execute(text('SELECT COUNT(*) FROM top_bar')).fetchone()[0]
side_count = session.execute(text('SELECT COUNT(*) FROM side_bar')).fetchone()[0]
website_count = session.execute(text('SELECT COUNT(*) FROM website')).fetchone()[0]

print(f'   TOP_BAR: {top_count} records')
print(f'   SIDE_BAR: {side_count} records')
print(f'   WEBSITE: {website_count} records')

session.close()
