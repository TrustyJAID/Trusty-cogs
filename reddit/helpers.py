import discord
import logging
import re

from apraw.models import Subreddit, Submission
from redbot.core import commands


BASE_URL = "https://reddit.com"

SELF_POST_SCRUB = re.compile(r"^(&#x200B;[\s\n]+)(https?://.+)$")

log = logging.getLogger("red.Trusty-cogs.reddit")


async def make_embed_from_submission(
    channel: discord.TextChannel, subreddit: Subreddit, submission: Submission,
):
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
    em = discord.Embed(
        title=submission.title[:256],
        timestamp=submission.created_utc
    )
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
    author_name = await submission.author()
    author_str = f"[u/{author_name}]({BASE_URL}/u/{author_name})"
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
                log.debug(data)
                has_image = True
                em.set_image(url=data["s"]["u"])
                break
            if data["e"] == "AnimatedImage":
                log.debug(data)
                has_image = True
                em.set_image(url=data["s"]["gif"])
                break

    if submission.over_18:
        em.add_field(name="Content Warning", value="NSFW")
    if not has_image and not has_text:
        em.description = submission.url
    em.set_footer(text=f"Score {submission.score}")
    return {"embed": em, "content": post_url}
