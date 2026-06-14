import os
import sqlite3
import requests
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OLYMPUS_TOKEN = os.getenv("OLYMPUS_TOKEN")
GANG_ID = os.getenv("GANG_ID", "54347")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

if not OLYMPUS_TOKEN:
    raise RuntimeError("OLYMPUS_TOKEN is missing.")

API_URL = f"https://stats.olympus-entertainment.com/api/v3.0/gangs/{GANG_ID}/"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

active_run = None

db = sqlite3.connect("database.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS owed (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    money INTEGER DEFAULT 0
)
""")

db.commit()


def get_bank():
    headers = {
        "Authorization": f"Token {OLYMPUS_TOKEN}"
    }

    response = requests.get(API_URL, headers=headers, timeout=15)

    if response.status_code != 200:
        raise Exception(f"Olympus API error: {response.status_code} - {response.text}")

    data = response.json()
    return int(data["bank"])


def add_money(user: discord.Member, amount: int):
    user_id = str(user.id)

    cur.execute("SELECT money FROM owed WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row:
        cur.execute(
            "UPDATE owed SET money = money + ?, name = ? WHERE user_id = ?",
            (amount, user.display_name, user_id)
        )
    else:
        cur.execute(
            "INSERT INTO owed (user_id, name, money) VALUES (?, ?, ?)",
            (user_id, user.display_name, amount)
        )

    db.commit()


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"BOT ONLINE: {bot.user}")


@bot.tree.command(name="start", description="Start a new cartel run.")
async def start(interaction: discord.Interaction):
    global active_run

    if active_run is not None:
        await interaction.response.send_message("A cartel run is already active.")
        return

    try:
        bank = get_bank()
    except Exception as e:
        await interaction.response.send_message(f"Failed to fetch gang bank: `{e}`")
        return

    active_run = {
        "start_bank": bank,
        "players": []
    }

    await interaction.response.send_message(
        f"Cartel run started.\nStart Bank: `${bank:,}`"
    )


@bot.tree.command(name="add", description="Add a player to the active cartel run.")
async def add(interaction: discord.Interaction, member: discord.Member):
    global active_run

    if active_run is None:
        await interaction.response.send_message("No active cartel run.")
        return

    if member.id in [p.id for p in active_run["players"]]:
        await interaction.response.send_message(f"{member.display_name} is already added.")
        return

    active_run["players"].append(member)

    await interaction.response.send_message(
        f"{member.display_name} added to the cartel run."
    )


@bot.tree.command(name="active", description="Show the active cartel run.")
async def active(interaction: discord.Interaction):
    if active_run is None:
        await interaction.response.send_message("No active cartel run.")
        return

    players = active_run["players"]

    if players:
        player_text = "\n".join([f"- {p.display_name}" for p in players])
    else:
        player_text = "No players added yet."

    await interaction.response.send_message(
        f"Active Cartel Run\nStart Bank: `${active_run['start_bank']:,}`\n\nPlayers:\n{player_text}"
    )


@bot.tree.command(name="end", description="End the active cartel run and split the profit.")
async def end(interaction: discord.Interaction):
    global active_run

    if active_run is None:
        await interaction.response.send_message("No active cartel run.")
        return

    players = active_run["players"]

    if not players:
        active_run = None
        await interaction.response.send_message("Cartel run ended, but no players were added.")
        return

    try:
        end_bank = get_bank()
    except Exception as e:
        await interaction.response.send_message(f"Failed to fetch gang bank: `{e}`")
        return

    start_bank = active_run["start_bank"]
    profit = end_bank - start_bank
    share = profit // len(players)

    for player in players:
        add_money(player, share)

    player_lines = "\n".join(
        [f"{player.display_name}: `${share:,}`" for player in players]
    )

    active_run = None

    await interaction.response.send_message(
        f"Cartel run finished.\n\n"
        f"Start Bank: `${start_bank:,}`\n"
        f"End Bank: `${end_bank:,}`\n"
        f"Profit: `${profit:,}`\n"
        f"Players: `{len(players)}`\n"
        f"Each Share: `${share:,}`\n\n"
        f"{player_lines}"
    )


@bot.tree.command(name="owed", description="Show all owed balances.")
async def owed(interaction: discord.Interaction):
    cur.execute("SELECT name, money FROM owed WHERE money != 0 ORDER BY money DESC")
    rows = cur.fetchall()

    if not rows:
        await interaction.response.send_message("Nobody is owed money.")
        return

    text = "\n".join([f"{name}: `${money:,}`" for name, money in rows])

    await interaction.response.send_message(
        f"Owed Balances\n\n{text}"
    )


@bot.tree.command(name="cashout", description="Reset only your own owed balance.")
async def cashout(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    cur.execute("SELECT money FROM owed WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if not row or row[0] == 0:
        await interaction.response.send_message("You have no balance to cash out.")
        return

    old_money = row[0]

    cur.execute("UPDATE owed SET money = 0 WHERE user_id = ?", (user_id,))
    db.commit()

    await interaction.response.send_message(
        f"{interaction.user.display_name} cashed out.\nPrevious Balance: `${old_money:,}`\nCurrent Balance: `$0`"
    )


@bot.tree.command(name="cancel", description="Cancel the active cartel run.")
async def cancel(interaction: discord.Interaction):
    global active_run

    if active_run is None:
        await interaction.response.send_message("No active cartel run.")
        return

    active_run = None

    await interaction.response.send_message("Active cartel run cancelled.")


bot.run(DISCORD_TOKEN)