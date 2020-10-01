import asyncio
import functools
import re

import aiohttp
import chatterbot
import discord
from chatterbot import ChatBot
from chatterbot.comparisons import levenshtein_distance
from chatterbot.response_selection import get_first_response
from chatterbot.trainers import ListTrainer
from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path

LINK_REGEX = re.compile(
    r"(http(s)?:\/\/.)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"
)


class Chatter(commands.Cog):
    """
    Train the bot to speak automatically by watching guilds
    """

    def __init__(self, bot):
        self.bot = bot
        default_guild = {
            "auto_train": False,
            "blacklist": [],
            "whitelist": [],
            "auto_response": False,
        }
        default_channel = {"message": None, "author": None}
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)
        # https://github.com/bobloy/Fox-V3/blob/master/chatter/chat.py
        path = cog_data_path(self)
        data_path = path / "database.sqlite3"
        self.chatbot = ChatBot(
            "ChatterBot",
            storage_adapter="chatterbot.storage.SQLStorageAdapter",
            database=str(data_path),
            statement_comparison_function=levenshtein_distance,
            response_selection_method=get_first_response,
            logic_adapters=[
                {"import_path": "chatterbot.logic.BestMatch", "default_response": ":thinking:"}
            ],
        )
        self.trainer = ListTrainer(self.chatbot)

    @commands.group()
    async def chatterbot(self, ctx, *, message):
        """Talk with cleverbot"""
        author = ctx.message.author
        channel = ctx.message.channel
        response = self.chatbot.get_response(message)
        await ctx.send(response)

    @chatterbot.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def toggle(self, ctx):
        """Toggles reply on mention"""
        guild = ctx.message.guild
        cur_toggle = await self.config.guild(guild).toggle()
        await self.config.guild(guild).toggle.set(not cur_toggle)
        if cur_toggle:
            await ctx.send("I won't reply on mention anymore.")
        else:
            await ctx.send("I will reply on mention.")

    @chatterbot.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def channel(self, ctx, channel: discord.TextChannel = None):
        """Toggles channel for automatic replies"""
        guild = ctx.message.guild
        if channel is None:
            await self.config.guild(guild).channel.set(channel)
        else:
            await self.config.guild(guild).channel.set(channel.id)
        await ctx.send("I will reply in {}".format(channel.mention))

    async def train_message(self, message):
        """
        This will handle training the bot on messages
        """
        last_author = await self.config.channel(channel).author()
        last_message = await self.config.channel(channel).message()
        if author.id == last_author and last_message != message.content:

            await self.config.channel(channel).message.set(last_message + "\n" + message.content)
        msg = message.content
        has_link = LINK_REGEX.findall(msg)
        if has_link:
            for link in LINK_REGEX.finditer(msg):
                msg = msg.replace(link.group(0), "")
        for user in message.mentions:
            msg = msg.replace(user.mention, "")
        print(msg)
        pass

    async def respond_message(self, message):
        """
        This will handle responding with a message
        """
        pass

    async def on_message(self, message):
        guild = message.guild
        channel = message.channel
        author = message.author
        conversation = []

        return

        if author.id != last_author and author.id != self.bot.user.id and last_author is not None:

            conversation.append(message.content)
            conversation.append(last_message)
            task = functools.partial(self.chatbot.train, conversation=conversation)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                response = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
            # self.chatbot.train(conversation)
            await self.config.channel(channel).message.set(None)
            await self.config.channel(channel).author.set(None)
        if last_author is None and last_message is None:
            await self.config.channel(channel).message.set(message.content)
            await self.config.channel(channel).author.set(author.id)
        if not await self.config.guild(guild).toggle() or message.guild is None:
            return

        if author.id != self.bot.user.id:
            to_strip = "@" + author.guild.me.display_name + " "
            text = message.clean_content
            if (
                not text.startswith(to_strip)
                and message.channel.id != await self.config.guild(guild).channel()
            ):
                return
            text = text.replace(to_strip, "", 1)
            text = text.replace("@everyone ", "")
            text = text.replace("@here", "")
            async with message.channel.typing():
                task = functools.partial(self.chatbot.get_response, input_item=text)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    response = await asyncio.wait_for(task, timeout=60)
                except asyncio.TimeoutError:
                    return
                await message.channel.send(response)
