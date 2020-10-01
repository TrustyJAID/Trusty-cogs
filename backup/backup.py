import datetime
import json
import os
from random import randint
from typing import Union

import discord
from redbot.core import checks, commands
from redbot.core.data_manager import cog_data_path


class GuildNotFoundError(Exception):
    pass


class Backup(commands.Cog):
    """
    Create a set of json backups of a server
    """

    def __init__(self, bot):
        self.bot = bot

    def save_json(self, filename, data):
        """Atomically saves json file"""
        rnd = randint(1000, 9999)
        path, ext = os.path.splitext(filename)
        tmp_file = "{}-{}.tmp".format(path, rnd)
        self._save_json(tmp_file, data)
        try:
            self._read_json(tmp_file)
        except json.decoder.JSONDecodeError:
            self.logger.exception(
                "Attempted to write file {} but JSON "
                "integrity check on tmp file has failed. "
                "The original file is unaltered."
                "".format(filename)
            )
            return False
        os.replace(tmp_file, filename)
        return True

    def _read_json(self, filename):
        with open(filename, encoding="utf-8", mode="r") as f:
            data = json.load(f)
        return data

    def _save_json(self, filename, data):
        with open(filename, encoding="utf-8", mode="w") as f:
            json.dump(data, f, indent=4, sort_keys=True, separators=(",", " : "))
        return data

    async def check_folder(self, folder_name):
        if not os.path.exists("{}/{}".format(str(cog_data_path(self)), folder_name)):
            try:
                os.makedirs("{}/{}".format(str(cog_data_path(self)), folder_name))
                os.makedirs("{}/{}/files".format(str(cog_data_path(self)), folder_name))
                return True
            except:
                return False
        else:
            return True

    async def get_guild_obj(self, guild_name):
        if type(guild_name) == int:
            page_guild = [g for g in self.bot.guilds if int(guild_name) == g.id]
        if type(guild_name) == str:
            page_guild = [g for g in self.bot.guilds if guild_name.lower() in g.name.lower()]
        try:
            if guild_name is not None:
                guilds = [g for g in self.bot.guilds]
                guild = guilds[guilds.index(page_guild[0])]
        except IndexError:
            raise GuildNotFoundError
        return guild

    @commands.command(aliases=["channelbackup"])
    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def channellogs(self, ctx, *, channel: discord.TextChannel = None):
        """
        Creat a backup of all channel data as json files This might take a long time

        `channel` is partial name or ID of the server you want to backup
        defaults to the server the command was run in
        """
        if channel is None:
            channel = ctx.channel
        guild = ctx.guild
        today = datetime.date.today().strftime("%Y-%m-%d")
        is_folder = await self.check_folder(guild.name)
        total_msgs = 0
        files_saved = 0
        message_list = []
        if not is_folder:
            print("{} folder doesn't exist!".format(guild.name))
            return
        try:
            async for message in channel.history(limit=None):
                data = {
                    "timestamp": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "tts": message.tts,
                    "author": {
                        "name": message.author.name,
                        "display_name": message.author.display_name,
                        "discriminator": message.author.discriminator,
                        "id": message.author.id,
                        "bot": message.author.bot,
                    },
                    "content": message.content,
                    "channel": {"name": message.channel.name, "id": message.channel.id},
                    "mention_everyone": message.mention_everyone,
                    "mentions": [
                        {
                            "name": user.name,
                            "display_name": user.display_name,
                            "discriminator": user.discriminator,
                            "id": user.id,
                            "bot": user.bot,
                        }
                        for user in message.mentions
                    ],
                    "channel_mentions": [
                        {"name": channel.name, "id": channel.id}
                        for channel in message.channel_mentions
                    ],
                    "role_mentions": [
                        {"name": role.name, "id": role.id} for role in message.role_mentions
                    ],
                    "id": message.id,
                    "pinned": message.pinned,
                }
                message_list.append(data)
                if message.attachments:
                    for a in message.attachments:
                        files_saved += 1
                        fp = "{}/{}/files/{}-{}".format(
                            str(cog_data_path(self)), guild.name, message.id, a.filename
                        )
                        await a.save(fp)
            total_msgs += len(message_list)
            self.save_json(
                "{}/{}/{}-{}.json".format(
                    str(cog_data_path(self)), guild.name, channel.name, today
                ),
                message_list,
            )
        except discord.errors.Forbidden:
            return
        await channel.send("{} messages saved from {}".format(total_msgs, channel.name))

    @commands.command(aliases=["serverbackup"])
    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def serverlogs(self, ctx, *, guild_name: Union[int, str] = None):
        """
        Creat a backup of all server data as json files This might take a long time

        `guild_name` is partial name or ID of the server you want to backup
        defaults to the server the command was run in
        """
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send("{} guild could not be found.".format(guild_name))
                return
        today = datetime.date.today().strftime("%Y-%m-%d")
        channel = ctx.message.channel
        is_folder = await self.check_folder(guild.name)
        total_msgs = 0
        files_saved = 0
        if not is_folder:
            print("{} folder doesn't exist!".format(guild.name))
            return
        for chn in guild.channels:
            # await channel.send("backing up {}".format(chn.name))
            message_list = []
            try:
                async for message in chn.history(limit=None):
                    data = {
                        "timestamp": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "tts": message.tts,
                        "author": {
                            "name": message.author.name,
                            "display_name": message.author.display_name,
                            "discriminator": message.author.discriminator,
                            "id": message.author.id,
                            "bot": message.author.bot,
                        },
                        "content": message.content,
                        "channel": {"name": message.channel.name, "id": message.channel.id},
                        "mention_everyone": message.mention_everyone,
                        "mentions": [
                            {
                                "name": user.name,
                                "display_name": user.display_name,
                                "discriminator": user.discriminator,
                                "id": user.id,
                                "bot": user.bot,
                            }
                            for user in message.mentions
                        ],
                        "channel_mentions": [
                            {"name": channel.name, "id": channel.id}
                            for channel in message.channel_mentions
                        ],
                        "role_mentions": [
                            {"name": role.name, "id": role.id} for role in message.role_mentions
                        ],
                        "id": message.id,
                        "pinned": message.pinned,
                    }
                    message_list.append(data)
                    if message.attachments:
                        for a in message.attachments:
                            files_saved += 1
                            fp = "{}/{}/files/{}-{}".format(
                                str(cog_data_path(self)), guild.name, message.id, a.filename
                            )
                            await a.save(fp)
                total_msgs += len(message_list)
                if len(message_list) == 0:
                    continue
                self.save_json(
                    "{}/{}/{}-{}.json".format(
                        str(cog_data_path(self)), guild.name, chn.name, today
                    ),
                    message_list,
                )
                await channel.send("{} messages saved from {}".format(len(message_list), chn.name))
            except discord.errors.Forbidden:
                await channel.send("0 messages saved from {}".format(chn.name))
                pass
            except AttributeError:
                await channel.send("0 messages saved from {}".format(chn.name))
                pass
        await channel.send("{} messages saved from {}".format(total_msgs, guild.name))
