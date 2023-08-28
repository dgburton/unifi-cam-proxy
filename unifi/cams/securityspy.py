import argparse
import json
import logging
import tempfile
from pathlib import Path

import aiohttp
from yarl import URL

from unifi.cams.base import UnifiCamBase


class SecuritySpyCam(UnifiCamBase):
    def __init__(self, args: argparse.Namespace, logger: logging.Logger) -> None:
        super().__init__(args, logger)
        self.snapshot_dir: str = tempfile.mkdtemp()
        self.motion_in_progress: bool = False

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        super().add_parser(parser)
        parser.add_argument("--username", "-u", required=True, help="SecuritySpy username")
        parser.add_argument("--password", "-p", required=True, help="SecuritySpy password")
        parser.add_argument("--cameranumber", "-c", required=True, help="SecuritySpy camera number")

    async def get_snapshot(self) -> Path:
        img_file = Path(self.snapshot_dir, "screen.jpg")
        url = (
            f"http://{self.args.ip}"
            f"/image?cameraNum={int(self.args.cameranumber)}"
        )
        await self.fetch_to_file(url, img_file)
        return img_file

    async def get_stream_source(self, stream_index: str) -> str:
        return (
            f"rtsp://{self.args.ip}:8000"
            f"/stream?cameraNum={int(self.args.cameranumber)}"
        )
