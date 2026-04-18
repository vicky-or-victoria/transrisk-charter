import discord
from discord.ext import commands
from discord import app_commands
from utils import database as db
from utils import embeds as e
from cogs.registration import player_group


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="View the current top players by score.")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await db.fetch_leaderboard(interaction.guild_id, 10)
        await interaction.response.send_message(embed=e.leaderboard_embed(rows))

    @player_group.command(name="profile", description="View your full profile and holdings.")
    async def player_profile(self, interaction: discord.Interaction):
        player = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not player:
            await interaction.response.send_message(embed=e.error("Not Registered", "You are not registered for this event."), ephemeral=True)
            return
        holdings = await db.fetch_holdings(interaction.guild_id, interaction.user.id)
        corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=e.profile_embed(player, holdings, corp), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
