import discord
import asyncio
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n


__version__ = "1.1.2"
__author__ = "TrustyJAID"

_ = Translator("Spoiler", __file__)
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class Spoiler(commands.Cog):
    """
        Post spoilers in chat without spoining the text for everyone
    """

    def __init__(self, bot):
        self.bot = bot
        default_guild = {"messages": []}
        self.config = Config.get_conf(self, 545496534746)
        self.config.register_guild(**default_guild)

    @commands.command(name="spoiler", aliases=["spoilers"])
    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True, add_reactions=True)
    async def _spoiler(self, ctx, *, spoiler_msg):
        """
            Post spoilers in chat, react to the message to see the spoilers
        """
        author = ctx.author.name
        msg_text = _(
            "**__SPOILERS__** (React to this message " "to view {auth}'s spoiler.)"
        ).format(auth=author)
        new_msg = await ctx.send(msg_text)
        await new_msg.add_reaction("✅")
        msg_list = await self.config.guild(ctx.guild).messages()
        spoiler_obj = {
            "message_id": new_msg.id,
            "spoiler_text": spoiler_msg,
            "author": ctx.author.id,
        }
        msg_list.append(spoiler_obj)
        await self.config.guild(ctx.guild).messages.set(msg_list)
        await asyncio.sleep(0.5)
        await ctx.message.delete()

    async def make_embed(self, channel, spoiler_obj):
        try:
            msg = await channel.get_message(spoiler_obj["message_id"])
            jump_url = msg.jump_url
        except:
            msg = None
            jump_url = ""
        author = await self.bot.get_user_info(spoiler_obj["author"])
        name = f"{author.name}#{author.discriminator} Spoiled"
        if msg:
            spoiler_text = spoiler_obj["spoiler_text"] + _(
                "\n\n [Click here for context]({jump})"
            ).format(jump=jump_url)
        else:
            spoiler_text = spoiler_obj["spoiler_text"]
        em = discord.Embed(description=spoiler_text, timestamp=msg.created_at)
        em.set_author(
            name=name, icon_url=getattr(author, "avatar_url", discord.Embed.Empty), url=jump_url
        )
        em.set_footer(text="{} | #{}".format(channel.guild.name, channel.name))
        return em

    @listener()
    async def on_raw_reaction_add(self, payload):
        if str(payload.emoji) != "✅":
            return
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except:
            return
        if payload.message_id not in [
            m["message_id"] for m in await self.config.guild(guild).messages()
        ]:
            return
        user = guild.get_member(payload.user_id)
        if user.bot:
            return
        msg_list = await self.config.guild(guild).messages()
        spoiler_obj = None
        for msg in msg_list:
            if payload.message_id == msg["message_id"]:
                spoiler_obj = msg
        if spoiler_obj is not None:
            try:
                await user.send(embed=await self.make_embed(channel, spoiler_obj))
            except Exception as e:
                print(e)
