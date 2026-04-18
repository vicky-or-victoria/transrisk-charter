import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import config
from utils import database as db
from utils import embeds as e
from utils.helpers import fluctuate_market, recalculate_scores, initialize_market, is_gamemaster


gm_group = app_commands.Group(name="gm", description="Gamemaster commands.")
gm_set_group = app_commands.Group(name="set", description="Set commands.", parent=gm_group)
gm_market_group = app_commands.Group(name="market", description="Market commands.", parent=gm_group)
gm_ping_group = app_commands.Group(name="ping", description="Ping commands.", parent=gm_group)


class Gamemaster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.round_timer.start()

    def cog_unload(self):
        self.round_timer.cancel()

    @tasks.loop(seconds=30)
    async def round_timer(self):
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            active_guilds = await conn.fetch("SELECT * FROM game_state WHERE active = TRUE")
        for state in active_guilds:
            if state['round_ends_at'] and datetime.utcnow() >= state['round_ends_at'].replace(tzinfo=None):
                await self._advance_round(state['guild_id'])

    @round_timer.before_loop
    async def before_round_timer(self):
        await self.bot.wait_until_ready()

    async def _advance_round(self, guild_id: int):
        state = await db.fetch_game_state(guild_id)
        new_round = state['round_number'] + 1
        duration = state['round_duration_seconds'] or config.ROUND_DURATION_SECONDS
        ends_at = datetime.utcnow() + timedelta(seconds=duration)
        await db.update_game_state(guild_id, round_number=new_round, round_ends_at=ends_at)
        await fluctuate_market(guild_id)
        await recalculate_scores(guild_id)

        channel = self.bot.get_channel(config.REGISTRATION_CHANNEL_ID)
        if channel:
            await channel.send(embed=e.round_announcement(new_round, ends_at))

    @gm_group.command(name="start", description="Start the game and begin Round 1. (Gamemaster only)")
    async def gm_start(self, interaction: discord.Interaction):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        state = await db.fetch_game_state(interaction.guild_id)
        if state['active']:
            await interaction.response.send_message(embed=e.warning("Already Active", "The game is already running."), ephemeral=True)
            return

        await initialize_market(interaction.guild_id)
        duration = state['round_duration_seconds'] or config.ROUND_DURATION_SECONDS
        ends_at = datetime.utcnow() + timedelta(seconds=duration)
        await db.update_game_state(interaction.guild_id, active=True, round_number=1, round_ends_at=ends_at)

        channel = self.bot.get_channel(config.REGISTRATION_CHANNEL_ID)
        if channel:
            registered_role = interaction.guild.get_role(config.REGISTERED_ROLE_ID)
            mention = registered_role.mention if registered_role else ""
            await channel.send(content=mention, embed=e.round_announcement(1, ends_at))

        await interaction.response.send_message(embed=e.success("Game Started", "Round 1 has begun. The market is now live."), ephemeral=True)

    @gm_group.command(name="end", description="End the game and display final results. (Gamemaster only)")
    async def gm_end(self, interaction: discord.Interaction):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        await recalculate_scores(interaction.guild_id)
        await db.update_game_state(interaction.guild_id, active=False)
        rows = await db.fetch_leaderboard(interaction.guild_id, 10)

        channel = self.bot.get_channel(config.REGISTRATION_CHANNEL_ID)
        if channel:
            registered_role = interaction.guild.get_role(config.REGISTERED_ROLE_ID)
            mention = registered_role.mention if registered_role else ""
            await channel.send(content=mention, embed=e.game_over_embed(rows))

        await interaction.response.send_message(embed=e.success("Game Ended", "The game has been ended and final scores posted."), ephemeral=True)

    @gm_group.command(name="next-round", description="Force-advance to the next round immediately. (Gamemaster only)")
    async def gm_next_round(self, interaction: discord.Interaction):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        state = await db.fetch_game_state(interaction.guild_id)
        if not state['active']:
            await interaction.response.send_message(embed=e.warning("Game Inactive", "The game is not currently running."), ephemeral=True)
            return

        await self._advance_round(interaction.guild_id)
        await interaction.response.send_message(embed=e.success("Round Advanced", "The next round has been forced."), ephemeral=True)

    @gm_set_group.command(name="round-duration", description="Set how long each round lasts. Applies from the next round onward. (Gamemaster only)")
    @app_commands.describe(minutes="Round duration in minutes. Default is 60.")
    async def gm_set_round_duration(self, interaction: discord.Interaction, minutes: int):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        if minutes < 1:
            await interaction.response.send_message(embed=e.error("Invalid Duration", "Round duration must be at least **1 minute**."), ephemeral=True)
            return

        seconds = minutes * 60
        await db.update_game_state(interaction.guild_id, round_duration_seconds=seconds)

        hours = minutes // 60
        mins = minutes % 60
        if hours and mins:
            readable = f"{hours}h {mins}m"
        elif hours:
            readable = f"{hours}h"
        else:
            readable = f"{mins}m"

        await interaction.response.send_message(
            embed=e.success("Round Duration Updated", f"Each round will now last **{readable}**.\n\nThis takes effect from the next round onward."),
            ephemeral=True
        )

    @gm_group.command(name="announce", description="Send an announcement to all registered players. (Gamemaster only)")
    @app_commands.describe(message="The announcement message to send.")
    async def gm_announce(self, interaction: discord.Interaction, message: str):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        channel = self.bot.get_channel(config.REGISTRATION_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message(embed=e.error("Channel Not Found", "Could not find the registration channel."), ephemeral=True)
            return

        registered_role = interaction.guild.get_role(config.REGISTERED_ROLE_ID)
        mention = registered_role.mention if registered_role else ""
        embed = e.info("Gamemaster Announcement", message)
        embed.set_footer(text=f"Announced by {interaction.user.display_name}  •  Market Wars")
        await channel.send(content=mention, embed=embed)
        await interaction.response.send_message(embed=e.success("Announced", "Your announcement has been sent."), ephemeral=True)

    @gm_market_group.command(name="set", description="Manually set a resource price. (Gamemaster only)")
    @app_commands.describe(resource="The resource or stock name.", price="The new price to set.")
    async def gm_market_set(self, interaction: discord.Interaction, resource: str, price: float):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE market SET price = $1 WHERE guild_id = $2 AND LOWER(resource) = LOWER($3)",
                price, interaction.guild_id, resource
            )
        if result == "UPDATE 0":
            await interaction.response.send_message(embed=e.error("Not Found", f"No resource named **{resource}** found."), ephemeral=True)
            return

        await interaction.response.send_message(embed=e.success("Price Updated", f"**{resource}** has been set to `${price:,.2f}`."), ephemeral=True)

    @gm_ping_group.command(name="players", description="Ping all registered players with a message. (Gamemaster only)")
    @app_commands.describe(message="Message to include with the ping.")
    async def gm_ping_players(self, interaction: discord.Interaction, message: str):
        if not is_gamemaster(interaction):
            await interaction.response.send_message(embed=e.error("Access Denied", "Only Gamemasters can use this command."), ephemeral=True)
            return

        channel = self.bot.get_channel(config.REGISTRATION_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message(embed=e.error("Channel Not Found", "Could not find the registration channel."), ephemeral=True)
            return

        registered_role = interaction.guild.get_role(config.REGISTERED_ROLE_ID)
        mention = registered_role.mention if registered_role else ""
        embed = e.warning("Attention Players", message)
        embed.set_footer(text=f"From {interaction.user.display_name}  •  Market Wars")
        await channel.send(content=mention, embed=embed)
        await interaction.response.send_message(embed=e.success("Pinged", "All registered players have been pinged."), ephemeral=True)


async def setup(bot):
    bot.tree.add_command(gm_group)
    await bot.add_cog(Gamemaster(bot))
