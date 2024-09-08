import asyncio
import uuid
from aiohttp import web
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer,
    VideoStreamTrack,
    RTCStatsReport,
    RTCTransportStats,
)
from aiortc.contrib.media import MediaRecorder, MediaRelay, MediaStreamTrack
from aiortc.contrib.signaling import TcpSocketSignaling, BYE
import logging
from typing import Any, List, Dict, Set
from dataclasses import dataclass
import numpy as np
import cv2
import uuid as UUID
from web_video_track import WebTrack
import webbrowser
import os
import datetime

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(message)s",
    filename="server.log",
    filemode="w",
)


@dataclass
class Client:
    ip: str
    port_num: int
    uuid: str
    pc: RTCPeerConnection = None
    recorder: MediaRecorder = None
    video: MediaStreamTrack = None

    last_rtp_time: datetime.datetime = None
    total_bytes: int = None


class Port:
    def __init__(self, port: int, server: Any = None):
        self.port = port

        self.app = web.Application()
        self.runner = web.AppRunner(self.app, handle_signals=True)
        self.site = None
        # 默认的ICE服务器
        ice_servers = [
            RTCIceServer(urls='stun:stun.l.google.com:19302'),
        ]
        ice_config = RTCConfiguration(iceServers=ice_servers)
        self.ice_config = ice_config

        self.server = server
        assert self.server is not None
        self.clients: List[Client] = []

        logging.debug(f"\n\nPort {self.port} created\n\n")

    async def start(self, host='127.0.0.1'):
        self.app.router.add_post(f"/port/offer", self.offer)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, self.port)
        await self.site.start()
        logging.debug(f"Port {self.port} started on {self.site.name}\n")

    async def stop(self):
        await self.runner.cleanup()
        for c in self.clients:
            await c.pc.close()
            if c in self.server.clients:
                self.server.clients.remove(c)
        logging.debug(f"Port {self.port} stopped")

    def remove_client_by_pc(self, pc: RTCPeerConnection):
        for c in self.clients:
            if c.pc == pc:
                self.clients.remove(c)
                if self.server and c in self.server.clients:
                    self.server.clients.remove(c)

    def remove_client_by_uuid(self, uuid: str):
        for c in self.clients:
            if c.uuid == uuid:
                self.clients.remove(c)
                if self.server and c in self.server.clients:
                    self.server.clients.remove(c)

    async def offer(self, request: web.Request):
        try:
            params = await request.json()

            logging.debug(
                30 * "-"
                + f"\nReceived offer from {request.remote} on port {self.port}\n"
                + 30 * "-"
            )
            # 得到client的offer
            offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])
            # 创建一个RTCPeerConnection对象
            pc = RTCPeerConnection(self.ice_config)

            # 为每个client创建一个uuid
            uuid = f"{self.port}-{request.remote}-{str(UUID.uuid4())}"

            # 为RTCPeerConnection对象添加uuid_属性
            pc.uuid = uuid
            # 创建一个client对象
            client = Client(
                ip=request.remote,
                port_num=self.port,
                uuid=uuid,
                pc=pc,
            )
            # 同步client到server
            self.clients.append(client)
            if self.server is not None and client not in self.server.clients:
                self.server.clients.append(client)
            pc.client = client

            @pc.on("icecandidate")
            async def on_icecandidate(candidate):
                if candidate:
                    await request.send_json({"candidate": candidate})

            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                print(f"ICE connection state is {pc.iceConnectionState}")
                if pc.iceConnectionState == "failed":
                    await pc.close()
                elif pc.iceConnectionState == "closed":
                    await pc.close()
                    if pc.uuid:
                        self.remove_client_by_uuid(pc.uuid)

            @pc.on("track")
            def on_track(track: VideoStreamTrack):

                if track.kind == "video":
                    if pc.client:
                        media_relay = MediaRelay()
                        # 转发
                        pc.client.video = media_relay.subscribe(track=track)

                    # for debug
                    async def show_video_stream():
                        while True:
                            frame = await track.recv()
                            cv2.imshow('frame', frame.to_ndarray(format="bgr24"))
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break

                    asyncio.ensure_future(show_video_stream())

            # 设置client的offer
            await pc.setRemoteDescription(offer)
            logging.debug(f"set offer for: {request.remote}")
            # 创建一个answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            logging.debug(f"set answer for: {request.remote}")

            print(f"client: {uuid} 信令交换成功")

            return web.json_response(
                {
                    "sdp": pc.localDescription.sdp,
                    "type": pc.localDescription.type,
                }
            )
        except Exception as e:
            logging.debug(
                f"error when port {self.port} handling offer for {request.remote}:\n\t{str(e)}"
            )
            print(
                f"error when port {self.port} handling offer for {request.remote}:\n\t{str(e)}"
            )
            return web.json_response({"error": str(e)}, status=500)

    async def get_current_bitrate(self, peer_connection: RTCPeerConnection):
        if not hasattr(peer_connection, 'client'):
            return 0
        client: Client = peer_connection.client
        stats = await peer_connection.getStats()

        trans_report: RTCTransportStats | None = None

        for report in stats.values():
            if report.type == 'transport':
                trans_report = report

        if not trans_report:
            return 0

        now = trans_report.timestamp
        total_byte = trans_report.bytesReceived

        if client.last_rtp_time is None:
            client.last_rtp_time = now
            client.total_bytes = total_byte
            return 0

        bits = 8 * (total_byte - client.total_bytes)

        interval = (now - client.last_rtp_time).total_seconds()
        bps = bits / interval
        client.last_rtp_time = now
        client.total_bytes = total_byte
        return bps

    async def get_load(self, is_print: bool = True) -> float:
        '''
        计算当前端口的平均bps
        '''
        avg_bps = 0

        for c in self.clients:
            pc = c.pc
            bps = await self.get_current_bitrate(pc)
            avg_bps += bps
        avg_bps /= len(self.clients)
        if is_print:
            print(f"avg load of port {self.port} is {avg_bps/8000}KB/S")
        return avg_bps


