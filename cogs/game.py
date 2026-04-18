import discord
from discord.ext import commands
from discord import app_commands
import config
from utils import database as db
from utils import embeds as e

UPGRADES = {
    "market insight": {
        "description": "Reduces the market impact of your buy/sell actions by 50%.",
        "cost": config.UPGRADE_COST
    },
    "war shield": {
        "description": "Reduces war damage taken by 25%.",
        "cost": config.UPGRADE_COST
    },
    "trade boost": {
        "description": "Increases profit from all sales by 10%.",
        "cost": config.UPGRADE_COST
    },
    "corp reinforcement": {
        "description": "Your corporation recovers 5 health per round.",
        "cost": config.UPGRADE_COST
    }
}


upgrade_group = app_commands.Group(name="upgrade", description="Upgrade commands.")
game_group = app_commands.Group(name="game", description="Game commands.")


class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @upgrade_group.command(name="list", description="View all available upgrades and their costs.")
    async def upgrade_list(self, interaction: discord.Interaction):
        embed = e.info("Available Upgrades", "Invest in upgrades to gain strategic advantages each round.")
        for name, data in UPGRADES.items():
            embed.add_field(
                name=f"`{name.title()}` — ${data['cost']:,}",
                value=f"> {data['description']}",
                inline=False
            )
        embed.set_footer(text="Market Wars  •  Upgrades")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @upgrade_group.command(name="buy", description="Purchase an upgrade to enhance your strategy.")
    @app_commands.describe(upgrade="The upgrade name to purchase.")
    @app_commands.choices(upgrade=[
        app_commands.Choice(name="Market Insight", value="market insight"),
        app_commands.Choice(name="War Shield", value="war shield"),
        app_commands.Choice(name="Trade Boost", value="trade boost"),
        app_commands.Choice(name="Corp Reinforcement", value="corp reinforcement"),
    ])
    async def upgrade_buy(self, interaction: discord.Interaction, upgrade: app_commands.Choice[str]):
        state = await db.fetch_game_state(interaction.guild_id)
        if not state or not state['active']:
            await interaction.response.send_message(embed=e.error("Game Not Active", "The game is not currently running."), ephemeral=True)
            return

        player = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not player:
            await interaction.response.send_message(embed=e.error("Not Registered", "You are not registered for this event."), ephemeral=True)
            return

        data = UPGRADES.get(upgrade.value)
        if not data:
            await interaction.response.send_message(embed=e.error("Invalid Upgrade", "That upgrade does not exist."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow("SELECT * FROM upgrades WHERE guild_id = $1 AND discord_id = $2 AND upgrade_name = $3", interaction.guild_id, interaction.user.id, upgrade.value)
            if existing:
                await interaction.response.send_message(embed=e.warning("Already Owned", f"You already have **{upgrade.name}**."), ephemeral=True)
                return

            if float(player['cash']) < data['cost']:
                await interaction.response.send_message(
                    embed=e.error("Insufficient Funds", f"**{upgrade.name}** costs **${data['cost']:,}** and you have **${float(player['cash']):,.2f}**."),
                    ephemeral=True
                )
                return

            await conn.execute("UPDATE players SET cash = cash - $1 WHERE guild_id = $2 AND discord_id = $3", data['cost'], interaction.guild_id, interaction.user.id)
            await conn.execute("INSERT INTO upgrades (guild_id, discord_id, upgrade_name) VALUES ($1, $2, $3)", interaction.guild_id, interaction.user.id, upgrade.value)

        await interaction.response.send_message(
            embed=e.success("Upgrade Purchased", f"**{upgrade.name}** is now active.\n\n> {data['description']}"),
            ephemeral=True
        )

    @upgrade_group.command(name="status", description="View your currently active upgrades.")
    async def upgrade_status(self, interaction: discord.Interaction):
        player = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not player:
            await interaction.response.send_message(embed=e.error("Not Registered", "You are not registered for this event."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT upgrade_name FROM upgrades WHERE guild_id = $1 AND discord_id = $2", interaction.guild_id, interaction.user.id)

        if not rows:
            await interaction.response.send_message(embed=e.info("No Upgrades", "You have not purchased any upgrades yet. Use `/upgrade list` to browse."), ephemeral=True)
            return

        embed = e.info("Your Upgrades")
        for row in rows:
            data = UPGRADES.get(row['upgrade_name'])
            if data:
                embed.add_field(name=row['upgrade_name'].title(), value=f"> {data['description']}", inline=False)
        embed.set_footer(text="Market Wars  •  Active Upgrades")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @game_group.command(name="info", description="View current round info and game status.")
    async def game_info(self, interaction: discord.Interaction):
        state = await db.fetch_game_state(interaction.guild_id)
        count = await db.count_players(interaction.guild_id)

        if not state or not state['active']:
            embed = e.info("Market Wars", "The game has not started yet. Stay tuned for the Gamemaster's signal.")
            embed.add_field(name="Registered Players", value=f"**{count}**", inline=True)
            embed.add_field(name="Status", value="**Awaiting Start**", inline=True)
        else:
            embed = e.info(f"Round {state['round_number']}", "The market is live. Trade, build, and conquer.")
            embed.add_field(name="Players", value=f"**{count}**", inline=True)
            embed.add_field(name="Round", value=f"**{state['round_number']}**", inline=True)
            if state['round_ends_at']:
                embed.add_field(name="Next Round", value=f"<t:{int(state['round_ends_at'].timestamp())}:R>", inline=True)

        embed.set_footer(text="Market Wars  •  Game Info")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    bot.tree.add_command(upgrade_group)
    bot.tree.add_command(game_group)
    await bot.add_cog(Game(bot))
