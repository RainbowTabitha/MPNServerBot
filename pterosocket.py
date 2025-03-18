import asyncio
import aiohttp
import json
from aiohttp import ClientSession, ClientWebSocketResponse
from node_events import EventEmitter

class PteroSocket(EventEmitter):
    def __init__(self, origin, api_key, server_no, auto_connect=True):
        super().__init__()
        self.origin = origin
        self.api_key = api_key
        self.server_no = server_no
        self.ws: ClientWebSocketResponse = None  # Aiohttp WebSocket client
        if auto_connect:
            asyncio.create_task(self.connect())

    async def api_request(self, service, body='', method='GET'):
        async with ClientSession() as session:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            async with session.request(method, f"{self.origin}/api/client/servers/{self.server_no}/{service}", headers=headers, json=body) as response:
                return await response.json()

    async def get_new_login(self):
        response = await self.api_request('websocket')
        # print("API Response:", response)  # Debugging output
        if "data" in response:
            return response['data']

    async def auth_login(self, token=""):
        if token:
            await self.write({"event": "auth", "args": [token]})
        else:
            login = await self.get_new_login()
            if not login:
                raise Exception("Couldn't connect - server didn't provide credentials.")
            token = login['token']
            await self.write({"event": "auth", "args": [token]})

    async def read_packet(self, packet):
        # Check if the message is a text message
        if packet.type == aiohttp.WSMsgType.TEXT:
            try:
                data = json.loads(packet.data)  # Extract the data and load it as JSON
                event = data['event']
                args = data.get('args', [])

                if event == 'stats':
                    if args[0].startswith("{"):
                        self.emit('stats', json.loads(args[0]))
                elif event == 'token expiring':
                    await self.auth_login()
                    self.emit(event.replace(" ", "_"))
                else:
                    self.emit(event.replace(" ", "_"), args[0] if args else None)
            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON: {e}")
        else:
            # Handle other types of WebSocket messages if needed
            print(f"Received non-text message: {packet.type}")

    async def connect(self):
        login = await self.get_new_login()
        if not login:
            raise Exception("Couldn't connect - server didn't provide credentials.")
        if self.ws:
            await self.close()
        token = login['token']
        socket = login['socket']
        
        # Using aiohttp for the WebSocket connection
        async with ClientSession() as session:
            async with session.ws_connect(socket, origin=self.origin) as ws:
                self.ws = ws
                await self.auth_login(token)
                self.emit('start')

                async for data in self.ws:
                    await self.read_packet(data)

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
            self.emit("close", "Connection closed by user")

    async def write(self, packet):
        if self.ws:
            await self.ws.send_str(json.dumps(packet))

    async def write_command(self, command_text):
        await self.write({"event": "send command", "args": [command_text]})

    async def write_power(self, command_text):
        await self.write({"event": "set state", "args": [command_text]})
