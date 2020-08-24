import discord
import aiohttp
import logging

from typing import Tuple

from redbot.core.bot import Red
from redbot.core import Config

from .errors import (
    NoCredentials,
    InvalidCredentials,
    APIError,
    OutOfRequests,
)

API_URL = "https://www.cleverbot.com/getreply"
IO_API_URL = "https://cleverbot.io/1.0"

log = logging.getLogger("red.trusty-cogs.Cleverbot")


class CleverbotAPI:
    """
        All API access for both cleverbot and cleverbot.io
    """
    bot: Red
    config: Config
    instances: dict

    def __init__(self, bot):
        self.bot = bot
        self.instances = {}

    async def get_response(self, author: discord.User, text: str) -> str:
        payload = {}
        try:
            payload["key"] = await self.get_credentials()
            payload["cs"] = self.instances.get(str(author.id), "")
            payload["input"] = text
            return await self.get_cleverbotcom_response(payload, author)
        except NoCredentials:
            payload["user"], payload["key"] = await self.get_io_credentials()
            payload["nick"] = str("{}".format(self.bot.user))
            return await self.get_cleverbotio_response(payload, text)

    async def make_cleverbotio_instance(self, payload: dict) -> None:
        """Makes the cleverbot.io instance if one isn't created for the user"""
        del payload["text"]
        async with aiohttp.ClientSession() as session:
            async with session.post(IO_API_URL + "/create", json=payload) as r:
                if r.status == 200:
                    return
                elif r.status == 400:
                    try:
                        error_msg = await r.json()
                    except Exception:
                        error_msg = "Error status 400, credentials seem to be invalid"
                        pass
                    log.error(error_msg)
                    raise InvalidCredentials()
                else:
                    error_msg = "Error making instance: " + str(r.status)
                    log.error(error_msg)
                    raise APIError(error_msg)

    async def get_cleverbotio_response(self, payload: dict, text: str) -> str:
        payload["text"] = text
        async with aiohttp.ClientSession() as session:
            async with session.post(IO_API_URL + "/ask/", json=payload) as r:
                if r.status == 200:
                    data = await r.json()
                elif r.status == 400:
                    # Try to make the instance for the user first before raising the error
                    await self.make_cleverbotio_instance(payload)
                    return await self.get_cleverbotio_response(payload, text)
                else:
                    error_msg = "Error getting response: " + str(r.status)
                    log.error(error_msg)
                    raise APIError(error_msg)
        return data["response"]

    async def get_cleverbotcom_response(self, payload: dict, author: discord.User) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=payload) as r:
                # print(r.status)
                if r.status == 200:
                    try:
                        data = await r.json()
                    except UnicodeDecodeError:
                        data = await r.json(encoding="latin-1")
                    except Exception:
                        raise APIError("Error decoding cleverbot respose.")
                    self.instances[str(author.id)] = data["cs"]  # Preserves conversation status
                elif r.status == 401:
                    log.error("Cleverbot.com Invalid Credentials")
                    raise InvalidCredentials()
                elif r.status == 503:
                    log.error("Cleverbot.com Out of Requests")
                    raise OutOfRequests()
                else:
                    error_msg = "Cleverbot.com API Error " + str(r.status)
                    log.error(error_msg)
                    raise APIError(error_msg)
        return data["output"]

    async def get_credentials(self) -> str:
        key = await self.config.api()
        if key is None:
            raise NoCredentials()
        else:
            return key

    async def get_io_credentials(self) -> Tuple[str, str]:
        io_key = await self.config.io_key()
        io_user = await self.config.io_user()
        if io_key is None:
            raise NoCredentials()
        else:
            return io_user, io_key
