import discord

from apraw import Subreddit, Submission
from redbot.core import commands


BASE_URL = "https://reddit.com"


async def make_embed_from_submission(
    self, ctx: commands.Context, subreddit: Subreddit, submission: Submission,
):
    """
            Generates a discord embed from a provided submission object.
        """
    em = None
    self.over_18 = submission.over_18
    if submission.over_18 and not ctx.channel.is_nsfw():
        return None
    if submission.spoiler:
        post_url = f"||{BASE_URL}{submission.permalink}||"
    else:
        post_url = f"{BASE_URL}{submission.permalink}"
    em = discord.Embed(title=submission.title[:256])
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
        icon_url=self._subreddit.community_icon,
    )
    if self._subreddit.primary_color:
        colour = int(self._subreddit.primary_color.replace("#", ""), 16)
        em.colour = discord.Colour(colour)
    if submission.selftext:
        em.description = submission.selftext[:512]
    author_name = await submission.author()
    author_str = f"[u/{author_name}]({BASE_URL}/u/{author_name})"
    em.add_field(name="Post Author", value=author_str)
    # em.add_field(name="Content Warning", value=)
    # link_str = f"[Click to see full post]({BASE_URL}{submission.permalink})"
    if submission.thumbnail:
        em.set_image(url=submission.url)
    if submission.over_18:
        em.add_field(name="Content Warning", value="NSFW")
    return {"embed": em, "content": post_url}
