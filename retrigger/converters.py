from discord.ext.commands.converter import Converter, IDConverter
from discord.ext.commands.errors import BadArgument
import re
import discord
import logging

log = logging.getLogger("red.ReTrigger")


class Trigger:
    """
        Trigger class to handle trigger objects
    """

    def __init__(self, 
                 name:str, 
                 regex:str, 
                 response_type:str, 
                 author:int, 
                 count:int, 
                 image:str, 
                 text:str, 
                 whitelist:list, 
                 blacklist:list, 
                 cooldown:dict):
        self.name = name
        self.regex = regex
        self.response_type = response_type
        self.author = author
        self.count = count
        self.image = image
        self.text = text
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.cooldown = cooldown

    def _add_count(self, number:int):
        self.count += number

    def to_json(self) -> dict:
        return {"name":self.name,
                "regex":self.regex,
                "response_type":self.response_type,
                "author": self.author,
                "count": self.count,
                "image":self.image,
                "text":self.text,
                "whitelist":self.whitelist,
                "blacklist":self.blacklist,
                "cooldown":self.cooldown
                }

    @classmethod
    def from_json(cls, data:dict):
        if "cooldown" not in data:
            cooldown = {}
        else:
            cooldown = data["cooldown"]
        return cls(data["name"],
                   data["regex"],
                   data["response_type"],
                   data["author"],
                   data["count"],
                   data["image"],
                   data["text"],
                   data["whitelist"],
                   data["blacklist"],
                   cooldown)


class TriggerExists(Converter):

    async def convert(self, ctx, argument):
        bot = ctx.bot
        guild = ctx.guild
        config = bot.get_cog("ReTrigger").config
        trigger_list = await config.guild(guild).trigger_list()
        result = None
        if argument in trigger_list:
            result = Trigger.from_json(trigger_list[argument])
        else:
            result = argument
        return result


class ValidRegex(Converter):
    """
    This will check to see if the provided regex pattern is valid

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """
    async def convert(self, ctx, argument):
        bot = ctx.bot
        try:
            re.compile(argument)
            result = argument
        except Exception as e:
            log.error("Retrigger conversion error", exc_info=True)
            err_msg = "`{arg}` is not a valid regex pattern. {e}".format(arg=argument, e=e)
            raise BadArgument(err_msg)
        return result

class ChannelUserRole(IDConverter):
    """
    This will check to see if the provided argument is a channel, user, or role

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """

    async def convert(self, ctx, argument):
        bot = ctx.bot
        guild = ctx.guild
        result = None
        id_match = self._get_id_match(argument)
        channel_match = re.match(r'<#([0-9]+)>$', argument)
        member_match = re.match(r'<@!?([0-9]+)>$', argument)
        role_match = re.match(r'<@&([0-9]+)>$', argument)
        for converter in ["channel", "role", "member"]:
            if converter == "channel":
                match = id_match or channel_match
                if match:
                    channel_id = match.group(1)
                    result = guild.get_channel(int(channel_id))
                else:
                    result = discord.utils.get(guild.text_channels, name=argument)
            if converter == "member":
                match = id_match or member_match
                if match:
                    member_id = match.group(1)
                    result = guild.get_member(int(member_id))
                else:
                    result = guild.get_member_named(argument)
            if converter == "role":
                match = id_match or role_match
                if match:
                    role_id = match.group(1)
                    result = guild.get_role(int(role_id))
                else:
                    result = discord.utils.get(guild._roles.values(), name=argument)
            if result:
                break
        if not result:
            msg = _("{arg} is not a valid channel, user or role.").format(arg=argument)
            raise BadArgument(msg)
        return result
