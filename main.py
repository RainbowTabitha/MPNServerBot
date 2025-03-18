import discord
from discord.ext import commands, tasks
from pterosocket import PteroSocket
import json
import os
import asyncio

# Discord bot setup
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix='/', intents=intents)

config_file_path = 'config.json'

def_config_data = {
    "api_key": "",
    "servers": {},
    "origin": "",
    "disc_token": ""
}

# Load or write to config.json
if os.path.exists(config_file_path):
    with open(config_file_path, 'r') as config_file:
        config_data = json.load(config_file)
else:
    with open(config_file_path, 'w') as config_file:
        json.dump(def_config_data, config_file, indent=4)
    config_data = def_config_data  # Use the default data

# Extract necessary configuration values
api_key = config_data.get("api_key")
origin = config_data.get("origin")
disc_token = config_data.get("disc_token")
servers = config_data.get("servers", {})

# Initialize dictionaries to hold PteroSocket instances and their connection status
ptero_sockets = {}
connection_status = {}
last_message_ids = {server_id: None for server_id in servers.keys()}  # Initialize last message IDs

# User ID allowed to run start and stop commands
ALLOWED_USER_ID = 1009059379003265134

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    await initialize_ptero_sockets()  # Initialize PteroSocket connections
    read_messages.start()  # Start the read_messages loop

async def initialize_ptero_sockets():
    for server_id, server_info in servers.items():
        if origin is None or api_key is None:
            print(f"Error: Missing 'origin' or 'api_key' for server ID {server_id}.")
            continue  # Skip this server if keys are missing
        
        # Initialize PteroSocket for each server and store it in the dictionary
        ptero_socket = PteroSocket(origin, api_key, server_id, auto_connect=False)
        ptero_sockets[server_id] = ptero_socket
        connection_status[server_id] = False  # Initialize connection status to False
        await ptero_socket.connect()  # Connect to the Pterodactyl server

        # Set up event listeners for connection status
        ptero_socket.on('connect', lambda server_id=server_id: set_connection_status(server_id, True))
        ptero_socket.on('disconnect', lambda server_id=server_id: set_connection_status(server_id, False))
        ptero_socket.on('console_output', lambda data, server_id=server_id: asyncio.create_task(handle_console_output(data, server_id)))

def set_connection_status(server_id, status):
    connection_status[server_id] = status
    print(f"Connection status for server {server_id}: {'Connected' if status else 'Disconnected'}")

@tasks.loop(seconds=0.25)  # Adjust the interval as needed
async def read_messages():
    for server_id in servers.keys():
        ptero_socket = ptero_sockets.get(server_id)  # Get the socket for the current server
        if ptero_socket and connection_status.get(server_id, False):  # Check if the socket is connected
            # Fetch messages from Pterodactyl (if applicable)
            messages = await ptero_socket.get_messages(server_id)  # Replace with actual method to get messages
            for message in messages:
                # Check if the message is new
                if last_message_ids[server_id] is None or message.id > last_message_ids[server_id]:
                    channel = bot.get_channel(server_info["channel_id"])  # Get the Discord channel
                    if channel:
                        await channel.send(f"New message from {message.author}: {message.content}")  # Send new message content
                    last_message_ids[server_id] = message.id  # Update last message ID
        else:
            print(f"Error: Not connected to Pterodactyl for server ID {server_id}.")  # Debugging statement

@bot.command()
async def start(ctx, server: str):
    if ctx.author.id != ALLOWED_USER_ID:
        await ctx.send("You do not have permission to use this command.")
        return

    server_info = next((s for s in servers.values() if s["id"] == server), None)  # Get server info
    if server_info:
        ptero_socket = PteroSocket(origin, api_key, server, auto_connect=False)
        await ptero_socket.connect()
        ptero_sockets[server] = ptero_socket  # Store the socket instance
        connection_status[server] = True  # Update connection status
        await ctx.send(f"Server {server_info['name']} started!")  # Use server name
    else:
        await ctx.send("Server not found.")

@bot.command()
async def stop(ctx, server: str):
    if ctx.author.id != ALLOWED_USER_ID:
        await ctx.send("You do not have permission to use this command.")
        return

    server_info = next((s for s in servers.values() if s["id"] == server), None)  # Get server info
    if server_info:
        ptero_socket = ptero_sockets.get(server)  # Retrieve the socket instance
        if ptero_socket:
            await ptero_socket.close()
            connection_status[server] = False  # Update connection status
            await ctx.send(f"Server {server_info['name']} stopped!")  # Use server name
        else:
            await ctx.send(f"Server {server_info['name']} is not running.")
    else:
        await ctx.send("Server not found.")

async def handle_console_output(data, server_id):
    channel = bot.get_channel(servers[server_id]["channel_id"])  # Get the Discord channel
    if channel:
        await channel.send(f"Console output for server {server_id}: {data}")  # Send console output to Discord

# Run the bot
bot.run(disc_token)