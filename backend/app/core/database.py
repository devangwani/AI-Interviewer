"""
Async MongoDB connection manager using Motor.

Lifecycle
---------
connect_db()   — called once during FastAPI startup (lifespan context in main.py)
close_db()     — called once during FastAPI shutdown
get_database() — FastAPI dependency injected into route handlers
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

# Module-level client — Motor manages its own connection pool internally
_client: AsyncIOMotorClient | None = None


async def connect_db() -> None:
    """
    Open the Motor client and validate the connection with a ping.
    Raises on misconfigured MONGO_URI so the error surfaces at startup,
    not on the first incoming request.
    """
    global _client
    _client = AsyncIOMotorClient(
        settings.MONGO_URI,
        serverSelectionTimeoutMS=5_000,   # fail fast if Atlas is unreachable
    )
    await _client.admin.command("ping")
    print(f"[DB] Connected to MongoDB Atlas — database: '{settings.MONGO_DB_NAME}'")


async def close_db() -> None:
    """Close the Motor client and release all pooled connections."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        print("[DB] MongoDB connection closed.")


def get_database() -> AsyncIOMotorDatabase:
    """
    FastAPI dependency that returns the active database handle.

    Usage in a route
    ----------------
        async def my_route(db: AsyncIOMotorDatabase = Depends(get_database)):
            doc = await db["collection"].find_one({...})
    """
    if _client is None:
        raise RuntimeError(
            "Database client is not initialised. "
            "Ensure connect_db() ran during application startup."
        )
    return _client[settings.MONGO_DB_NAME]
