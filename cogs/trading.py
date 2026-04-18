import discord
from discord.ext import commands
from discord import app_commands
from utils import database as db
from utils import embeds as e

market_group = app_commands.Group(name="market", description="Market commands.")
trade_group = app_commands.Group(name="trade", description="Trade commands.")


class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _require_active_player(self, interaction):
        state = await db.fetch_game_state(interaction.guild_id)
        if not state or not state['active']:
            await interaction.response.send_message(embed=e.error("Game Not Active", "The game is not currently running."), ephemeral=True)
            return None, None
        player = await db.fetch_player(interaction.guild_id, interaction.user.id)
        if not player:
            await interaction.response.send_message(embed=e.error("Not Registered", "You are not registered for this event."), ephemeral=True)
            return None, None
        return player, state

    @market_group.command(name="view", description="View the current market prices for all resources and stocks.")
    async def market_view(self, interaction: discord.Interaction):
        rows = await db.fetch_market(interaction.guild_id)
        if not rows:
            await interaction.response.send_message(embed=e.warning("Market Empty", "The market has not been initialized yet."), ephemeral=True)
            return
        await interaction.response.send_message(embed=e.market_embed(rows), ephemeral=True)

    @trade_group.command(name="buy", description="Buy a resource or stock from the market.")
    @app_commands.describe(resource="The resource or stock to buy.", quantity="How many units to purchase.")
    async def trade_buy(self, interaction: discord.Interaction, resource: str, quantity: float):
        player, _ = await self._require_active_player(interaction)
        if not player:
            return

        if quantity <= 0:
            await interaction.response.send_message(embed=e.error("Invalid Quantity", "Quantity must be greater than zero."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            market_row = await conn.fetchrow("SELECT * FROM market WHERE guild_id = $1 AND LOWER(resource) = LOWER($2)", interaction.guild_id, resource)
            if not market_row:
                await interaction.response.send_message(embed=e.error("Not Found", f"**{resource}** is not available on the market."), ephemeral=True)
                return

            total_cost = float(market_row['price']) * quantity
            if float(player['cash']) < total_cost:
                await interaction.response.send_message(
                    embed=e.error("Insufficient Funds", f"This purchase costs **${total_cost:,.2f}** but you only have **${float(player['cash']):,.2f}**."),
                    ephemeral=True
                )
                return

            await conn.execute("UPDATE players SET cash = cash - $1 WHERE guild_id = $2 AND discord_id = $3", total_cost, interaction.guild_id, interaction.user.id)
            await conn.execute("""
                INSERT INTO holdings (guild_id, discord_id, resource, quantity)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, discord_id, resource) DO UPDATE SET quantity = holdings.quantity + EXCLUDED.quantity
            """, interaction.guild_id, interaction.user.id, market_row['resource'], quantity)

            new_price = max(1.0, round(float(market_row['price']) * (1 + 0.01 * quantity / 10), 2))
            await conn.execute("UPDATE market SET price = $1 WHERE guild_id = $2 AND resource = $3", new_price, interaction.guild_id, market_row['resource'])

        await interaction.response.send_message(
            embed=e.success(
                "Purchase Complete",
                f"You bought **{quantity:,.2f}x {market_row['resource']}** for **${total_cost:,.2f}**.\n\nNew balance: **${float(player['cash']) - total_cost:,.2f}**"
            ),
            ephemeral=True
        )

    @trade_group.command(name="sell", description="Sell a resource or stock back to the market.")
    @app_commands.describe(resource="The resource or stock to sell.", quantity="How many units to sell.")
    async def trade_sell(self, interaction: discord.Interaction, resource: str, quantity: float):
        player, _ = await self._require_active_player(interaction)
        if not player:
            return

        if quantity <= 0:
            await interaction.response.send_message(embed=e.error("Invalid Quantity", "Quantity must be greater than zero."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            holding = await conn.fetchrow("SELECT * FROM holdings WHERE guild_id = $1 AND discord_id = $2 AND LOWER(resource) = LOWER($3)", interaction.guild_id, interaction.user.id, resource)
            if not holding or float(holding['quantity']) < quantity:
                held = float(holding['quantity']) if holding else 0
                await interaction.response.send_message(
                    embed=e.error("Insufficient Holdings", f"You only hold **{held:,.2f}** units of **{resource}**."),
                    ephemeral=True
                )
                return

            market_row = await conn.fetchrow("SELECT * FROM market WHERE guild_id = $1 AND LOWER(resource) = LOWER($2)", interaction.guild_id, resource)
            total_earned = float(market_row['price']) * quantity

            await conn.execute("UPDATE players SET cash = cash + $1 WHERE guild_id = $2 AND discord_id = $3", total_earned, interaction.guild_id, interaction.user.id)
            await conn.execute("UPDATE holdings SET quantity = quantity - $1 WHERE guild_id = $2 AND discord_id = $3 AND resource = $4", quantity, interaction.guild_id, interaction.user.id, holding['resource'])
            await conn.execute("DELETE FROM holdings WHERE guild_id = $1 AND discord_id = $2 AND resource = $3 AND quantity <= 0", interaction.guild_id, interaction.user.id, holding['resource'])

            new_price = max(1.0, round(float(market_row['price']) * (1 - 0.01 * quantity / 10), 2))
            await conn.execute("UPDATE market SET price = $1 WHERE guild_id = $2 AND resource = $3", new_price, interaction.guild_id, market_row['resource'])

        await interaction.response.send_message(
            embed=e.success(
                "Sale Complete",
                f"You sold **{quantity:,.2f}x {holding['resource']}** for **${total_earned:,.2f}**.\n\nNew balance: **${float(player['cash']) + total_earned:,.2f}**"
            ),
            ephemeral=True
        )

    @market_group.command(name="event", description="Trigger a market event that boosts or crashes a resource.")
    @app_commands.describe(resource="The resource or stock to target.")
    async def market_event(self, interaction: discord.Interaction, resource: str):
        player, _ = await self._require_active_player(interaction)
        if not player:
            return

        if float(player['cash']) < 750:
            await interaction.response.send_message(embed=e.error("Insufficient Funds", "Triggering a market event costs **$750**."), ephemeral=True)
            return

        pool = await db.get_pool()
        async with pool.acquire() as conn:
            market_row = await conn.fetchrow("SELECT * FROM market WHERE guild_id = $1 AND LOWER(resource) = LOWER($2)", interaction.guild_id, resource)
            if not market_row:
                await interaction.response.send_message(embed=e.error("Not Found", f"**{resource}** was not found on the market."), ephemeral=True)
                return

            import random
            direction = random.choice(["boom", "crash"])
            modifier = random.uniform(0.20, 0.40) if direction == "boom" else random.uniform(-0.40, -0.20)
            new_price = max(1.0, round(float(market_row['price']) * (1 + modifier), 2))

            await conn.execute("UPDATE players SET cash = cash - 750 WHERE guild_id = $1 AND discord_id = $2", interaction.guild_id, interaction.user.id)
            await conn.execute("UPDATE market SET price = $1 WHERE guild_id = $2 AND resource = $3", new_price, interaction.guild_id, market_row['resource'])

        direction_text = "surged" if direction == "boom" else "crashed"
        change_pct = abs(modifier) * 100
        embed = e.warning(
            "Market Event Triggered",
            f"**{market_row['resource']}** has {direction_text} by **{change_pct:.1f}%**!\n\nNew price: **${new_price:,.2f}**"
        )
        embed.set_footer(text=f"Triggered by {interaction.user.display_name}  •  Market Wars")
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message(embed=e.success("Event Triggered", f"Market event for **{market_row['resource']}** has been broadcast."), ephemeral=True)


async def setup(bot):
    bot.tree.add_command(market_group)
    bot.tree.add_command(trade_group)
    await bot.add_cog(Trading(bot))
