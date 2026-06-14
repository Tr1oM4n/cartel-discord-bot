import discord
from discord.ext import commands
from discord import app_commands
import requests
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OLYMPUS_TOKEN = os.getenv("OLYMPUS_TOKEN")
GANG_ID = os.getenv("GANG_ID")

API = f"https://stats.olympus-entertainment.com/api/v3.0/gangs/{GANG_ID}/"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

active_run = None

db = sqlite3.connect("database.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS owed(
user_id TEXT PRIMARY KEY,
name TEXT,
money INTEGER DEFAULT 0
)
""")

db.commit()


def get_bank():

    headers = {
        "Authorization": f"Token {OLYMPUS_TOKEN}"
    }

    r = requests.get(API, headers=headers)

    if r.status_code != 200:
        raise Exception("API Error")

    return r.json()["bank"]


def add_money(user, amount):

    cur.execute(
        "SELECT money FROM owed WHERE user_id=?",
        (str(user.id),)
    )

    row = cur.fetchone()

    if row:

        cur.execute(
            """
            UPDATE owed
            SET money=money+?
            WHERE user_id=?
            """,
            (
                amount,
                str(user.id)
            )
        )

    else:

        cur.execute(
            """
            INSERT INTO owed
            VALUES(?,?,?)
            """,
            (
                str(user.id),
                user.name,
                amount
            )
        )

    db.commit()


@bot.event
async def on_ready():

    await bot.tree.sync()

    print("BOT ONLINE")


@bot.tree.command()
async def start(
    interaction: discord.Interaction
):

    global active_run

    if active_run:

        return await interaction.response.send_message(
            "A cartel is already active."
        )

    bank = get_bank()

    active_run = {
        "bank": bank,
        "players": []
    }

    await interaction.response.send_message(
        f"Started.\nBank: ${bank:,}"
    )


@bot.tree.command()
async def add(
    interaction: discord.Interaction,
    member: discord.Member
):

    global active_run

    if not active_run:

        return await interaction.response.send_message(
            "No active cartel."
        )

    if member in active_run["players"]:

        return await interaction.response.send_message(
            "Already added."
        )

    active_run["players"].append(member)

    await interaction.response.send_message(
        f"{member.display_name} added."
    )


@bot.tree.command()
async def end(
    interaction: discord.Interaction
):

    global active_run

    if not active_run:

        return await interaction.response.send_message(
            "No active cartel."
        )

    end_bank = get_bank()

    diff = end_bank - active_run["bank"]

    players = active_run["players"]

    if not players:

        active_run = None

        return await interaction.response.send_message(
            "No players."
        )

    share = diff // len(players)

    for p in players:
        add_money(
            p,
            share
        )

    msg = "\n".join(
        [
            f"{x.display_name}: ${share:,}"
            for x in players
        ]
    )

    active_run = None

    await interaction.response.send_message(
        f"""
Finished

Profit:
${diff:,}

{msg}
"""
    )


@bot.tree.command()
async def owed(
    interaction: discord.Interaction
):

    cur.execute(
        """
        SELECT name,money
        FROM owed
        ORDER BY money DESC
        """
    )

    rows = cur.fetchall()

    if not rows:

        return await interaction.response.send_message(
            "Nobody owed."
        )

    text = ""

    for n, m in rows:

        text += (
            f"{n} → ${m:,}\n"
        )

    await interaction.response.send_message(
        text
    )


@bot.tree.command()
async def cashout(
    interaction: discord.Interaction
):

    cur.execute(
        """
        UPDATE owed
        SET money=0
        WHERE user_id=?
        """,
        (
            str(
                interaction.user.id
            ),
        )
    )

    db.commit()

    await interaction.response.send_message(
        "Balance reset."
    )


bot.run(DISCORD_TOKEN)