import asyncio
import json
import requests
from aiortc.contrib.signaling import BYE, TcpSocketSignaling
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCStatsReport,
    RTCRtpReceiver,
)
from video_track import (
    OpenCVCapture,
)
import logging

logging.basicConfig(level=logging.INFO)
is_connected = False


async def run(pc: RTCPeerConnection, server_ip: str):
    # Initial communication to get the assigned port
    response = requests.post(f"http://{server_ip}:9999/control/offer")
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logging.error(f"failed to connet to the server: {e}")
        return
    assigned_port = response.json()["port"]
    logging.info(f"assigned port successfully: {assigned_port}")

    offer_url = f"http://{server_ip}:{assigned_port}/port/offer"

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            response = requests.post(
                offer_url,
                json={"candidate": candidate.to_dict()},
            )
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logging.error(f"failed when sending ice candidate: {e}")

            if response.status_code == 200:
                logging.info("ice candidate sent successfully")

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        logging.info(f"ICE connection state is {pc.iceConnectionState}")
        if pc.iceConnectionState == "failed":
            await pc.close()
        elif pc.iceConnectionState == "closed":
            await pc.close()
            is_connected = False
            logging.info(f"closed connection")
        elif pc.iceConnectionState == "checking":
            logging.info(f"checking connection")
        elif pc.iceConnectionState == "completed":
            logging.info(f"connection completed")
            is_connected = True

    local_video = OpenCVCapture()
    pc.addTrack(local_video)

    # Create an offer and set local description
    try:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
    except Exception as e:
        logging.error(f"failed to create offer: {e}")
        return

    # Send the offer to the assigned port and receive the answer
    response = requests.post(
        offer_url,
        json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
    )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logging.error(f"failed to get answer: {e}\n {response.text}")
        return
    answer = response.json()
    logging.info(20 * "-" + "\nreceived answer successfully\n" + 20 * "-")

    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
    )

    # Run event loop
    while True:
        await asyncio.sleep(0.1)


async def log_rtc_stat(pc: RTCPeerConnection):
    stats = await pc.getStats()
    recv = pc.getReceivers()

    for r in recv:
        print(f"\n\nreceiver: {r}\n\n")
    for report in stats.values():
        print(f"\n\nreports: {report}\n\n")
    await asyncio.sleep(1)


if __name__ == "__main__":
    # import argparse

    # parser = argparse.ArgumentParser(description="WebRTC video client")
    # parser.add_argument("server_ip", help="The IP address of the WebRTC server")
    # args = parser.parse_args()
    # server_ip = args.server_ip
    server_ip = "127.0.0.1"
    pc = RTCPeerConnection()

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(log_rtc_stat(pc))
        loop.run_until_complete(run(pc, server_ip if server_ip else '127.0.0.1'))

    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())
