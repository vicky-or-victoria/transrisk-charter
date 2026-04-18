import discord
from datetime import datetime

BRAND_COLOR = 0x2B2D31
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
WARNING_COLOR = 0xFEE75C
INFO_COLOR = 0x5865F2
GOLD_COLOR = 0xF1C40F

def base(title: str, description: str = None, color: int = BRAND_COLOR) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.utcnow()
    return embed

def success(title: str, description: str = None) -> discord.Embed:
    return base(title, description, SUCCESS_COLOR)

def error(title: str, description: str = None) -> discord.Embed:
    return base(title, description, ERROR_COLOR)

def warning(title: str, description: str = None) -> discord.Embed:
    return base(title, description, WARNING_COLOR)

def info(title: str, description: str = None) -> discord.Embed:
    return base(title, description, INFO_COLOR)

def gold(title: str, description: str = None) -> discord.Embed:
    return base(title, description, GOLD_COLOR)

def registration_panel(count: int) -> discord.Embed:
    embed = discord.Embed(
        title="__Market Wars — Grand Event__",
        description=(
            "Welcome to **Market Wars**, the ultimate strategy competition.\n\n"
            "Build your fortune through trading stocks and raw materials, "
            "forge powerful corporations, crush rivals in economic warfare, "
            "and rise to the top of the leaderboard.\n\n"
            "**How to join:**\n"
            "> Press the **Register** button below to secure your spot.\n"
            "> Registration grants you a role and starting capital once the game begins.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=GOLD_COLOR
    )
    embed.add_field(name="Registered Players", value=f"**{count}** players signed up", inline=True)
    embed.add_field(name="Status", value="**Open**", inline=True)
    embed.set_footer(text="Market Wars  •  Registration")
    return embed

def profile_embed(player, holdings, corp) -> discord.Embed:
    embed = base(f"{player['username']}'s Profile")
    embed.add_field(name="Cash", value=f"**${player['cash']:,.2f}**", inline=True)
    embed.add_field(name="Score", value=f"**{player['score']:,.0f} pts**", inline=True)
    embed.add_field(name="War Wins", value=f"**{player['wins']}**", inline=True)

    if corp:
        embed.add_field(name="Corporation", value=f"**{corp['name']}**", inline=True)
        embed.add_field(name="Corp Health", value=f"**{corp['health']}%**", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

    if holdings:
        lines = "\n".join(f"> **{h['resource']}** — {h['quantity']:,.2f} units" for h in holdings)
        embed.add_field(name="Holdings", value=lines, inline=False)

    embed.set_footer(text="Market Wars  •  Player Profile")
    return embed

def market_embed(market_rows) -> discord.Embed:
    embed = gold("Market Board")
    resources = [r for r in market_rows if r['kind'] == 'resource']
    stocks = [r for r in market_rows if r['kind'] == 'stock']

    if resources:
        lines = "\n".join(f"> **{r['resource']}** — `${r['price']:,.2f}`" for r in resources)
        embed.add_field(name="Raw Materials", value=lines, inline=False)

    if stocks:
        lines = "\n".join(f"> **{r['resource']}** — `${r['price']:,.2f}`" for r in stocks)
        embed.add_field(name="Stocks", value=lines, inline=False)

    embed.set_footer(text="Market Wars  •  Prices update each round")
    return embed

def leaderboard_embed(rows) -> discord.Embed:
    embed = gold("__Leaderboard — Top Players__")
    medals = ["**`1st`**", "**`2nd`**", "**`3rd`**"]
    lines = []
    for i, row in enumerate(rows):
        prefix = medals[i] if i < 3 else f"**`{i+1}th`**"
        lines.append(f"{prefix}  {row['username']} — **{row['score']:,.0f} pts**  ·  ${row['cash']:,.2f}")
    embed.description = "\n".join(lines) if lines else "*No players yet.*"
    embed.set_footer(text="Market Wars  •  Leaderboard")
    return embed

def corp_embed(corp, members) -> discord.Embed:
    embed = base(f"Corporation — {corp['name']}", color=INFO_COLOR)
    embed.add_field(name="Treasury", value=f"**${corp['treasury']:,.2f}**", inline=True)
    embed.add_field(name="Health", value=f"**{corp['health']}%**", inline=True)
    embed.add_field(name="Members", value=f"**{len(members)}**", inline=True)
    if members:
        lines = "\n".join(f"> {m['username']}" for m in members)
        embed.add_field(name="Roster", value=lines, inline=False)
    embed.set_footer(text="Market Wars  •  Corporation")
    return embed

def round_announcement(round_number: int, ends_at) -> discord.Embed:
    embed = base(f"Round {round_number} Has Begun", color=SUCCESS_COLOR)
    embed.description = (
        "A new round of trading is now open.\n\n"
        "**Available actions this round:**\n"
        "> `/trade buy` · `/trade sell`\n"
        "> `/corp deposit` · `/upgrade buy`\n"
        "> `/market event` · `/war declare`\n\n"
        f"**Round ends:** <t:{int(ends_at.timestamp())}:R>"
    )
    embed.set_footer(text="Market Wars  •  Round Update")
    return embed

def game_over_embed(rows) -> discord.Embed:
    embed = gold("__Market Wars — Game Over__")
    if rows:
        winner = rows[0]
        embed.description = (
            f"The game has concluded.\n\n"
            f"**Winner: {winner['username']}** with **{winner['score']:,.0f} pts**\n\n"
            "**Final Standings:**"
        )
        medals = ["1st", "2nd", "3rd"]
        lines = []
        for i, row in enumerate(rows):
            prefix = medals[i] if i < 3 else f"{i+1}th"
            lines.append(f"> **{prefix}** — {row['username']}  ·  {row['score']:,.0f} pts")
        embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
    embed.set_footer(text="Market Wars  •  Thanks for playing")
    return embed
