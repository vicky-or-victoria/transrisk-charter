import discord
from discord.ext import commands
from discord import app_commands
import config
from utils import database as db
from utils import embeds as e


corp_group = app_commands.Group(name="corp", description="Corporation commands.")


class Corporations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _require_player(self, interaction):
        player = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not player:
            await interaction.response.send_message(embed=e.error("Not Registered", "You must be registered to use corporation commands."), ephemeral=True)
            return None
        return player

    @corp_group.command(name="create", description="Create a new corporation.")
    @app_commands.describe(name="The name of your corporation.")
    async def corp_create(self, interaction: discord.Interaction, name: str):
        player = await self._require_player(interaction)
        if not player:
            return

        existing = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        if existing:
            await interaction.response.send_message(embed=e.error("Already in a Corporation", f"You are already a member of **{existing['name']}**."), ephemeral=True)
            return

        if len(name) > 32:
            await interaction.response.send_message(embed=e.error("Name Too Long", "Corporation names must be 32 characters or fewer."), ephemeral=True)
            return

        name_taken = await db.fetch_corporation_by_name(interaction.guild_id, name)
        if name_taken:
            await interaction.response.send_message(embed=e.error("Name Taken", f"A corporation named **{name}** already exists."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            corp = await conn.fetchrow("""
                INSERT INTO corporations (guild_id, name, owner_id)
                VALUES ($1, $2, $3) RETURNING *
            """, interaction.guild_id, name, interaction.user.id)
            await conn.execute("""
                INSERT INTO corp_members (guild_id, discord_id, corp_id) VALUES ($1, $2, $3)
            """, interaction.guild_id, interaction.user.id, corp['id'])

        await interaction.response.send_message(
            embed=e.success("Corporation Founded", f"**{name}** has been established.\n\nYou are the founding CEO. Invite players using `/corp invite`."),
            ephemeral=True
        )

    @corp_group.command(name="invite", description="Invite a player to your corporation.")
    @app_commands.describe(member="The player to invite.")
    async def corp_invite(self, interaction: discord.Interaction, member: discord.Member):
        player = await self._require_player(interaction)
        if not player:
            return

        corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        if not corp:
            await interaction.response.send_message(embed=e.error("No Corporation", "You are not in a corporation."), ephemeral=True)
            return

        if corp['owner_id'] != interaction.user.id:
            await interaction.response.send_message(embed=e.error("Not the CEO", "Only the CEO can invite members."), ephemeral=True)
            return

        members = await db.fetch_corp_members(corp['id'])
        if len(members) >= config.MAX_CORP_MEMBERS:
            await interaction.response.send_message(embed=e.error("Corporation Full", f"Your corporation has reached the maximum of **{config.MAX_CORP_MEMBERS}** members."), ephemeral=True)
            return

        target = await db.fetch_player(interaction.guild_id, member.id)
        if not target:
            await interaction.response.send_message(embed=e.error("Not Registered", f"**{member.display_name}** is not registered for this event."), ephemeral=True)
            return

        existing = await db.fetch_corporation_by_member(interaction.guild_id, member.id)
        if existing:
            await interaction.response.send_message(embed=e.error("Already in a Corp", f"**{member.display_name}** is already in **{existing['name']}**."), ephemeral=True)
            return

        view = CorpInviteView(corp, interaction.guild_id, interaction.user)
        await member.send(
            embed=e.info(
                "Corporation Invite",
                f"**{interaction.user.display_name}** has invited you to join **{corp['name']}**.\n\nAccept or decline below."
            ),
            view=view
        )
        await interaction.response.send_message(embed=e.success("Invite Sent", f"An invite has been sent to **{member.display_name}**."), ephemeral=True)

    @corp_group.command(name="leave", description="Leave your current corporation.")
    async def corp_leave(self, interaction: discord.Interaction):
        player = await self._require_player(interaction)
        if not player:
            return

        corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        if not corp:
            await interaction.response.send_message(embed=e.error("No Corporation", "You are not in a corporation."), ephemeral=True)
            return

        if corp['owner_id'] == interaction.user.id:
            await interaction.response.send_message(embed=e.error("You are the CEO", "CEOs cannot leave. Transfer ownership or disband the corporation first."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM corp_members WHERE guild_id = $1 AND discord_id = $2 AND corp_id = $3", interaction.guild_id, interaction.user.id, corp['id'])

        await interaction.response.send_message(embed=e.success("Left Corporation", f"You have left **{corp['name']}**."), ephemeral=True)

    @corp_group.command(name="disband", description="Disband your corporation. (CEO only)")
    async def corp_disband(self, interaction: discord.Interaction):
        player = await self._require_player(interaction)
        if not player:
            return

        corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        if not corp or corp['owner_id'] != interaction.user.id:
            await interaction.response.send_message(embed=e.error("Not the CEO", "You must be the CEO to disband the corporation."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM corp_members WHERE corp_id = $1", corp['id'])
            await conn.execute("DELETE FROM corporations WHERE id = $1", corp['id'])

        await interaction.response.send_message(embed=e.success("Corporation Disbanded", f"**{corp['name']}** has been permanently dissolved."), ephemeral=True)

    @corp_group.command(name="info", description="View information about your corporation or another by name.")
    @app_commands.describe(name="Optional: name of the corporation to look up.")
    async def corp_info(self, interaction: discord.Interaction, name: str = None):
        if name:
            corp = await db.fetch_corporation_by_name(interaction.guild_id, name)
        else:
            corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)

        if not corp:
            await interaction.response.send_message(embed=e.error("Not Found", "No corporation found."), ephemeral=True)
            return

        members = await db.fetch_corp_members(corp['id'])
        await interaction.response.send_message(embed=e.corp_embed(corp, members), ephemeral=True)

    @corp_group.command(name="deposit", description="Deposit cash into your corporation's treasury.")
    @app_commands.describe(amount="Amount to deposit.")
    async def corp_deposit(self, interaction: discord.Interaction, amount: float):
        player = await self._require_player(interaction)
        if not player:
            return

        if amount <= 0:
            await interaction.response.send_message(embed=e.error("Invalid Amount", "Amount must be greater than zero."), ephemeral=True)
            return

        corp = await db.fetch_corporation_by_member(interaction.guild_id, interaction.user.id)
        if not corp:
            await interaction.response.send_message(embed=e.error("No Corporation", "You are not in a corporation."), ephemeral=True)
            return

        if float(player['cash']) < amount:
            await interaction.response.send_message(embed=e.error("Insufficient Funds", f"You only have **${float(player['cash']):,.2f}**."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE players SET cash = cash - $1 WHERE guild_id = $2 AND discord_id = $3", amount, interaction.guild_id, interaction.user.id)
            await conn.execute("UPDATE corporations SET treasury = treasury + $1 WHERE id = $2", amount, corp['id'])

        await interaction.response.send_message(
            embed=e.success("Deposit Successful", f"**${amount:,.2f}** has been added to **{corp['name']}**'s treasury."),
            ephemeral=True
        )


class CorpInviteView(discord.ui.View):
    def __init__(self, corp, guild_id, inviter):
        super().__init__(timeout=300)
        self.corp = corp
        self.guild_id = guild_id
        self.inviter = inviter

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = await db.fetch_corporation_by_member(self.guild_id, interaction.user.id)
        if existing:
            await interaction.response.send_message(embed=e.error("Already in a Corp", "You have already joined a corporation."), ephemeral=True)
            return

        members = await db.fetch_corp_members(self.corp['id'])
        if len(members) >= 5:
            await interaction.response.send_message(embed=e.error("Corporation Full", "This corporation is now full."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO corp_members (guild_id, discord_id, corp_id) VALUES ($1, $2, $3)", self.guild_id, interaction.user.id, self.corp['id'])

        await interaction.response.send_message(embed=e.success("Welcome!", f"You have joined **{self.corp['name']}**."))
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=e.info("Declined", f"You declined the invite to **{self.corp['name']}**."))
        self.stop()


async def setup(bot):
    bot.tree.add_command(corp_group)
    await bot.add_cog(Corporations(bot))
