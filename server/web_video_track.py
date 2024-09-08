from aiortc import MediaStreamTrack
from av import VideoFrame
import numpy as np
import cv2
import base64


class WebTrack(MediaStreamTrack):
    def __init__(self, track: MediaStreamTrack):
        super().__init__()
        self.track = track

    async def recv(self) -> VideoFrame:
        frame = await self.track.recv()
        # return frame.to_ndarray(format="bgr24")
        return frame

    async def decoded_recv(self) -> np.ndarray:
        frame: VideoFrame = await self.track.recv()
        return frame.to_ndarray(format="bgr24")

    async def img_recv(self) -> str:
        '''
        返回base64编码的图片
        '''
        img = await self.decoded_recv()
        quality = 90
        _, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        encoded_img = base64.b64encode(buffer).decode("utf-8")
        return encoded_img
