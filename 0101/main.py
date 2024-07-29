import discord
from discord.ext import commands
import os
import datetime
import asyncio
import sqlite3
from dotenv import load_dotenv
from binary_guide import pages

load_dotenv()

def update_current_count(conn, server_id, type, count):
    sql = ''' UPDATE channels
              SET current_count = ?
              WHERE server_id = ? AND type = ? '''
    try:
        cur = conn.cursor()
        cur.execute(sql, (count, server_id, type))
        conn.commit()
        print("Current count updated!")
    except sqlite3.Error as e:
        print("SQLite error:", e)


def get_current_count(conn, server_id, type):
    cur = conn.cursor()
    cur.execute("SELECT current_count FROM channels WHERE server_id=? AND type=?", (server_id, type,))
    row = cur.fetchone()
    print("Current count retrieved from Database!")
    return row[0] if row else 0

def has_permission():
    async def predicate(ctx):
        required_permissions = discord.Permissions(administrator=True)
        return ctx.author.guild_permissions >= required_permissions

    return commands.check(predicate)

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        print("Database Connected!")
        return conn
    except sqlite3.Error as e:
        print("SQLite error:", e)
    return conn

def main():
    database = r"Subi Counting/channels.db"

    conn = create_connection(database)
    if conn is not None:
        with conn:
            create_table(conn)
            print("Database Table Created!")
    else:
        print("Error: Could not establish a connection to the database.")

def create_table(conn):
    sql_create_channels_table = """CREATE TABLE IF NOT EXISTS channels (
                                    server_id INTEGER,
                                    type TEXT,
                                    channel_id INTEGER,
                                    current_count INTEGER DEFAULT 0,  
                                    PRIMARY KEY (server_id, type)
                                );"""

    sql_create_cooldown_table = """CREATE TABLE IF NOT EXISTS cooldown (
                                    server_id INTEGER,
                                    user_id INTEGER,
                                    cooldown_type TEXT,
                                    cooldown_time TEXT,
                                    PRIMARY KEY (server_id, user_id, cooldown_type)
                                );"""

    try:
        c = conn.cursor()
        c.execute(sql_create_channels_table)
        c.execute(sql_create_cooldown_table)
        print('Database tables created!')
    except sqlite3.Error as e:
        print(e)

def update_channel(conn, server_id, count_type, channel_id):
    """
    Update the counting channel for the specified type in the database.
    """
    sql = """ UPDATE channels
              SET channel_id = ?
              WHERE server_id = ? AND type = ?"""
    try:
        cur = conn.cursor()
        cur.execute(sql, (channel_id, server_id, count_type))
        conn.commit()
        print("Channel Updated!")
    except sqlite3.Error as e:
        print("SQLite error:", e)

def insert_channel(conn, server_id, type, channel_id):
    sql = ''' INSERT OR REPLACE INTO channels(server_id, type, channel_id)
              VALUES(?,?,?) '''
    try:
        cur = conn.cursor()
        cur.execute(sql, (server_id, type, channel_id))
        conn.commit()
        print("Channel Inserted!")
    except sqlite3.Error as e:
        print("SQLite error:", e)

def get_channel(conn, server_id, type):
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM channels WHERE server_id=? AND type=?", (server_id, type,))
    row = cur.fetchone()
    print("Channel Retrieved from Database!")
    return row[0] if row else None

def delete_channel(conn, type):
    sql = 'DELETE FROM channels WHERE type=?'
    cur = conn.cursor()
    cur.execute(sql, (type,))
    conn.commit()
    print("Channel Deleted")

def main():
    database = r"channels.db"

    conn = create_connection(database)
    with conn:
        create_table(conn)
        print("Database Table Created!")

TOKEN = os.getenv('TOKEN')
LASTCOUNTED = {}
COUNTING_COOLDOWN = {}

intents = discord.Intents.all()
intents.message_content = True

global conn
conn = None

