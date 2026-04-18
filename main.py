import discord
from discord.ext import commands
import asyncio
import config
from utils.database import setup_tables

COGS = [
    "cogs.registration",
    "cogs.gamemaster",
    "cogs.trading",
    "cogs.corporations",
    "cogs.war",
    "cogs.leaderboard",
    "cogs.game",
]

class MarketWarsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await setup_tables()
        for cog in COGS:
            await self.load_extension(cog)
        await self.tree.sync()
        print(f"Synced slash commands.")

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="the markets"
        ))
        print(f"Logged in as {self.user} ({self.user.id})")


async def main():
    bot = MarketWarsBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


asyncio.run(main())
