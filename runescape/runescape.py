import discord
from redbot.core import commands
from redbot.core import Config
import json
import aiohttp
from tabulate import tabulate
from .profile import Profile
from redbot.core.utils.chat_formatting import pagify, box


class Runescape(commands.Cog):
    """
        Display Runescape account info
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1845134845412)
        default = {"rsn": ""}
        self.config.register_user(**default)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    @commands.group(name="runescape", aliases=["rs"])
    async def runescape(self, ctx):
        """Search for a user account or profile"""
        pass

    @commands.group(name="osrs")
    async def osrs(self, ctx):
        """Search for OSRS highscores"""
        pass

    @osrs.command(name="stats")
    async def osrs_stats(self, ctx, runescape_name=None):
        user = self.bot.get_user(ctx.message.author.id)
        if runescape_name is None:
            runescape_name = await self.config.user(user).rsn()
            if runescape_name is None:
                await ctx.send("You need to set your Runescape name first!")
                return

        details = await self.get_osrs_hiscores(runescape_name)
        if not details:
            return await ctx.send("I can't find username `{}`".format(runescape_name))
        msg = await self.osrs_stats_page(details, runescape_name)
        for page in pagify(msg):
            await ctx.send(box(page, lang="css"))

    @runescape.command()
    async def set(self, ctx, *, RunescapeName: str):
        """Set your runescape name for easer commands."""
        user = self.bot.get_user(ctx.message.author.id)
        await self.config.user(user).rsn.set(RunescapeName)
        await ctx.send("Your Runescape name has been set. To change re-do this command.")

    async def osrs_highscores(self, runescape_name):
        return "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={}".format(
            runescape_name
        )

    async def get_osrs_hiscores(self, runescape_name):
        async with self.session.get(await self.osrs_highscores(runescape_name)) as resp:
            if resp.status != 200:
                return None
            return await resp.read()

    async def make_url_profile(self, runescape_name, activities):
        return "https://apps.runescape.com/runemetrics/profile/profile?user={}&activities={}".format(
            runescape_name, activities
        )

    async def make_url_player_details(self, runescape_name):
        return "http://services.runescape.com/m=website-data/playerDetails.ws?names=%5B%22{}%22%5D&callback=jQuery000000000000000_0000000000&_=0".format(
            runescape_name
        )

    async def get_player_details(self, runescape_name):
        async with self.session.get(await self.make_url_player_details(runescape_name)) as resp:
            data = await resp.text()
        json_data = json.loads(
            data.replace("jQuery000000000000000_0000000000([", "").replace("]);", "")
        )
        return json_data
        # return await resp.json()

    async def get_data_profile(self, runescape_name, activities):
        async with self.session.get(
            await self.make_url_profile(runescape_name, activities)
        ) as resp:
            return await resp.json()

    async def get_profile_obj(self, profile_data):
        return await Profile.from_json(profile_data)

    async def get_profile(self, runescape_name, activities=5):
        data = await self.get_data_profile(runescape_name, activities)
        if "error" in data:
            return "NO PROFILE"
        return await self.get_profile_obj(data)

    @runescape.command()
    async def profile(self, ctx, runescape_name: str = None, activity: int = 10):
        """Display a players profile in Runescape"""
        user = self.bot.get_user(ctx.message.author.id)
        if runescape_name is None:
            runescape_name = await self.config.user(user).rsn()
            if runescape_name is None:
                await ctx.send("You need to set your Runescape name first!")
                return

        details = await self.get_player_details(runescape_name)
        data = await self.get_profile(runescape_name, activity)
        if data == "NO PROFILE":
            await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
            return
        # print(data.slayer)
        embed = await self.profile_embed(data, details)
        await ctx.send(embed=embed)

    @runescape.command()
    async def stats(self, ctx, *, runescape_name: str = None):
        """Display a players stats in Runescape"""
        user = self.bot.get_user(ctx.message.author.id)
        if runescape_name is None:
            runescape_name = await self.config.user(user).rsn()
            if runescape_name is None:
                await ctx.send("You need to set your Runescape name first!")
                return

        details = await self.get_player_details(runescape_name)
        data = await self.get_profile(runescape_name)
        if data == "NO PROFILE":
            await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
            return
        # print(data.slayer)
        skills = await self.stats_message(data)
        await ctx.send(skills)

    async def raw_stats_message(self, p):
        skills_list = [["Overall", p.totalskill, "{:,}".format(p.totalxp), p.rank]]
        skills = [
            "Attack",
            "Defence",
            "Strength",
            "Constitution",
            "Ranged",
            "Prayer",
            "Magic",
            "Cooking",
            "Woodcutting",
            "Fletching",
            "Fishing",
            "Firemaking",
            "Crafting",
            "Smithing",
            "Mining",
            "Herblore",
            "Agility",
            "Thieving",
            "Slayer",
            "Farming",
            "Runecrafting",
            "Hunter",
            "Construction",
            "Summoning",
            "Dungeoneering",
            "Divination",
            "Invention",
        ]
        stats = p.to_json()
        for skill in skills:
            level = stats[skill.lower()]["level"]
            xp = stats[skill.lower()]["xp"]
            rank = stats[skill.lower()]["rank"] if "rank" in stats[skill.lower()] else "Unranked"
            skills_list.append([skill, level, xp, rank])
        return tabulate(
            skills_list, headers=["Skill", "Level", "Experience", "Rank"], tablefmt="orgtbl"
        )

    async def stats_message(self, p):
        table = await self.raw_stats_message(p)
        top_row_len = len(table.split("\n")[0])
        top_row = top_row_len * "-"
        spaces = int(((top_row_len - (14 + len(p.name))) / 2) - 1) * " "
        skills = "```css\n{top_row}\n|{spaces}RS3 STATS FOR {user}{spaces}|\n{top_row}\n{skills}\n{top_row}```".format(
            spaces=spaces, top_row=top_row, user=p.name, skills=table
        )
        return skills

    async def osrs_stats_page(self, data, runescape_name):
        table = await Profile.from_text(data)
        top_row_len = len(table.split("\n")[0])
        top_row = top_row_len * "-"
        spaces = int(((top_row_len - (14 + len(runescape_name))) / 2) - 1) * " "
        skills = "{top_row}\n|{spaces}OSRS STATS FOR {user}{spaces}|\n{top_row}\n{skills}\n{top_row}".format(
            spaces=spaces, top_row=top_row, user=runescape_name, skills=table
        )
        return skills

    async def profile_embed(self, profile, details):
        em = discord.Embed()
        if details["isSuffix"]:
            em.set_author(name="{} {}".format(profile.name, details["title"]))
        else:
            em.set_author(name="{} {}".format(details["title"], profile.name))
        activities = ""
        for activity in profile.activities:
            activities += "[{}] {}\n".format(activity["date"], activity["text"])

        # em.colour = int(teams[_teams.name]["home"].replace("#", ""), 16)
        em.set_thumbnail(
            url="http://secure.runescape.com/m=avatar-rs/{}/chat.png".format(
                profile.name.replace(" ", "%20")
            )
        )
        em.add_field(name="Combat Level", value=profile.combatlevel)
        em.add_field(name="Total Level", value=profile.totalskill)
        em.add_field(name="Total XP", value=profile.totalxp)
        if activities != "":
            em.add_field(name="Activities", value=activities)
        # if profile.logged_in:
        # em.set_footer(text="Online", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Green_pog.svg/64px-Green_pog.svg.png")
        # else:
        # em.set_footer(text="Offline", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/Red_pog.svg/64px-Red_pog.svg.png")
        return em

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    __unload = cog_unload
