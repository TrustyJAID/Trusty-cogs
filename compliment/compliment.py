from random import choice
from typing import List

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Compliment", __file__)

compliments: List[str] = [
    _("Your smile is contagious."),
    _("You look great today."),
    _("You're a smart cookie."),
    _("I bet you make babies smile."),
    _("You have impeccable manners."),
    _("I like your style."),
    _("You have the best laugh."),
    _("I appreciate you."),
    _("You are the most perfect you there is."),
    _("You are enough."),
    _("You're strong."),
    _("Your perspective is refreshing."),
    _("You're an awesome friend."),
    _("You light up the room."),
    _("You deserve a hug right now."),
    _("You should be proud of yourself."),
    _("You're more helpful than you realize."),
    _("You have a great sense of humor."),
    _("You've got all the right moves!"),
    _('Is that your picture next to "charming" in the dictionary?'),
    _("Your kindness is a balm to all who encounter it."),
    _("You're all that and a super-size bag of chips."),
    _("On a scale from 1 to 10, you're an 11."),
    _("You are brave."),
    _("You're even more beautiful on the inside than you are on the outside."),
    _("You have the courage of your convictions."),
    _("Your eyes are breathtaking."),
    _(
        "If cartoon bluebirds were real, a bunch of them would be sitting on your shoulders singing right now."
    ),
    _("You are making a difference."),
    _("You're like sunshine on a rainy day."),
    _("You bring out the best in other people."),
    _("Your ability to recall random factoids at just the right time is impressive."),
    _("You're a great listener."),
    _("How is it that you always look great, even in sweatpants?"),
    _("Everything would be better if more people were like you!"),
    _("I bet you sweat glitter."),
    _("You were cool way before hipsters were cool."),
    _("That color is perfect on you."),
    _("Hanging out with you is always a blast."),
    _("You always know -- and say -- exactly what I need to hear when I need to hear it."),
    _("You smell really good."),
    _(
        "You may dance like no one's watching, but everyone's watching because you're an amazing dancer!"
    ),
    _("Being around you makes everything better!"),
    _('When you say, "I meant to do that," I totally believe you.'),
    _("When you're not afraid to be yourself is when you're most incredible."),
    _("Colors seem brighter when you're around."),
    _(
        "You're more fun than a ball pit filled with candy. (And seriously, what could be more fun than that?)"
    ),
    _("That thing you don't like about yourself is what makes you so interesting."),
    _("You're wonderful."),
    _(
        "You have cute elbows. For reals! (You're halfway through the list. Don't stop now! You should be giving at least one awesome compliment every day!)"
    ),
    _("Jokes are funnier when you tell them."),
    _("You're better than a triple-scoop ice cream cone. With sprinkles."),
    _("Your hair looks stunning."),
    _("You're one of a kind!"),
    _("You're inspiring."),
    _(
        "If you were a box of crayons, you'd be the giant name-brand one with the built-in sharpener."
    ),
    _("You should be thanked more often. So thank you!!"),
    _("Our community is better because you're in it."),
    _("Someone is getting through something hard right now because you've got their back."),
    _("You have the best ideas."),
    _("You always know how to find that silver lining."),
    _("Everyone gets knocked down sometimes, but you always get back up and keep going."),
    _("You're a candle in the darkness."),
    _("You're a great example to others."),
    _("Being around you is like being on a happy little vacation."),
    _("You always know just what to say."),
    _("You're always learning new things and trying to better yourself, which is awesome."),
    _("If someone based an Internet meme on you, it would have impeccable grammar."),
    _("You could survive a Zombie apocalypse."),
    _("You're more fun than bubble wrap."),
    _("When you make a mistake, you fix it."),
    _("Who raised you? They deserve a medal for a job well done."),
    _("You're great at figuring stuff out."),
    _("Your voice is magnificent."),
    _("The people you love are lucky to have you in their lives."),
    _("You're like a breath of fresh air."),
    _("You're gorgeous -- and that's the least interesting thing about you, too."),
    _("You're so thoughtful."),
    _("Your creative potential seems limitless."),
    _("Your name suits you to a T."),
    _("You're irresistible when you blush."),
    _("Actions speak louder than words, and yours tell an incredible story."),
    _("Somehow you make time stop and fly at the same time."),
    _("When you make up your mind about something, nothing stands in your way."),
    _("You seem to really know who you are."),
    _("Any team would be lucky to have you on it."),
    _('In high school I bet you were voted "most likely to keep being awesome."'),
    _("I bet you do the crossword puzzle in ink."),
    _("Babies and small animals probably love you."),
    _(
        "If you were a scented candle they'd call it Perfectly Imperfect (and it would smell like summer)."
    ),
    _("There's ordinary, and then there's you."),
    _("You're someone's reason to smile."),
    _("You're even better than a unicorn, because you're real."),
    _("How do you keep being so funny and making everyone laugh?"),
    _("You have a good head on your shoulders."),
    _("Has anyone ever told you that you have great posture?"),
    _("The way you treasure your loved ones is incredible."),
    _("You're really something special."),
    _("You're a gift to those around you."),
]


@cog_i18n(_)
class Compliment(commands.Cog):
    """Compliment users because there's too many insults"""

    __author__ = ["Airen", "JennJenn", "TrustyJAID"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    @commands.command()
    async def compliment(self, ctx: commands.Context, user: discord.Member = None) -> None:
        """
        Compliment the user

        `user` the user you would like to compliment
        """
        msg = " "
        if user:
            if user.id == self.bot.user.id:
                user = ctx.message.author
                bot_msg: List[str] = [
                    _("Hey, I appreciate the compliment! :smile:"),
                    _("No ***YOU'RE*** awesome! :smile:"),
                ]
                await ctx.send(f"{ctx.author.mention} {choice(bot_msg)}")

            else:
                await ctx.send(user.mention + msg + choice(compliments))
        else:
            await ctx.send(ctx.message.author.mention + msg + choice(compliments))
