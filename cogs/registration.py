import discord
from discord.ext import commands
from discord import app_commands
import config
from utils import database as db
from utils import embeds as e

class RegisterButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register", style=discord.ButtonStyle.success, custom_id="register_button")
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if existing:
            await interaction.response.send_message(
                embed=e.warning("Already Registered", "You are already registered for this event."),
                ephemeral=True
            )
            return

        result = await db.register_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
        if result is None:
            await interaction.response.send_message(
                embed=e.warning("Already Registered", "You are already registered for this event."),
                ephemeral=True
            )
            return

        guild = interaction.guild
        role = guild.get_role(config.REGISTERED_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)

        count = await db.count_players(interaction.guild_id)
        try:
            await interaction.message.edit(embed=e.registration_panel(count))
        except Exception:
            pass

        await interaction.response.send_message(
            embed=e.success(
                "Registration Confirmed",
                f"Welcome, **{interaction.user.display_name}**.\n\nYou have been registered for Market Wars.\nYou will be notified when the game begins."
            ),
            ephemeral=True
        )


setup_group = app_commands.Group(name="setup", description="Setup commands.")
player_group = app_commands.Group(name="player", description="Player commands.")


class Registration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @setup_group.command(name="registration", description="Post the registration panel in the registration channel. (Gamemaster only)")
    async def setup_registration(self, interaction: discord.Interaction):
        from utils.helpers import is_gamemaster
        if not is_gamemaster(interaction):
            await interaction.response.send_message(
                embed=e.error("Access Denied", "Only Gamemasters can post the registration panel."),
                ephemeral=True
            )
            return

        if interaction.channel_id != config.REGISTRATION_CHANNEL_ID:
            channel = interaction.guild.get_channel(config.REGISTRATION_CHANNEL_ID)
            mention = channel.mention if channel else "the registration channel"
            await interaction.response.send_message(
                embed=e.error("Wrong Channel", f"The registration panel can only be posted in {mention}."),
                ephemeral=True
            )
            return

        count = await db.count_players(interaction.guild_id)
        view = RegisterButton()
        await interaction.channel.send(embed=e.registration_panel(count), view=view)
        await interaction.response.send_message(
            embed=e.success("Panel Posted", "The registration panel has been posted successfully."),
            ephemeral=True
        )

    @player_group.command(name="status", description="Check your registration and game status.")
    async def player_status(self, interaction: discord.Interaction):
        player = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not player:
            await interaction.response.send_message(
                embed=e.error("Not Registered", "You are not registered. Press the **Register** button in the registration channel to join."),
                ephemeral=True
            )
            return

        holdings = await db.fetch_holdings(interaction.guild_id, interaction.user.id)
        corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            embed=e.profile_embed(player, holdings, corp),
            ephemeral=True
        )

    async def cog_load(self):
        self.bot.add_view(RegisterButton())


async def setup(bot):
    bot.tree.add_command(setup_group)
    bot.tree.add_command(player_group)
    await bot.add_cog(Registration(bot))
