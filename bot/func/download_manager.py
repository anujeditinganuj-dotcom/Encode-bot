# Developed by ARGON telegram: @REACTIVEARGON
import asyncio

from bot.logger import LOGGER

log = LOGGER(__name__)


class DownloadManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DownloadManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._semaphore = asyncio.Semaphore(4)
        self._initialized = True
        log.info("DownloadManager initialized with 4 concurrent slots")

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()


download_manager = DownloadManager()
