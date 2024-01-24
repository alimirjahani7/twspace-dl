import os
import re
import uuid
import shutil
import requests
import concurrent.futures
import mutagen.id3 as mid3
from dataclasses import dataclass
from urllib.parse import urlparse
from requests_futures.sessions import FuturesSession


class TwitterSpace:
    @dataclass
    class SpacePlaylists:
        chunk_server: str
        dyn_url: str
        master_url: str

    @dataclass
    class Chunk:
        url: str
        filename: str

    @staticmethod
    def getPlaylists(dyn_url=None):
        dataLocation = dyn_url
        dataLocation = re.sub(
            r"(dynamic_playlist\.m3u8((?=\?)(\?type=[a-z]{4,}))?|master_playlist\.m3u8(?=\?)(\?type=[a-z]{4,}))",
            "master_playlist.m3u8", dataLocation)
        dataComponents = urlparse(dataLocation)
        dataServer = f"{dataComponents.scheme}://{dataComponents.hostname}"
        dataPath = dataComponents.path
        playlistRequest = requests.get(f"{dataServer}{dataPath}")
        playlistResponse = playlistRequest.text.split('\n')[-2]
        playlistUrl = f"{dataServer}{playlistResponse}"
        chunkServer = f"{dataServer}{dataPath[:-20]}"
        if playlistResponse == "#EXT-X-ENDLIST":
            return TwitterSpace.SpacePlaylists(chunkServer[:-14], f"{dataServer}{dataPath}", f"{dataServer}{dataPath}")
        else:
            return TwitterSpace.SpacePlaylists(chunkServer, f"{dataServer}{dataPath}", playlistUrl)

    @staticmethod
    def getChunks(playlists):
        m3u8Request = requests.get(playlists.master_url)
        m3u8Data = m3u8Request.text
        chunkList = list()
        del m3u8Request
        for chunk in re.findall(r"chunk_\d{19}_\d+_a\.aac", m3u8Data):
            chunkList.append(TwitterSpace.Chunk(f"{playlists.chunk_server}{chunk}", chunk))
        return chunkList

    @staticmethod
    def detect_remove_partial_headers(file_path):
        byteseq = bytes([0x49, 0x44, 0x33, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3F, 0x50, 0x52, 0x49, 0x56])
        with open(file_path, 'rb') as file:
            data = file.read()

        if not data.startswith(byteseq):
            sequence_index = data.find(byteseq)

            if sequence_index != -1:
                modified_data = data[sequence_index:]
                with open(file_path, 'wb') as file:
                    file.write(modified_data)
        else:
            return

    @staticmethod
    def downloadChunks(chunklist, filename, path=os.getcwd()):
        uniqueFoldername = str(uuid.uuid4().hex)  # Create A Unique Folder Name for the Program to operate in
        if os.path.isdir(path) is not True:
            os.makedirs(path)  # Do I even need this?

        if os.path.isdir(os.path.join(path, uniqueFoldername)) is not True:
            os.makedirs(os.path.join(path, uniqueFoldername))
        chunkpath = os.path.join(path, uniqueFoldername)

        session = FuturesSession(max_workers=os.cpu_count())

        for chunk in chunklist:
            chunk.url = session.get(chunk.url)
        print("Finished Getting URLs, Waiting for responses")
        concurrent.futures.wait([fchunk.url for fchunk in chunklist], timeout=5,
                                return_when=concurrent.futures.ALL_COMPLETED)

        for chunk in chunklist:
            with open(os.path.join(chunkpath, chunk.filename), "wb") as chunkWriter:
                chunkWriter.write(chunk.url.result().content)
            del chunkWriter

        print("Finished Downloading Chunks")

        with open(os.path.join(path, f"{filename}.aac"), "wb") as tempAAC:
            for file in sorted(os.listdir(chunkpath)):
                file = os.path.join(chunkpath, file)
                TwitterSpace.detect_remove_partial_headers(file)
                audio = mid3.ID3()
                audio.save(file)

                with open(file, "rb") as fileReader:
                    shutil.copyfileobj(fileReader, tempAAC)
        shutil.rmtree(chunkpath)

    def _download_playlist(self):
        m3u8_request = requests.get(self.playlists.master_url, timeout=10)
        filename = re.search(r'[a-zA-Z]+_([A-Za-z0-9]+(\.(m3u8)+)+)', self.playlists.master_url)[0]
        with open(os.path.join(self.path, filename), 'w', encoding='utf-8') as m3u8file:
            m3u8file.write(m3u8_request.text)

    def _display_info(self):
        space_information = ["[TWITTER SPACE STREAM INFORMATION]"]
        if self.dyn_url:
            space_information.append(f"Dynamic URL: {self.dyn_url}")
        space_information.append(f"Master URL: {self.playlists.master_url}")

    def __init__(self, dyn_url=None, filename=None, path=None):
        self.dyn_url = dyn_url
        self.filename = filename
        self.path = path
        self.playlists = TwitterSpace.getPlaylists(dyn_url=self.dyn_url)
        self._display_info()
        chunks = TwitterSpace.getChunks(self.playlists)
        TwitterSpace.downloadChunks(chunks, self.filename, path=self.path)
