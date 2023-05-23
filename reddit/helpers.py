import re
from typing import Dict, Optional, Union

import apraw
import discord
from apraw.models import Submission, Subreddit
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator

BASE_URL = "https://reddit.com"

SELF_POST_SCRUB = re.compile(r"^(&#x200B;[\s\n]+)(https?://.+)$")

REDDIT_RE = re.compile(r"\/?r\/([a-zA-Z0-9_]+)")

log = getLogger("red.Trusty-cogs.reddit")

_ = Translator("Reddit", __file__)


class SubredditConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> apraw.models.Subreddit:
        if not ctx.cog.login:
            raise BadArgument(
                _(
                    "The bot owner has not added credentials to utilize this cog.\n"
                    "Have them see `{prefix}redditset creds` for more information"
                ).format(prefix=ctx.clean_prefix)
            )
        await ctx.typing()
        subr = REDDIT_RE.search(argument)
        if subr:
            subreddit = subr.group(1)
        else:
            subreddit = re.sub(r"<|>|\/|\\|\.|,|;|\'|\"", "", argument)
        try:
            sub = await ctx.cog.login.subreddit(subreddit)
        except Exception:
            raise BadArgument(
                _("`{argument}` does not look like a valid subreddit.").format(argument=argument)
            )
        if len(sub._data.keys()) < 7:
            raise BadArgument(
                _("`{argument}` does not look like a valid subreddit.").format(argument=argument)
            )
        if getattr(sub, "over18", False) and not ctx.channel.is_nsfw():
            raise BadArgument(_("I cannot post contents from this sub in non-NSFW channels."))
        return sub


async def make_embed_from_submission(
    channel: discord.TextChannel,
    subreddit: Subreddit,
    submission: Submission,
) -> Optional[Dict[str, Union[discord.Embed, str]]]:
    """
    Generates a discord embed from a provided submission object.
    """
    em = None
    if submission.over_18 and not channel.is_nsfw():
        return None
    if submission.spoiler:
        post_url = f"||{BASE_URL}{submission.permalink}||"
    else:
        post_url = f"{BASE_URL}{submission.permalink}"
    em = discord.Embed(title=submission.title[:256], timestamp=submission.created_utc)
    has_text, has_image = False, False
    kind = " post"
    if submission.is_self:
        kind = " self post"
    if submission.is_video:
        kind = " video post"
    if submission.is_meta:
        kind = " meta post"
    if submission.is_original_content:
        kind = "n OC post"
    em.set_author(
        name=f"A{kind} has been submitted to {submission.subreddit_name_prefixed}",
        url=BASE_URL + submission.permalink,
        icon_url=subreddit.community_icon,
    )
    if subreddit.primary_color:
        colour = int(subreddit.primary_color.replace("#", ""), 16)
        em.colour = discord.Colour(colour)
    if submission.selftext:
        has_text = True
        text = SELF_POST_SCRUB.sub("", submission.selftext)
        em.description = text[:512]
    try:
        author_name = await submission.author()
        author_str = f"[u/{author_name}]({BASE_URL}/u/{author_name})"
    except Exception:
        author_name = _("Unknown or Deleted User")
        author_str = _("Unknown or Deleted User")
    em.add_field(name="Post Author", value=author_str)
    # em.add_field(name="Content Warning", value=)
    # link_str = f"[Click to see full post]({BASE_URL}{submission.permalink})"
    if submission.thumbnail:
        url = submission.url
        if url.endswith("gifv"):
            url = url.replace("gifv", "gif")
        if submission.thumbnail != "self":
            has_image = True
            em.set_image(url=url)
    if getattr(submission, "media_metadata", None):
        log.debug("There's media metadata!")
        for _id, data in submission.media_metadata.items():
            if data["e"] == "RedditVideo":
                continue
            if data["e"] == "Image":
                log.verbose("make_embed_from_submission Image data: %s", data)
                has_image = True
                em.set_image(url=data["s"]["u"])
                break
            if data["e"] == "AnimatedImage":
                log.verbose("make_embed_from_submission AnimatedImage data: %s", data)
                has_image = True
                em.set_image(url=data["s"]["gif"])
                break

    if submission.over_18:
        em.add_field(name="Content Warning", value="NSFW")
    if not has_image and not has_text:
        em.description = submission.url
    em.set_footer(text=f"Score {submission.score}")
    return {"embed": em, "content": post_url}
