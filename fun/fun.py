import re
from typing import Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify

from .constants import emoji_dict, regionals

log = getLogger("red.trusty-cogs.fun")

VARIATION_CHAR = "\N{VARIATION SELECTOR-16}"
ENCLOSING_KEYCAP = "\N{COMBINING ENCLOSING KEYCAP}"
INVALID_CHARS = re.compile(rf"<a?:([a-zA-Z0-9\_]+?):([0-9]+?)>|[^a-z0-9\?\!#{ENCLOSING_KEYCAP}]")
VALID_CHARS = re.compile(r"[a-zA-Z0-9\?\!#]")
EMOJI_REGEX = re.compile(r"<a?:(?:[a-zA-Z0-9\_]+?):(?P<emoji_id>[0-9]+?)>")


class Fun(commands.Cog):
    """
    Module for fun/meme commands.

    RedBot V3 conversion of Appu's Fun cog.
    """

    __author__ = ["Appu", "TrustyJAID"]
    __version__ = "1.4.0"

    def __init__(self, bot: Red):
        self.bot = bot

        self.text_flip = {}
        self.generate_text_flip()

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    def generate_text_flip(self):
        char_list = r"!#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}"
        alt_char_list = r"{|}zʎxʍʌnʇsɹbdouɯlʞɾᴉɥƃɟǝpɔqɐ,‾^[\]Z⅄XMΛ∩┴SɹQԀONW˥ʞſIHפℲƎpƆq∀@¿<=>;:68ㄥ9ϛㄣƐᄅƖ0/˙-'+*(),⅋%$#¡"
        for idx, char in enumerate(char_list):
            self.text_flip[char] = alt_char_list[::-1][idx]
            self.text_flip[alt_char_list[::-1][idx]] = char

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    # used in [p]react, checks if it's possible to react with the duper string or not
    def has_dupe(self, duper: Union[str, list]) -> bool:
        collect_my_duper = list(filter(lambda x: x != "⃣", duper))
        #  ⃣ appears twice in the number unicode thing, so that must be stripped
        return len(set(collect_my_duper)) != len(collect_my_duper)

    # used in [p]react, replaces e.g. 'ng' with '🆖'
    def replace_combos(self, react_me: str) -> str:
        for combo in emoji_dict["combination"]:
            if combo[0] in react_me:
                react_me = react_me.replace(combo[0], combo[1], 1)
        return react_me

    # used in [p]react, replaces e.g. 'aaaa' with '🇦🅰🍙🔼'
    def replace_letters(self, react_me: str):
        for char in emoji_dict.keys():
            if char == "combination":
                continue
            char_count = react_me.count(char)
            if char_count > 1:  # there's a duplicate of this letter:
                if len(emoji_dict[char]) >= char_count:
                    # if we have enough different ways to say the letter to complete the emoji chain
                    i = 0
                    while i < char_count:
                        # moving goal post necessitates while loop instead of for
                        try:
                            if emoji_dict[char][i] not in react_me:
                                react_me = react_me.replace(char, emoji_dict[char][i], 1)
                        except IndexError:
                            log.error("Error replacing %s iterations %s", char, i)
                        i += 1
            else:
                if char_count == 1:
                    react_me = react_me.replace(char, emoji_dict[char][0])
        return react_me

    @commands.command()
    async def vowelreplace(self, ctx: commands.Context, replace: str, *, msg: str) -> None:
        """Replaces all vowels in a word with a letter."""
        result = ""
        for letter in msg:
            result += replace if letter.lower() in "aeiou" else letter
        await ctx.send(result)

    @commands.command()
    async def textflip(self, ctx: commands.Context, *, msg: str) -> None:
        """Flip given text."""
        result = ""
        for char in msg:
            result += self.text_flip[char] if char in self.text_flip else char
        await ctx.send(result[::-1])  # slice reverses the string

    @commands.command()
    async def regional(self, ctx: commands.Context, *, msg: str) -> None:
        """Replace letters with regional indicator emojis."""
        regional_list = [regionals[x.lower()] if x.lower() in regionals else x for x in list(msg)]
        await ctx.send("\u200b".join(regional_list))

    @commands.command()
    async def space(self, ctx: commands.Context, *, msg: str) -> None:
        """Add n spaces between each letter. Ex: `[p]space 2 thicc`."""
        if msg.split(" ", 1)[0].isdigit():
            spaces = int(msg.split(" ", 1)[0]) * " "
            msg = msg.split(" ", 1)[1].strip()
        else:
            spaces = " "
        spaced_message = pagify(spaces.join(list(msg)))
        try:
            await ctx.send_interactive(spaced_message)
        except discord.HTTPException:
            await ctx.send("That message is too long.", delete_after=10)

    @commands.command()
    async def oof(self, ctx: commands.Context, message: Optional[discord.Message]) -> None:
        """
        React 🅾🇴🇫 to a message.

        `[message]` Can be a message ID from the current channel, a jump URL,
        or a channel_id-message_id from shift + copying ID on the message.
        """
        OOF = (
            "\N{NEGATIVE SQUARED LATIN CAPITAL LETTER O}\N{VARIATION SELECTOR-16}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER O}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER F}",
        )
        deleted = False
        if ctx.bot_permissions.manage_messages:
            try:
                await ctx.message.delete()
                deleted = True
            except Exception:
                pass
        if message is None:
            if ctx.message.reference:
                message = ctx.message.reference.cached_message
                if message is None and ctx.message.reference.message_id:
                    message = ctx.channel.get_partial_message(ctx.message.reference.message_id)
            elif ctx.bot_permissions.read_message_history:
                limit = 1 if deleted else 2
                async for messages in ctx.channel.history(limit=limit):
                    message = messages
        if message is None:
            await ctx.send("No message was available to react to.")
            return

        if not message.channel.permissions_for(ctx.me).add_reactions:
            await ctx.send("I require add_reactions permission in that channel.")
            return
        my_emojis = [r.emoji for r in message.reactions if r.me]
        for emoji in OOF:
            if emoji in my_emojis:
                log.trace("Already reacted to %s", message)
                continue
            try:
                await message.add_reaction(emoji)
            except Exception:
                break

    # given String react_me, return a list of emojis that can construct the string with no duplicates (for the purpose of reacting)
    # TODO make it consider reactions already applied to the message
    @commands.command()
    async def react(
        self,
        ctx: commands.Context,
        message: Optional[discord.Message],
        *,
        msg: str,
    ) -> None:
        """
        Add letter(s) as reaction to previous message.

        `[message]` Can be a message ID from the current channel, a jump URL,
        or a channel_id-message_id from shift + copying ID on the message.
        """
        deleted = False
        if ctx.bot_permissions.manage_messages:
            try:
                await ctx.message.delete()
                deleted = True
            except Exception:
                pass
        if message is None:
            if ctx.message.reference:
                message = ctx.message.reference.cached_message
                if message is None and ctx.message.reference.message_id:
                    message = ctx.channel.get_partial_message(ctx.message.reference.message_id)
            elif ctx.bot_permissions.read_message_history:
                limit = 1 if deleted else 2
                async for messages in ctx.channel.history(limit=limit):
                    message = messages
        if message is None:
            await ctx.send("No message was available to react to.")
            return

        reactions = []
        non_unicode_emoji_list = []
        react_me = ""
        # this is the string that will hold all our unicode converted characters from msg

        # replace all custom server emoji <:emoji:123456789> with "<" and add emoji ids to non_unicode_emoji_list
        emotes = EMOJI_REGEX.findall(msg)
        extras = VALID_CHARS.sub("", msg)
        react_me = INVALID_CHARS.sub("", msg)
        log.debug("Extras %s react_me %s", extras, react_me)

        for emoji_id in emotes:
            emoji = discord.utils.get(self.bot.emojis, id=int(emoji_id))
            if emoji is not None:
                reactions.append(emoji)
                non_unicode_emoji_list.append(emoji)

        if self.has_dupe(non_unicode_emoji_list):
            await ctx.send(
                "You requested that I react with at least two of the exact same specific emoji. "
                "I'll try to find alternatives for alphanumeric text, but if you specify a specific emoji must be used, I can't help."
            )
            return

        react_me_original = react_me
        # we'll go back to this version of react_me if prefer_combine
        # is false but we can't make the reaction happen unless we combine anyway.

        if self.has_dupe(react_me):
            log.debug("has dupe?")
            # there's a duplicate letter somewhere, so let's go ahead try to fix it.
            react_me = self.replace_combos(react_me)
            react_me = self.replace_letters(react_me)
            # print(react_me)
            if self.has_dupe(react_me):  # check if we were able to solve the dupe
                react_me = react_me_original
                react_me = self.replace_combos(react_me)
                react_me = self.replace_letters(react_me)
                if self.has_dupe(react_me):
                    # this failed too, so there's really nothing we can do anymore.
                    await ctx.send("Failed to fix all duplicates. Cannot react with this string.")
                    return

            for char in react_me:
                if not char.isdigit():
                    # these unicode characters are weird and actually more than one character.
                    if char not in [VARIATION_CHAR, ENCLOSING_KEYCAP]:
                        reactions.append(char)
                else:
                    reactions.append(emoji_dict[char][0])
            for char in extras:
                log.debug(char)
                if char != VARIATION_CHAR:
                    reactions.append(char)
                else:
                    reactions.append(f"{reactions.pop()}{VARIATION_CHAR}")
        else:  # probably doesn't matter, but by treating the case without dupes seperately, we can save some time
            for char in react_me:
                log.debug("searching char %s", ord(char))
                if char in emoji_dict.keys():
                    if char == "combination":
                        continue
                    reactions.append(emoji_dict[char][0])
                elif char == VARIATION_CHAR:
                    log.debug("Found Variation Character")
                    reactions.append(f"{reactions.pop()}{VARIATION_CHAR}")
                else:
                    reactions.append(char)
            for char in extras:
                log.debug(char)
                if char not in [VARIATION_CHAR, ENCLOSING_KEYCAP]:
                    reactions.append(char)
                else:
                    reactions.append(f"{reactions.pop()}{VARIATION_CHAR}")

        log.debug(reactions)
        my_emojis = [getattr(r, "emoji") for r in getattr(message, "reactions", []) if r.me]
        if message.channel.permissions_for(ctx.me).add_reactions and message is not None:
            for reaction in reactions:
                if reaction in my_emojis:
                    log.trace("Already reacted to %s", message)
                    continue
                try:
                    await message.add_reaction(reaction)
                except Exception:
                    log.error("Error adding reaction %s", reaction)
                    break
