import argparse
import json
import time
import logging
import tempfile
from pathlib import Path
from pysecspy.secspy_server import SecSpyServer

from aiohttp import ClientSession
import asyncio

import aiohttp
from yarl import URL

from unifi.cams.base import RetryableError, SmartDetectObjectType, UnifiCamBase


class SecuritySpyCam(UnifiCamBase):
    def __init__(self, args: argparse.Namespace, logger: logging.Logger) -> None:
        super().__init__(args, logger)
        self.snapshot_dir: str = tempfile.mkdtemp()
        self.motion_in_progress: bool = False

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        super().add_parser(parser)
        parser.add_argument("--cameranumber", "-c", required=True, help="SecuritySpy camera number")

    async def get_snapshot(self) -> Path:
        img_file = Path(self.snapshot_dir, "screen.jpg")
        url = (
            f"http://{self.args.ip}:8000"
            f"/image?cameraNum={int(self.args.cameranumber)}"
        )
        await self.fetch_to_file(url, img_file)
        return img_file

    async def get_stream_source(self, stream_index: str) -> str:
        return (
            f"rtsp://{self.args.ip}:8000"
            f"/stream?cameraNum={int(self.args.cameranumber)}"
        )

    async def run(self) -> None:
        while True:
            session = ClientSession()

            # set up eventstream from SecuritySpy
            secspy = SecSpyServer(
                session,
                self.args.ip,
                8000,
                '',
                '',
            )

            def subscriber(updated):
                k = str(list(updated.keys())[0])
                obj = updated[k]

                if "event_object" in obj and "event_type" in obj and "event_on" in obj and "live_stream" in obj:
                    # does the event relate to our camera number?
                    if f"&cameraNum={int(self.args.cameranumber)}&" in obj["live_stream"]:
                        if obj["event_type"] == "motion":

                            object_type = None
                            if obj["event_object"] == "Human":
                                object_type = SmartDetectObjectType.PERSON
                            elif obj["event_object"] == "Vehicle":
                                object_type = SmartDetectObjectType.VEHICLE
                            elif obj["event_object"] == "Animal":
                                object_type = SmartDetectObjectType.PERSON # we don't have the "animal" type defined as Unifi doesn't support it, so we'll treat them as just vanilla "motion" events

                            if object_type != None:
                                if obj["event_on"] == True:
                                    if not self.motion_in_progress:
                                        self.motion_in_progress = True
                                        self.logger.info(f"Trigger motion start {object_type}")
                                        loop = asyncio.get_running_loop()
                                        if obj["event_object"] == "Animal":
                                            tsk = loop.create_task(self.trigger_motion_start())
                                        else:
                                            tsk = loop.create_task(self.trigger_motion_start(object_type))
                            elif obj["event_on"] == False:
                                if self.motion_in_progress:
                                    self.motion_in_progress = False
                                    self.logger.info(f"Trigger motion end {object_type}")
                                    loop = asyncio.get_running_loop()
                                    tsk = loop.create_task(self.trigger_motion_stop())

                            #self.logger.info("* * * * * * * Event object=%s", obj)
                            #self.logger.info(f"* * Event time:{updated['0']['event_start']} type:{updated['0']['event_type']} active:{updated['0']['event_on']}")

            await secspy.update()
            unsub = secspy.subscribe_websocket(subscriber)

            for i in range(15000):
                await asyncio.sleep(1)

            # Close the Session
            await session.close()
            await secspy.async_disconnect_ws()
            unsub()

    #def get_extra_ffmpeg_args(self, stream_index: str) -> str:
    #    return (
    #        "-ar 32000 -ac 1 -codec:a aac -b:a 32k -c:v copy -vbsf"
    #        f' "h264_metadata=tick_rate=50000/1001:fixed_frame_rate_flag=1"'
    #    )