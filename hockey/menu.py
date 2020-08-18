import asyncio
import discord
import logging

from redbot.core.commands import Context
from .embeds import roster_embed, make_leaderboard_embed
from .standings import Standings
from .game import Game
from redbot.core.i18n import Translator
from redbot.core.utils.menus import start_adding_reactions, DEFAULT_CONTROLS


_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.hockey")

numbs = {
    "next": "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
    "back": "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
    "exit": "\N{CROSS MARK}",
}


async def hockey_menu(
    ctx: Context,
    display_type: str,
    post_list: list,
    message: discord.Message = None,
    page=0,
    timeout: int = 30,
):
    """menu control logic for this taken from
       https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
    if ctx.channel.permissions_for(ctx.me).embed_links:
        if display_type == "standings":
            em = await Standings.build_standing_embed(post_list, page)
        if display_type == "division":
            em = await Standings.build_standing_embed(post_list, page)
        if display_type == "conference":
            em = await Standings.build_standing_embed(post_list, page)
        if display_type == "teams":
            em = await Standings.build_standing_embed(post_list, page)
        if display_type == "all":
            em = await Standings.all_standing_embed(post_list, page)
        if display_type == "roster":
            em = await roster_embed(post_list, page)
        if display_type == "game":
            em = await Game.get_game_embed(post_list, page)
        if display_type == "season":
            leaderboard = {"type": "Seasonal", "lists": post_list}
            em = await make_leaderboard_embed(ctx.guild, leaderboard, page)
        if display_type == "weekly":
            leaderboard = {"type": "Weekly", "lists": post_list}
            em = await make_leaderboard_embed(ctx.guild, leaderboard, page)
        if display_type == "worst":
            leaderboard = {"type": "Worst", "lists": post_list}
            em = await make_leaderboard_embed(ctx.guild, leaderboard, page)
    else:
        await ctx.send(_("I don't have embed links permission!"))
        return

    if not message:
        message = await ctx.send(embed=em)
        start_adding_reactions(message, DEFAULT_CONTROLS.keys())
    else:
        # message edits don't return the message object anymore lol
        await message.edit(embed=em)
    check = (
        lambda react, user: user == ctx.message.author
        and str(react.emoji) in numbs.values()
        and react.message.id == message.id
    )
    try:
        react, user = await ctx.bot.wait_for("reaction_add", check=check, timeout=timeout)
    except asyncio.TimeoutError:
        for emoji in numbs.values():
            await message.remove_reaction(emoji, ctx.me)
        return None
    else:
        reacts = {v: k for k, v in numbs.items()}
        react = reacts[react.emoji]
        if react == "next":
            next_page = 0
            log.debug("Going to next page")
            if page == len(post_list) - 1:
                next_page = 0  # Loop around to the first item
            else:
                next_page = page + 1
            if ctx.channel.permissions_for(ctx.me).manage_messages:
                await message.remove_reaction(
                    "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}", ctx.message.author
                )
            return await hockey_menu(
                ctx, display_type, post_list, message=message, page=next_page, timeout=timeout
            )

        elif react == "back":
            next_page = 0
            if page == 0:
                next_page = len(post_list) - 1  # Loop around to the last item
            else:
                next_page = page - 1
            if ctx.channel.permissions_for(ctx.me).manage_messages:
                await message.remove_reaction(
                    "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}", ctx.message.author
                )
            return await hockey_menu(
                ctx, display_type, post_list, message=message, page=next_page, timeout=timeout
            )
        else:
            return await message.delete()
