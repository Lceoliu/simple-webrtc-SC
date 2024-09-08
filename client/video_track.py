import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame


# no audio track
class OpenCVCapture(VideoStreamTrack):

    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        self.kind = "video"
        print("OpenCVCapture initialized, but not capturing yet.")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception("Failed to capture video frame")

        # Convert the frame to VideoFrame
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame
