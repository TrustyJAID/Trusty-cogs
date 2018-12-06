import discord
from redbot.core import Config, checks, commands


__version__ = "1.1.0"
__author__ = "TrustyJAID"


class Spoiler(getattr(commands, "Cog", object)):
    """
        Post spoilers in chat without spoining the text for everyone
    """

    def __init__(self, bot):
        self.bot = bot
        default_guild = {"messages":[]}
        self.config = Config.get_conf(self, 545496534746)
        self.config.register_guild(**default_guild)


    @commands.command(name="spoiler", aliases=["spoilers"])
    @commands.guild_only()
    async def _spoiler(self, ctx, *, spoiler_msg):
        """
            Post spoilers in chat, react to the message to see the spoilers
        """
        if not ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.send("I don't have `manage_messages` permission.")
            return
        if not ctx.channel.permissions_for(ctx.me).add_reactions:
            await ctx.send("I don't have `add_reactions` permission.")
            return
        await ctx.message.delete()
        author = ctx.author.name
        msg_text = "**__SPOILERS__** (React to this message to view {}'s spoiler.)".format(author)
        new_msg = await ctx.send(msg_text)
        await new_msg.add_reaction("✅")
        msg_list = await self.config.guild(ctx.guild).messages()
        spoiler_obj = {"message_id":new_msg.id, "spoiler_text":spoiler_msg, "author":ctx.author.id}
        msg_list.append(spoiler_obj)
        await self.config.guild(ctx.guild).messages.set(msg_list)

    async def make_embed(self, channel, spoiler_obj):
        msg = await channel.get_message(spoiler_obj["message_id"])
        author = await self.bot.get_user_info(spoiler_obj["author"])
        name = f"{author.name}#{author.discriminator} Spoiled"
        spoiler_text = spoiler_obj["spoiler_text"] + f"\n\n [Click here for context]({msg.jump_url})"
        em = discord.Embed(description = spoiler_text, timestamp=msg.created_at)
        em.set_author(name=name, icon_url=getattr(author, "avatar_url", discord.Embed.Empty), url=msg.jump_url)
        em.set_footer(text='{} | #{}'.format(channel.guild.name, channel.name))
        return em

    async def on_raw_reaction_add(self, payload):
        if str(payload.emoji) != "✅":
            return
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except:
            return
        if payload.message_id not in [m["message_id"] for m in await self.config.guild(guild).messages()]:
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
                await user.send(embed = await self.make_embed(channel, spoiler_obj))
            except Exception as e:
                print(e)