class Server:
    def __init__(self, max_port_clients=5):
        # ports: 一个server可以有多个port来接受不同的client的连接
        self.ports: Dict[int, Port] = {}
        # clients: 一个server的所有client的连接
        self.clients: List[Client] = []

        self.app = web.Application()
        self.runner = web.AppRunner(self.app)
        self.site = None
        # max_port_clients: 每个port最多可以接受的client数量
        self.max_port_clients = max_port_clients
        # next_port: 下一个接受视频流port的编号，每次新建一个port，编号+1
        self.next_port = 16666
        # control_port: 一个固定port用于接受client的连接请求(如果要修改，必须把client端的port也修改)
        self.control_port = 9999
        # 为control_port添加一个接受client连接请求的route
        self.app.add_routes([web.post("/control/offer", self.handle_initial_offer)])

        self.app.add_routes([web.get("/", self.index)])
        self.app.router.add_get('/static/{filename}', self.static)

        self.app.add_routes([web.get("/stats", self.get_stats)])

    async def start(self, host='127.0.0.1'):
        logging.debug(f"Starting server on {host}:{self.control_port}")
        self.host = host
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, self.control_port)
        await self.site.start()
        logging.debug("Server started")

    async def open_browser(self):
        if not self.host:
            raise ValueError("Host is not set")
        webbrowser.open("http://" + self.host + ":" + str(self.control_port))

    async def index(self, request: web.Request):
        '''
        index地址
        '''
        p = os.path.join(BASE_PATH, "static", "server_ui.html")
        return web.FileResponse(p)

    async def static(self, request: web.Request):
        filename = request.match_info.get('filename', 'server_ui.html')
        file_path = os.path.abspath(os.path.join(BASE_PATH, 'static', filename))
        return web.FileResponse(file_path)

    async def stop(self):
        logging.debug("Stopping server...")
        await self.runner.cleanup()
        self.clients.clear()
        logging.debug("Server stopped")

    async def handle_initial_offer(self, request: web.Request):
        '''
        当client试图连接server时, 会先发送一个请求到control_port, server会根据当前的port的负载情况, 选择一个port来接受client的连接 <br>
        目前默认的请求是空的get请求
        '''
        try:
            logging.debug(f"Handling initial offer from {request.remote}")
            least_loaded_port = await self.get_least_loaded_port()

            if least_loaded_port is None:
                logging.debug("Creating new port")
                new_port_num = self.next_port
                # 每次新建一个port，编号+1, 当然也可以预先把port的编号存储起来
                self.next_port += 1
                self.ports[new_port_num] = Port(new_port_num, server=self)
                assert new_port_num in self.ports.keys()

                new_port = self.ports[new_port_num]
                await new_port.start()

                least_loaded_port = new_port
            # 返回给client一个port的编号
            response = {"port": least_loaded_port.port}
            logging.debug(f"Ready to assign port {least_loaded_port.port} for client")
            return web.json_response(response)
        except Exception as e:
            logging.error(f"Error handling initial offer: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def get_least_loaded_port(self) -> Port:
        if not self.ports:
            return None

        async def m_min(p: Port):
            return await p.get_load()

        loads = {}
        for pt_num, pt in self.ports.items():
            loads[pt_num] = await pt.get_load()
        least_loaded_port: Port = self.ports[min(loads, key=loads.get)]
        least_load = min(loads.values())
        if least_load > 1e5:
            return None
        return least_loaded_port

    async def get_stats(self, request: web.Request):
        '''
        返回当前server的所有数据,包括视频流
        ---
        数据格式: <br>
        \{
            [
                {"port_num": port_num, "client_id": client_uuid, "bps": avg_bps,
                "video": video_frame,"ice_connection_state": ice_connection_state},
                ...
            ]
        \}
        '''
        stats = {}
        clients_num = len(self.clients)
        for client in self.clients:
            pc = client.pc
            port = self.ports[client.port_num]
            track = WebTrack(client.video)
            stats[client.uuid] = {
                "port_num": client.port_num,
                "client_id": client.uuid,
                "bps": await port.get_load(),
                # "video": (await track.recv()).tolist(),
                "video": await track.img_recv(),
                "ice_connection_state": pc.iceConnectionState,
            }
        return web.json_response(stats)


async def main():
    server = Server(max_port_clients=5)
    await server.start()
    await server.open_browser()
    print(f"Server started on {server.site.name}")

    await asyncio.Event().wait()


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
