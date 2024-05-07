import logging
import os
import re
import shutil
import subprocess
import tempfile
from functools import cached_property
from urllib.parse import urlparse

from mutagen.mp4 import MP4, MP4Cover

from .api import API
from .twspace import Twspace

DEFAULT_FNAME_FORMAT = "(%(creator_name)s)%(title)s-%(id)s"
MP4_COVER_FORMAT_MAP = {"jpg": MP4Cover.FORMAT_JPEG, "png": MP4Cover.FORMAT_PNG}


class TwspaceDL:
    """Downloader class for twitter spaces"""

    def __init__(self, space: Twspace, format_str: str) -> None:
        self.space = space
        self.format_str = format_str or DEFAULT_FNAME_FORMAT
        self._tempdir = ""

    @cached_property
    def filename(self) -> str:
        """Returns the formatted filename"""
        filename = self.space.format(self.format_str)
        return filename

    @cached_property
    def dyn_url(self) -> str:
        """Returns the dynamic url i.e. the url used by the browser"""
        space = self.space
        if space["state"] == "Ended" and not space["available_for_replay"]:
            logging.error(
                (
                    "Can't Download. Space has ended, can't retrieve master url. "
                    "You can provide it with -f URL if you have it."
                )
            )
            raise ValueError("Space Ended")
        media_key = space["media_key"]
        try:
            metadata = API.live_video_stream_api.status(media_key)
        except Exception as err:
            raise RuntimeError("Space isn't available", space.source) from err
        dyn_url = metadata["source"]["location"]
        return dyn_url

    @cached_property
    def master_url(self) -> str:
        """Master URL for a space"""
        master_url = re.sub(
            r"(?<=/audio-space/).*", "master_playlist.m3u8", self.dyn_url
        )
        return master_url

    @property
    def playlist_url(self) -> str:
        response = API.client.get(self.master_url)
        response_text = response.text
        has_inner = self.has_inner_play_list(response_text)
        if not has_inner:
            return self.master_url
        else:
            playlist_suffix = response_text.splitlines()[3]
            if "#" in playlist_suffix:
                playlist_suffix = response_text.splitlines()[-1]
        domain = urlparse(self.master_url).netloc
        playlist_url = f"https://{domain}{playlist_suffix}"
        return playlist_url

    def has_inner_play_list(self, response_text):
        return "/Transcoding" in response_text

    @property
    def playlist_text(self) -> str:
        """Modify the chunks URL using the master one to be able to download"""
        playlist_url = self.playlist_url
        playlist = API.client.get(playlist_url)
        playlist_text = playlist.text
        if not self.master_url:
            master_url_wo_file = self.find_master_url_wo(self.dyn_url)
            playlist_text = re.sub(r"(?=chunk)", master_url_wo_file, playlist_text)
            return playlist_text

        # master_url_wo_file = re.sub(r"playlist.*\.m3u8.*", "", playlist_url)
        # print(master_url_wo_file)
        # if "https://" not in master_url_wo_file:
        master_url_wo_file = self.find_master_url_wo(self.master_url)
        if "https://" not in master_url_wo_file:
            master_url_wo_file = self.find_master_url_wo(self.dyn_url)
        playlist_text = re.sub(r"(?=chunk)", master_url_wo_file, playlist_text)
        return playlist_text

    def find_master_url_wo(self, target_url):
        last_slash_index = target_url.rfind('/')
        return target_url[:last_slash_index + 1]

    def write_playlist(self, save_dir: str = "./", file_name: str = '') -> None:
        """Write the modified playlist for external use"""
        file_name = file_name if file_name else self.filename
        filename = os.path.basename(file_name) + ".m3u8"
        path = os.path.join(save_dir, filename)
        with open(path, "w", encoding="utf-8") as stream_io:
            stream_io.write(self.playlist_text)
        logging.debug("%(path)s written to disk", dict(path=path))

    def download(self) -> None:
        """Download a twitter space"""
        if not shutil.which("ffmpeg"):
            raise FileNotFoundError("ffmpeg not installed")
        space = self.space
        self._tempdir = tempfile.mkdtemp(dir=".")
        self.write_playlist(save_dir=self._tempdir)
        cmd_base = [
            "ffmpeg",
            "-y",
            "-stats",
            "-v",
            "warning",
            "-i",
            "-c",
            "copy",
            "-metadata",
            f"title={space['title']}",
            "-metadata",
            f"artist={space['creator_name']}",
            "-metadata",
            f"episode_id={space['id']}",
        ]

        filename = os.path.basename(self.filename)
        filename_m3u8 = os.path.join(self._tempdir, filename + ".m3u8")
        is_audio = False
        with open(filename_m3u8, "r") as file:
            content = file.read()
            if ".aac" in content:
                is_audio = True
        extension = ".m4a" if is_audio else ".mp4"
        print(f'file extension {extension}')
        filename_old = os.path.join(self._tempdir, filename + extension)
        cmd_old = cmd_base.copy()
        cmd_old.insert(1, "-protocol_whitelist")
        cmd_old.insert(2, "file,https,httpproxy,tls,tcp")
        cmd_old.insert(8, filename_m3u8)
        cmd_old.append(filename_old)
        logging.debug("Command for the old part: %s", " ".join(cmd_old))

        try:
            subprocess.run(cmd_old, check=True)
        except subprocess.CalledProcessError as err:
            raise RuntimeError(
                " ".join(err.cmd)
                + "\nThis might be a temporary error, retry in a few minutes"
            ) from err
        if os.path.dirname(self.filename):
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        shutil.move(filename_old, self.filename + extension)

        logging.info("Finished downloading")

    def embed_cover(self) -> None:
        """Embed the user profile image as the cover art"""
        cover_url = self.space["creator_profile_image_url"]
        cover_ext = cover_url.split(".")[-1]
        try:
            response = API.client.get(cover_url)
            if cover_format := MP4_COVER_FORMAT_MAP.get(cover_ext):
                meta = MP4(f"{self.filename}.m4a")
                meta.tags["covr"] = [
                    MP4Cover(response.content, imageformat=cover_format)
                ]
                meta.save()
            else:
                logging.error(f"Unsupported user profile image format: {cover_ext}")
        except RuntimeError:
            logging.error(f"Cannot download user profile image from URL: {cover_url}")
            raise

    def cleanup(self) -> None:
        if os.path.exists(self._tempdir):
            shutil.rmtree(self._tempdir)
