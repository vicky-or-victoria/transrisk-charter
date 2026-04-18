import discord
from discord.ext import commands
from discord import app_commands
import random
import config
from utils import database as db
from utils import embeds as e


war_group = app_commands.Group(name="war", description="War commands.")


class War(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @war_group.command(name="declare", description="Declare war on another player.")
    @app_commands.describe(target="The player you wish to attack.")
    async def war_declare(self, interaction: discord.Interaction, target: discord.Member):
        state = await db.fetch_game_state(interaction.guild_id)
        if not state or not state['active']:
            await interaction.response.send_message(embed=e.error("Game Not Active", "The game is not currently running."), ephemeral=True)
            return

        if target.id == interaction.user.id:
            await interaction.response.send_message(embed=e.error("Invalid Target", "You cannot declare war on yourself."), ephemeral=True)
            return

        attacker = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not attacker:
            await interaction.response.send_message(embed=e.error("Not Registered", "You are not registered for this event."), ephemeral=True)
            return

        defender = await db.fetch_player(interaction.guild_id, target.id)
        if not defender:
            await interaction.response.send_message(embed=e.error("Not Registered", f"**{target.display_name}** is not registered."), ephemeral=True)
            return

        if float(attacker['cash']) < config.WAR_COST:
            await interaction.response.send_message(embed=e.error("Insufficient Funds", f"Declaring war costs **${config.WAR_COST:,}**."), ephemeral=True)
            return

        view = WarConfirmView(attacker, defender, target, interaction.guild_id, state['round_number'])
        embed = e.warning(
            "Declare War?",
            f"You are about to declare war on **{target.display_name}**.\n\n"
            f"**Cost:** ${config.WAR_COST:,}\n"
            f"**If you win:** Steal cash and assets from your target.\n"
            f"**If you lose:** Your corporation takes damage and you lose resources.\n\n"
            f"War outcomes are determined by a weighted roll based on your wealth and corp power."
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class WarConfirmView(discord.ui.View):
    def __init__(self, attacker, defender, defender_member, guild_id, round_number):
        super().__init__(timeout=60)
        self.attacker = attacker
        self.defender = defender
        self.defender_member = defender_member
        self.guild_id = guild_id
        self.round_number = round_number

    @discord.ui.button(label="Confirm Attack", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = await db.get_pool()

        attacker_power = float(self.attacker['cash']) + self.attacker['wins'] * 200
        defender_power = float(self.defender['cash']) + self.defender['wins'] * 200

        total = attacker_power + defender_power
        attacker_wins = random.random() < (attacker_power / total if total > 0 else 0.5)

        async with pool.acquire() as conn:
            await conn.execute("UPDATE players SET cash = cash - $1 WHERE guild_id = $2 AND discord_id = $3", config.WAR_COST, self.guild_id, interaction.user.id)

            if attacker_wins:
                stolen_cash = round(float(self.defender['cash']) * random.uniform(0.05, 0.20), 2)
                stolen_cash = min(stolen_cash, float(self.defender['cash']))
                await conn.execute("UPDATE players SET cash = cash - $1 WHERE guild_id = $2 AND discord_id = $3", stolen_cash, self.guild_id, self.defender['discord_id'])
                await conn.execute("UPDATE players SET cash = cash + $1, wins = wins + 1 WHERE guild_id = $2 AND discord_id = $3", stolen_cash, self.guild_id, interaction.user.id)

                defender_corp = await db.fetch_corporation_by_member(self.guild_id, self.defender['discord_id'])
                if defender_corp:
                    damage = random.randint(5, 20)
                    await conn.execute("UPDATE corporations SET health = GREATEST(0, health - $1) WHERE id = $2", damage, defender_corp['id'])

                await conn.execute("""
                    INSERT INTO wars (guild_id, attacker_id, defender_id, result, round_number)
                    VALUES ($1, $2, $3, 'attacker_win', $4)
                """, self.guild_id, interaction.user.id, self.defender['discord_id'], self.round_number)

                result_embed = e.success(
                    "Victory!",
                    f"Your forces overwhelmed **{self.defender_member.display_name}**.\n\n"
                    f"**Stolen:** ${stolen_cash:,.2f}\n"
                    f"**Their corporation** took damage."
                )
                try:
                    await self.defender_member.send(embed=e.error(
                        "You Were Attacked",
                        f"**{interaction.user.display_name}** declared war on you and won.\n\n"
                        f"**You lost:** ${stolen_cash:,.2f} and your corporation took structural damage."
                    ))
                except Exception:
                    pass

            else:
                lost_cash = round(float(self.attacker['cash']) * random.uniform(0.05, 0.15), 2)
                await conn.execute("UPDATE players SET cash = cash - $1 WHERE guild_id = $2 AND discord_id = $3", lost_cash, self.guild_id, interaction.user.id)

                attacker_corp = await db.fetch_corporation_by_member(self.guild_id, interaction.user.id)
                if attacker_corp:
                    damage = random.randint(10, 25)
                    await conn.execute("UPDATE corporations SET health = GREATEST(0, health - $1) WHERE id = $2", damage, attacker_corp['id'])

                await conn.execute("UPDATE players SET wins = wins + 1 WHERE guild_id = $1 AND discord_id = $2", self.guild_id, self.defender['discord_id'])
                await conn.execute("""
                    INSERT INTO wars (guild_id, attacker_id, defender_id, result, round_number)
                    VALUES ($1, $2, $3, 'defender_win', $4)
                """, self.guild_id, interaction.user.id, self.defender['discord_id'], self.round_number)

                result_embed = e.error(
                    "Defeated",
                    f"Your assault on **{self.defender_member.display_name}** failed.\n\n"
                    f"**Lost:** ${lost_cash:,.2f}\n"
                    f"**Your corporation** took heavy damage."
                )
                try:
                    await self.defender_member.send(embed=e.success(
                        "Attack Repelled",
                        f"**{interaction.user.display_name}** declared war on you, but you successfully defended."
                    ))
                except Exception:
                    pass

        await interaction.response.send_message(embed=result_embed, ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=e.info("Cancelled", "War declaration has been cancelled."), ephemeral=True)
        self.stop()


async def setup(bot):
    bot.tree.add_command(war_group)
    await bot.add_cog(War(bot))
