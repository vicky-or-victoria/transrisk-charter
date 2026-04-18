import asyncpg
import config

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.POSTGRES_URI)
    return _pool

async def setup_tables():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                guild_id BIGINT NOT NULL,
                discord_id BIGINT NOT NULL,
                username TEXT NOT NULL,
                cash NUMERIC DEFAULT 10000,
                score NUMERIC DEFAULT 0,
                wins INTEGER DEFAULT 0,
                registered_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (guild_id, discord_id)
            );

            CREATE TABLE IF NOT EXISTS corporations (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                treasury NUMERIC DEFAULT 0,
                owner_id BIGINT NOT NULL,
                health INTEGER DEFAULT 100,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (guild_id, name)
            );

            CREATE TABLE IF NOT EXISTS corp_members (
                guild_id BIGINT NOT NULL,
                discord_id BIGINT NOT NULL,
                corp_id INTEGER REFERENCES corporations(id) ON DELETE CASCADE,
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (guild_id, discord_id)
            );

            CREATE TABLE IF NOT EXISTS market (
                guild_id BIGINT NOT NULL,
                resource TEXT NOT NULL,
                price NUMERIC NOT NULL,
                kind TEXT NOT NULL,
                PRIMARY KEY (guild_id, resource)
            );

            CREATE TABLE IF NOT EXISTS holdings (
                guild_id BIGINT NOT NULL,
                discord_id BIGINT NOT NULL,
                resource TEXT NOT NULL,
                quantity NUMERIC DEFAULT 0,
                PRIMARY KEY (guild_id, discord_id, resource)
            );

            CREATE TABLE IF NOT EXISTS wars (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                attacker_id BIGINT NOT NULL,
                defender_id BIGINT NOT NULL,
                result TEXT,
                round_number INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS game_state (
                guild_id BIGINT PRIMARY KEY,
                active BOOLEAN DEFAULT FALSE,
                round_number INTEGER DEFAULT 0,
                round_ends_at TIMESTAMPTZ,
                round_duration_seconds INTEGER DEFAULT 3600
            );

            CREATE TABLE IF NOT EXISTS upgrades (
                guild_id BIGINT NOT NULL,
                discord_id BIGINT NOT NULL,
                upgrade_name TEXT NOT NULL,
                purchased_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (guild_id, discord_id, upgrade_name)
            );
        """)

async def ensure_game_state(guild_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO game_state (guild_id) VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING
        """, guild_id)

async def fetch_player(guild_id: int, discord_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM players WHERE guild_id = $1 AND discord_id = $2", guild_id, discord_id)

async def register_player(guild_id: int, discord_id: int, username: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            INSERT INTO players (guild_id, discord_id, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, discord_id) DO NOTHING
            RETURNING *
        """, guild_id, discord_id, username)

async def count_players(guild_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM players WHERE guild_id = $1", guild_id)

async def fetch_game_state(guild_id: int):
    await ensure_game_state(guild_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM game_state WHERE guild_id = $1", guild_id)

async def update_game_state(guild_id: int, **kwargs):
    await ensure_game_state(guild_id)
    pool = await get_pool()
    fields = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    values = [guild_id] + list(kwargs.values())
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE game_state SET {fields} WHERE guild_id = $1", *values)

async def fetch_leaderboard(guild_id: int, limit: int = 10):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT username, cash, score, wins FROM players
            WHERE guild_id = $1
            ORDER BY score DESC LIMIT $2
        """, guild_id, limit)

async def fetch_market(guild_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM market WHERE guild_id = $1 ORDER BY kind, resource", guild_id)

async def fetch_holdings(guild_id: int, discord_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM holdings WHERE guild_id = $1 AND discord_id = $2", guild_id, discord_id)

async def fetch_corporation_by_member(guild_id: int, discord_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT c.* FROM corporations c
            JOIN corp_members cm ON c.id = cm.corp_id
            WHERE c.guild_id = $1 AND cm.discord_id = $2
        """, guild_id, discord_id)

async def fetch_corporation_by_name(guild_id: int, name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM corporations WHERE guild_id = $1 AND LOWER(name) = LOWER($2)", guild_id, name)

async def fetch_corp_members(corp_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT p.* FROM players p
            JOIN corp_members cm ON p.discord_id = cm.discord_id
            WHERE cm.corp_id = $1
        """, corp_id)
