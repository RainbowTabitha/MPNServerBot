# pterosocket.py
import asyncio
import json
import websockets
import aiohttp
from aiohttp import ClientSession
from node_events import EventEmitter

class PteroSocket(EventEmitter):
    def __init__(self, origin, api_key, server_no, auto_connect=True):
        super().__init__()
        self.origin = origin
        self.api_key = api_key
        self.server_no = server_no
        self.ws = None
        if auto_connect:
            asyncio.run(self.connect())

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
        data = json.loads(packet)
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

    async def connect(self):
        login = await self.get_new_login()
        if not login:
            raise Exception("Couldn't connect - server didn't provide credentials.")
        if self.ws:
            await self.close()
        token = login['token']
        socket = login['socket']
        
        self.ws = await websockets.connect(socket, origin=self.origin)
        await self.auth_login(token)
        self.emit('start')

        async def listen():
            async for data in self.ws:
                await self.read_packet(data)

        asyncio.create_task(listen())

    async def close(self):
        await self.ws.close()
        self.ws = None
        self.emit("close", "Connection closed by user")

    async def write(self, packet):
        await self.ws.send(json.dumps(packet))

    async def write_command(self, command_text):
        await self.write({"event": "send command", "args": [command_text]})

    async def write_power(self, command_text):
        await self.write({"event": "set state", "args": [command_text]})