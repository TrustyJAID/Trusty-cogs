from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
import os
import aiohttp
import discord

API_URL = "https://www.cleverbot.com/getreply"
IO_API_URL = "https://cleverbot.io/1.0"


class CleverbotError(Exception):
    pass

class NoCredentials(CleverbotError):
    pass

class InvalidCredentials(CleverbotError):
    pass

class APIError(CleverbotError):
    pass

class OutOfRequests(CleverbotError):
    pass

class OutdatedCredentials(CleverbotError):
    pass


class Cleverbot(getattr(commands, "Cog", object)):
    """Cleverbot rewritten for V3 from https://github.com/Twentysix26/26-Cogs/tree/master/cleverbot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 127486454786)
        default_global = {"api":None, "io_user":None, "io_key":None}
        default_guild = {"channel":None, "toggle":False}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.instances = {}

    @commands.group(no_pm=True, invoke_without_command=True)
    async def cleverbot(self, ctx, *, message):
        """Talk with cleverbot"""
        author = ctx.message.author
        channel = ctx.message.channel
        async with channel.typing():
            try:
                result = await self.get_response(author, message)
            except NoCredentials:
                await ctx.send("The owner needs to set the credentials first.\n"
                                                     "See: `[p]cleverbot apikey` or `[p]cleverbot ioapikey`")
            except APIError as e:
                await ctx.send("Error contacting the API. Error code: {}".format(e))
            except InvalidCredentials:
                await ctx.send("The token that has been set is not valid.\n"
                                                     "See: `[p]cleverbot apikey`")
            except OutOfRequests:
                await ctx.send("You have ran out of requests for this month. "
                                                     "The free tier has a 5000 requests a month limit.")
            except OutdatedCredentials:
                await ctx.send("You need a valid cleverbot.com api key for this to "
                                                     "work. The old cleverbot.io service will soon be no "
                                                     "longer active. See `[p]help cleverbot apikey`")
            else:
                await ctx.send(result)

    @cleverbot.command(pass_context=True)
    @checks.mod_or_permissions(manage_channels=True)
    async def toggle(self, ctx):
        """Toggles reply on mention"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).toggle():
            await self.config.guild(guild).toggle.set(True)
            await ctx.send("I will reply on mention.")
        else:
            await self.config.guild(guild).toggle.set(False)
            await ctx.send("I won't reply on mention anymore.")
    
    @cleverbot.command(pass_context=True)
    @checks.mod_or_permissions(manage_channels=True)
    async def channel(self, ctx, channel: discord.TextChannel=None):
        """Toggles channel for automatic replies"""
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.message.channel
        await self.config.guild(guild).channel.set(channel.id)
        await ctx.send("I will reply in {}".format(channel))

    @cleverbot.command()
    @checks.is_owner()
    async def apikey(self, ctx, key: str=None):
        """Sets token to be used with cleverbot.com
        You can get it from https://www.cleverbot.com/api/
        Use this command in direct message to keep your
        token secret"""
        await self.config.api.set(key)
        await ctx.send("Credentials set.")

    @cleverbot.command()
    @checks.is_owner()
    async def ioapikey(self, ctx, io_user: str=None, io_key: str=None):
        """Sets token to be used with cleverbot.io
        You can get it from https://www.cleverbot.io/
        Use this command in direct message to keep your
        token secret"""
        await self.config.io_user.set(io_user)
        await self.config.io_key.set(io_key)
        await ctx.send("Credentials set.")

    async def get_response(self, author, text):
        payload = {}
        try:
            payload["key"] = await self.get_credentials()
            payload["cs"] = self.instances.get(str(author.id), "")
            payload["input"] = text
            return await self.get_cleverbotcom_response(payload, author)
        except NoCredentials:
            guild = author.guild
            if guild is None:
                return
            payload["user"], payload["key"] = await self.get_io_credentials()
            payload["nick"] = str("{}#{}".format(guild.me.name, guild.me.discriminator))
            return await self.get_cleverbotio_response(payload, text)

    async def make_cleverbotio_instance(self, payload):
        """Makes the cleverbot.io instance if one isn't created for the user"""
        del payload["text"]
        async with self.session.post(IO_API_URL+"/create", json=payload) as r:
            if r.status == 200:
                return
            elif r.status == 400:
                raise InvalidCredentials()
            else:
                raise APIError("Error making instance: " + str(r.status))            

    async def get_cleverbotio_response(self, payload, text):
        payload["text"] = text
        async with self.session.post(IO_API_URL+"/ask/", json=payload) as r:
            if r.status == 200:
                data = await r.json()
            elif r.status == 400:
                # Try to make the instance for the user first before raising the error
                await self. make_cleverbotio_instance(payload)
                return await self.get_cleverbotio_response(payload, text)
            else:
                raise APIError("Error getting response: " + str(r.status))
        return data["response"]

    async def get_cleverbotcom_response(self, payload, author):
        async with self.session.get(API_URL, params=payload) as r:
            # print(r.status)
            if r.status == 200:
                data = await r.json()
                self.instances[str(author.id)] = data["cs"] # Preserves conversation status
            elif r.status == 401:
                raise InvalidCredentials()
            elif r.status == 503:
                raise OutOfRequests()
            else:
                raise APIError(str(r.status))
        return data["output"]


    async def get_credentials(self):
        key = await self.config.api()
        if key is None:
            raise NoCredentials()
        else:
            return key

    async def get_io_credentials(self):
        io_key = await self.config.io_key()
        io_user = await self.config.io_user()
        if io_key is None:
            raise NoCredentials()
        else:
            return io_user, io_key

    async def on_message(self, message):
        if not hasattr(message, "guild"):
            return
        guild = message.guild
        if guild is None:
            return
        author = message.author
        channel = message.channel
        
        if message.author.id != self.bot.user.id:
            to_strip = "@" + guild.me.display_name + " "
            text = message.clean_content
            if not text.startswith(to_strip) and message.channel.id != await self.config.guild(guild).channel():
                return
            if not await self.config.guild(guild).toggle():
                return
            async with channel.typing():
                try:
                    response = await self.get_response(author, text)
                except NoCredentials:
                    await channel.send("The owner needs to set the credentials first.\n"
                                                         "See: `[p]cleverbot apikey`")
                except APIError as e:
                    await ctx.send("Error contacting the API. Error code: {}".format(e))
                except InvalidCredentials:
                    await channel.send("The token that has been set is not valid.\n"
                                                         "See: `[p]cleverbot apikey`")
                except OutOfRequests:
                    await channel.send("You have ran out of requests for this month. "
                                                         "The free tier has a 5000 requests a month limit.")
                except OutdatedCredentials:
                    await channel.send("You need a valid cleverbot.com api key for this to "
                                                         "work. The old cleverbot.io service will soon be no "
                                                         "longer active. See `[p]help cleverbot apikey`")
                else:
                    await channel.send(response)

    def __unload(self):
        if self.session:
            self.bot.loop.create_task(self.session.close())
