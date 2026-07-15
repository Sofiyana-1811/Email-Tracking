import os
import urllib.parse
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Adapt DATABASE_URL to use asyncpg driver if configured for sync postgresql
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# strip sslmode from query string to prevent asyncpg TypeError
url_parts = urllib.parse.urlparse(DATABASE_URL)
query_params = urllib.parse.parse_qs(url_parts.query)
if "sslmode" in query_params:
    query_params.pop("sslmode")
new_query = urllib.parse.urlencode(query_params, doseq=True)
url_parts = url_parts._replace(query=new_query)
DATABASE_URL = urllib.parse.urlunparse(url_parts)

engine = create_async_engine(DATABASE_URL, connect_args={"ssl": "require"}, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
