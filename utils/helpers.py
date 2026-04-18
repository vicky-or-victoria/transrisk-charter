import random
import config
from utils.database import get_pool

async def initialize_market(guild_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        for resource in config.RESOURCES:
            price = round(random.uniform(50, 200), 2)
            await conn.execute("""
                INSERT INTO market (guild_id, resource, price, kind)
                VALUES ($1, $2, $3, 'resource')
                ON CONFLICT (guild_id, resource) DO NOTHING
            """, guild_id, resource, price)
        for stock in config.STOCKS:
            price = round(random.uniform(100, 500), 2)
            await conn.execute("""
                INSERT INTO market (guild_id, resource, price, kind)
                VALUES ($1, $2, $3, 'stock')
                ON CONFLICT (guild_id, resource) DO NOTHING
            """, guild_id, stock, price)

async def fluctuate_market(guild_id: int, event_modifier: dict = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT resource, price FROM market WHERE guild_id = $1", guild_id)
        for row in rows:
            change = random.uniform(-0.15, 0.15)
            if event_modifier and row['resource'] in event_modifier:
                change += event_modifier[row['resource']]
            new_price = max(1.0, round(float(row['price']) * (1 + change), 2))
            await conn.execute("UPDATE market SET price = $1 WHERE guild_id = $2 AND resource = $3", new_price, guild_id, row['resource'])

async def recalculate_scores(guild_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        players = await conn.fetch("SELECT discord_id, cash, wins FROM players WHERE guild_id = $1", guild_id)
        market = {r['resource']: float(r['price']) for r in await conn.fetch("SELECT * FROM market WHERE guild_id = $1", guild_id)}
        for player in players:
            holdings = await conn.fetch("SELECT * FROM holdings WHERE guild_id = $1 AND discord_id = $2", guild_id, player['discord_id'])
            asset_value = sum(float(h['quantity']) * market.get(h['resource'], 0) for h in holdings)
            corp = await conn.fetchrow("""
                SELECT c.treasury, c.health FROM corporations c
                JOIN corp_members cm ON c.id = cm.corp_id
                WHERE c.guild_id = $1 AND cm.discord_id = $2
            """, guild_id, player['discord_id'])
            corp_bonus = (float(corp['treasury']) * 0.1 + corp['health'] * 10) if corp else 0
            score = float(player['cash']) + asset_value + (player['wins'] * 500) + corp_bonus
            await conn.execute("UPDATE players SET score = $1 WHERE guild_id = $2 AND discord_id = $3", round(score, 2), guild_id, player['discord_id'])

def is_gamemaster(interaction) -> bool:
    if interaction.user.id == config.BOT_OWNER_ID:
        return True
    return any(r.id == config.GAMEMASTER_ROLE_ID for r in interaction.user.roles)
