from app.database import get_session
from sqlalchemy import text

session = next(get_session())
print('📊 Current Database Tables:')
result = session.execute(text('SHOW TABLES'))
tables = [row[0] for row in result.fetchall()]
for table in sorted(tables):
    print(f'   - {table}')

print(f'\n📈 Total Tables: {len(tables)}')
session.close()