client = commands.Bot(command_prefix = "/", intents = intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    main()

    global COUNTINGCHANNELS
    COUNTINGCHANNELS = {}

    global conn
    database = r"channels.db"
    conn = create_connection(database)
    if conn is not None:
        for guild in client.guilds:
            server_id = guild.id
            counting_channels = {
                'decimal': get_channel(conn, server_id, 'decimal'),
                'binary': get_channel(conn, server_id, 'binary')
            }
            COUNTINGCHANNELS[server_id] = counting_channels
            print("Database Loaded for server:", guild.name)
            print("Counting channels for", guild.name, ":", counting_channels)

    await client.tree.sync()

@client.event
async def on_message(message):
    global COUNTING_COOLDOWN, COUNTINGCHANNELS, conn
    CORRECT_EMOJI = '✅'
    INCORRECT_EMOJI = '❌'

    if message.author == client.user:
        return

    server_id = message.guild.id
    counting_channels = COUNTINGCHANNELS.get(server_id)

    if counting_channels is not None:
        for count_type, channel_id in counting_channels.items():
            if channel_id == message.channel.id:
                if count_type == 'decimal':
                    current_count = get_current_count(conn, server_id, count_type)

                    try:
                        number = int(message.content)
                    except ValueError:
                        return  

                    COOLDOWN = COUNTING_COOLDOWN.get(f"{message.author.id}_decimal")
                    if COOLDOWN and datetime.datetime.now() - COOLDOWN < datetime.timedelta(seconds=15):
                        await message.add_reaction(INCORRECT_EMOJI)
                        await message.channel.send(f"Oops! {message.author.mention} you can only count once every 15 seconds.")
                        await message.channel.send(f"Oops! {message.author.mention} ruined it at {current_count}! The Next Number is Now 1.")
                        COUNTING_COOLDOWN = {}  # Reset all cooldowns
                        update_current_count(conn, server_id, count_type, 0)
                        return

                    if number == current_count + 1:
                        await message.add_reaction(CORRECT_EMOJI)
                        COUNTING_COOLDOWN = {}
                        COUNTING_COOLDOWN[f"{message.author.id}_decimal"] = datetime.datetime.now()
                        update_current_count(conn, server_id, count_type, current_count + 1)

                    else:
                        await message.add_reaction(INCORRECT_EMOJI)
                        await message.channel.send(f"Oops! {message.author.mention} ruined it at {current_count}! The Next Number is Now 1.")
                        COUNTING_COOLDOWN = {}  # Reset all cooldowns
                        update_current_count(conn, server_id, count_type, 0)

                elif count_type == 'binary':
                    current_count = get_current_count(conn, server_id, count_type)
                    COOLDOWN_BINARY = COUNTING_COOLDOWN.get(f"{message.author.id}_binary", {})

                    try:
                        binary_number = int(message.content, 2)
                    except ValueError:
                        return

                    if COOLDOWN_BINARY and datetime.datetime.now() - COOLDOWN_BINARY < datetime.timedelta(seconds=15):
                        await message.add_reaction(INCORRECT_EMOJI)
                        await message.channel.send(f"Oops! {message.author.mention} you can only count binary once every 15 seconds.")
                        await message.channel.send(f"Oops! {message.author.mention} ruined it at {current_count}! The Next Number is Now 1.")
                        COUNTING_COOLDOWN = {}  # Reset all cooldowns
                        update_current_count(conn, server_id, count_type, 0)
                        return

                    if binary_number == current_count + 1:
                        await message.add_reaction(CORRECT_EMOJI)
                        COUNTING_COOLDOWN = {}
                        COUNTING_COOLDOWN[f"{message.author.id}_binary"] = datetime.datetime.now()
                        update_current_count(conn, server_id, count_type, current_count + 1)

                    else:
                        await message.add_reaction(INCORRECT_EMOJI)
                        await message.channel.send(f"Oops! {message.author.mention} ruined it at {current_count}! The Next Number is Now 1.")
                        COUNTING_COOLDOWN = {}  # Reset all cooldowns
                        update_current_count(conn, server_id, count_type, 0)


@client.hybrid_command(name='set_count')
@commands.has_permissions(administrator=True)
async def set_count(ctx, type: str, count: int):
    database = r'channels.db'
    conn = create_connection(database)
    if conn is None:
        await ctx.send("Error: Could not establish a connection to the database.", ephemeral=True)
        return

    try:
        server_id = ctx.guild.id

        if type.lower() == 'decimal':
            if count is None:
                await ctx.send('Please set a number!', ephemeral=True)
                return
            if not isinstance(count, int):
                await ctx.send('Please set a valid number!', ephemeral=True)
                return
            update_current_count(conn, server_id, type.lower(), count)
            await ctx.send(f"Current count updated to: {count}")
        elif type.lower() == 'binary':
            if count is None:
                await ctx.send('Please set a number!', ephemeral=True)
                return
            if not isinstance(count, int):
                await ctx.send('Please set a valid number!', ephemeral=True)
                return
            update_current_count(conn, server_id, type.lower(), count)
            await ctx.send(f"Current count updated to: {count}")

        else:
            await ctx.send('Invalid type! Please specify either "decimal" or "binary".', ephemeral=True)

    except sqlite3.Error as e:
        print("SQLite error:", e)
        await ctx.send("An error occurred while accessing the database.", ephemeral=True)
    finally:
        conn.close()



#Command to set counting channels.
@client.hybrid_command(brief="Set or change the counting channels. Types: Decimal or Binary")
@has_permission()
async def setup(ctx: commands.Context, type: str, channel: discord.TextChannel):
    database = r"channels.db"
    conn = create_connection(database)

    if conn is None:
        await ctx.send("Error: Could not establish a connection to the database.", ephemeral=True)
        return

    try:
        server_id = ctx.guild.id
        
        if type.lower() == 'decimal':
            current_channel_id = get_channel(conn, server_id, 'decimal')
            if current_channel_id:
                update_channel(conn, server_id, 'decimal', channel.id)
                await ctx.send(f"Counting channel updated to {channel.mention} for decimal counting.", ephemeral=True)
            else:
                insert_channel(conn, server_id, 'decimal', channel.id)
                await ctx.send(f"Counting channel set to {channel.mention} for decimal counting.", ephemeral=True)
            update_current_count(conn, server_id, 'decimal', 0)
        
        elif type.lower() == 'binary':
            current_channel_id = get_channel(conn, server_id, 'binary')
            if current_channel_id:
                update_channel(conn, server_id, 'binary', channel.id)
                await ctx.send(f"Counting channel updated to {channel.mention} for binary counting.", ephemeral=True)
            else:
                insert_channel(conn, server_id, 'binary', channel.id)
                await ctx.send(f"Counting channel set to {channel.mention} for binary counting.", ephemeral=True)
            update_current_count(conn, server_id, 'binary', 0)
        
        else:
            await ctx.send("Invalid type. Please use 'decimal' or 'binary'.", ephemeral=True)
        
        counting_channels = {
            'decimal': get_channel(conn, server_id, 'decimal'),
            'binary': get_channel(conn, server_id, 'binary')
        }
        COUNTINGCHANNELS[server_id] = counting_channels
    
    except sqlite3.Error as e:
        print("SQLite error:", e)
        await ctx.send("An error occurred while accessing the database.", ephemeral=True)
    
    finally:
        if conn:
            conn.close()

@client.hybrid_command(brief="Learn Command")
async def learn(ctx: commands.Context):

    embeds = []
    for page in pages:
        embed = discord.Embed(title=page["title"], description=page["description"], color=discord.Color.blue())
        for field in page["fields"]:
            embed.add_field(name=field["name"], value=field["value"], inline=False)
        embeds.append(embed)

    index = 0
    message = await ctx.send(embed=embeds[index])
    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")
    await message.add_reaction("❌")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️", "❌"]

    while True:
        try:
            reaction, user = await client.wait_for("reaction_add", timeout=60, check=check)
            if str(reaction.emoji) == "➡️" and index < len(embeds) - 1:
                index += 1
                await message.edit(embed=embeds[index])
            elif str(reaction.emoji) == "⬅️" and index > 0:
                index -= 1
                await message.edit(embed=embeds[index])
            elif str(reaction.emoji) == "❌":
                await message.delete()
                break
            await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            await message.delete()
            break

client.run(TOKEN)
