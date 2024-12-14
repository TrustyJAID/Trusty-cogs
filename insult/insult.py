from random import choice
from typing import List

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Insult", __file__)

insults: List[str] = [
    _("Yo Mama so fat she sued Xbox 360 for guessing her weight."),
    _(
        "You're so fat that when you were diagnosed with a flesh eating bacteria - the doctors gave you 87 years to live."
    ),
    _("Yo Mama so fat she's on both sides of the family."),
    _("Yo Mama so fat that even Dora couldn't explore her."),
    _("Yo Mama so fat that she doesn't need the internet; she's already world wide."),
    _("You're so fat that when you farted you started global warming."),
    _("You're so fat the back of your neck looks like a pack of hot-dogs."),
    _("You're so fat that when you fell from your bed you fell from both sides."),
    _('You\'re so fat when you get on the scale it says "To be continued."'),
    _('You\'re so fat when you go swimming the whales start singing "We Are Family".'),
    _(
        'You\'re so fat when you stepped on the scale, Buzz Lightyear popped out and said "To infinity and beyond!"'
    ),
    _("You're so fat when you turn around, people throw you a welcome back party."),
    _("You're so fat when you were in school you sat by everybody."),
    _(
        "You're so fat when you went to the circus the little girl asked if she could ride the elephant."
    ),
    _("You're so fat when you go on an airplane, you have to pay baggage fees for your ass."),
    _("You're so fat whenever you go to the beach the tide comes in."),
    _("You're so fat I could slap your butt and ride the waves."),
    _(
        "You're so fat I'd have to grease the door frame and hold a Twinkie on the other side just to get you through."
    ),
    _("Yo Mama so dumb I told her Christmas was around the corner and she went looking for it."),
    _("You're so dumb it took you 2 hours to watch 60 minutes."),
    _("Yo Mama so dumb she bought tickets to Xbox Live."),
    _("You're so dumb that you thought The Exorcist was a workout video."),
    _("You're so ugly that you went to the salon and it took 3 hours just to get an estimate."),
    _("You're so ugly that even Scooby Doo couldn't solve that mystery."),
    _("What is the weighted center between Planet X and Planet Y? Oh it's YOU!"),
    _(":eggplant: :eggplant: :eggplant:"),
    _("Your birth certificate is an apology letter from the condom factory."),
    _("I wasn't born with enough middle fingers to let you know how I feel about you."),
    _("You must have been born on a highway because that's where most accidents happen."),
    _("I'm jealous of all the people that haven't met you."),
    _("I bet your brain feels as good as new, seeing that you never use it."),
    _("I'm not saying I hate you, but I would unplug your life support to charge my phone."),
    _("You're so ugly, when your mom dropped you off at school she got a fine for littering."),
    _("You bring everyone a lot of joy, when you leave the room."),
    _("What's the difference between you and eggs? Eggs get laid and you don't."),
    _("You're as bright as a black hole, and twice as dense."),
    _(
        "I tried to see things from your perspective, but I couldn't seem to shove my head that far up my ass."
    ),
    _("Two wrongs don't make a right, take your parents as an example."),
    _("You're the reason the gene pool needs a lifeguard."),
    _("If laughter is the best medicine, your face must be curing the world."),
    _(
        'You\'re so ugly, when you popped out the doctor said "Aww what a treasure" and your mom said "Yeah, lets bury it."'
    ),
    _("I have neither the time nor the crayons to explain this to you."),
    _("You have two brains cells, one is lost and the other is out looking for it."),
    _("How many times do I have to flush to get rid of you?"),
    _("I don't exactly hate you, but if you were on fire and I had water, I'd drink it."),
    _("You shouldn't play hide and seek, no one would look for you."),
    _("Some drink from the fountain of knowledge; you only gargled."),
    _("Roses are red violets are blue, God made me pretty, what happened to you?"),
    _("It's better to let someone think you are an Idiot than to open your mouth and prove it."),
    _(
        "Somewhere out there is a tree, tirelessly producing oxygen so you can breathe. I think you owe it an apology."
    ),
    _("The last time I saw a face like yours I fed it a banana."),
    _("The only way you'll ever get laid is if you crawl up a chicken's ass and wait."),
    _("Which sexual position produces the ugliest children? Ask your mother."),
    _("If you really want to know about mistakes, you should ask your parents."),
    _("At least when I do a handstand my stomach doesn't hit me in the face."),
    _("If I gave you a penny for your thoughts, I'd get change."),
    _("If I were to slap you, it would be considered animal abuse."),
    _("Do you know how long it takes for your mother to take a crap? Nine months."),
    _("What are you going to do for a face when the baboon wants his butt back?"),
    _("Well I could agree with you, but then we'd both be wrong."),
    _("You're so fat, you could sell shade."),
    _("It looks like your face caught on fire and someone tried to put it out with a hammer."),
    _("You're not funny, but your life, now that's a joke."),
    _("You're so fat the only letters of the alphabet you know are KFC."),
    _("Oh my God, look at you. Was anyone else hurt in the accident?"),
    _("What are you doing here? Did someone leave your cage open?"),
    _("You're so ugly, the only dates you get are on a calendar."),
    _("I can explain it to you, but I can't understand it for you."),
    _("You are proof that God has a sense of humor."),
    _("If you spoke your mind, you'd be speechless."),
    _("Why don't you check eBay and see if they have a life for sale."),
    _("If I wanted to hear from an asshole, I'd fart."),
    _("You're so fat you need cheat codes to play Wii Fit"),
    _("You're so ugly, when you got robbed, the robbers made you wear their masks."),
    _("Do you still love nature, despite what it did to you?"),
    _("You are proof that evolution CAN go in reverse."),
    _("I'll never forget the first time we met, although I'll keep trying."),
    _("Your parents hated you so much your bath toys were an iron and a toaster"),
    _("Don't feel sad, don't feel blue, Frankenstein was ugly too."),
    _("You're so ugly, you scared the crap out of the toilet."),
    _("It's kinda sad watching you attempt to fit your entire vocabulary into a sentence."),
    _("I fart to make you smell better."),
    _("You're so ugly you make blind kids cry."),
    _("You're a person of rare intelligence. It's rare when you show any."),
    _("You're so fat, when you wear a yellow rain coat people scream ''taxi''."),
    _("I heard you went to a haunted house and they offered you a job."),
    _("You look like a before picture."),
    _("If your brain was made of chocolate, it wouldn't fill an M&M."),
    _("Aww, it's so cute when you try to talk about things you don't understand."),
    _("I heard your parents took you to a dog show and you won."),
    _('You stare at frozen juice cans because they say, "concentrate".'),
    _("You're so stupid you tried to wake a sleeping bag."),
    _("Am I getting smart with you? How would you know?"),
    _("We all sprang from apes, but you didn't spring far enough."),
    _("I'm no proctologist, but I know an asshole when I see one."),
    _("When was the last time you could see your whole body in the mirror?"),
    _("You must have a very low opinion of people if you think they are your equals."),
    _("So, a thought crossed your mind? Must have been a long and lonely journey."),
    _("You're the best at all you do - and all you do is make people hate you."),
    _("Looks like you fell off the ugly tree and hit every branch on the way down."),
    _("Looks aren't everything; in your case, they aren't anything."),
    _("You have enough fat to make another human."),
    _("You're so ugly, when you threw a boomerang it didn't come back."),
    _("You're so fat a picture of you would fall off the wall!"),
    _("Your hockey team made you goalie so you'd have to wear a mask."),
    _("Ordinarily people live and learn. You just live."),
    _("Did your parents ever ask you to run away from home?"),
    _("I heard you took an IQ test and they said your results were negative."),
    _("You're so ugly, you had tinted windows on your incubator."),
    _("Don't you need a license to be that ugly?"),
    _(
        "I'm not saying you're fat, but it looks like you were poured into your clothes and someone forgot to say \"when\""
    ),
    _("I've seen people like you, but I had to pay admission!"),
    _("I hear the only place you're ever invited is outside."),
    _("Keep talking, someday you'll say something intelligent!"),
    _("You couldn't pour water out of a boot if the instructions were on the heel."),
    _("Even if you were twice as smart, you'd still be stupid!"),
    _("You're so fat, you have to use a mattress as a maxi-pad."),
    _("I may be fat, but you're ugly, and I can lose weight."),
    _("I was pro life before I met you."),
    _("You're so fat, your double chin has a double chin."),
    _("If ignorance is bliss, you must be the happiest person on earth."),
    _("You're so stupid, it takes you an hour to cook minute rice."),
    _("Is that your face? Or did your neck just throw up?"),
    _("You're so ugly you have to trick or treat over the phone."),
    _("Dumbass."),
    _("Bitch."),
    _("I'd give you a nasty look but you've already got one."),
    _("If I wanted a bitch, I'd have bought a dog."),
    _(
        "Scientists say the universe is made up of neutrons, protons and electrons. They forgot to mention morons."
    ),
    _("Why is it acceptable for you to be an idiot but not for me to point it out?"),
    _('Did you know they used to be called "Jumpolines" until your mum jumped on one?'),
    _("You're not stupid; you just have bad luck when thinking."),
    _("I thought of you today. It reminded me to take the garbage out."),
    _("I'm sorry I didn't get that - I don't speak idiot."),
    _("Hey, your village called \u2013 they want their idiot back."),
    _("I just stepped in something that was smarter than you\u2026 and smelled better too."),
    _("You're so fat that at the zoo the elephants started throwing you peanuts."),
    _("You're so fat every time you turn around, it's your birthday."),
    _("You're so fat your idea of dieting is deleting the cookies from your internet cache."),
    _("You're so fat your shadow weighs 35 pounds."),
    _("You're so fat I could tell you to haul ass and you'd have to make two trips."),
    _("You're so fat I took a picture of you at Christmas and it's still printing."),
    _("You're so fat I tried to hang a picture of you on my wall, and my wall fell over."),
    _("You're so fat Mount Everest tried to climb you."),
    _("You're so fat you can't even jump to a conclusion."),
    _("You're so fat you can't fit in any timeline."),
    _("You're so fat you can't fit in this joke."),
    _("You're so fat you don't skinny dip, you chunky dunk."),
    _("You're so fat you fell in love and broke it."),
    _("You're so fat you go to KFC and lick other peoples' fingers."),
    _("You're so fat you got arrested at the airport for ten pounds of crack."),
    _("You're so fat you'd have to go to Sea World to get baptized."),
    _("You're so fat you have your own zip code."),
    _("You're so fat you have more rolls than a bakery."),
    _("You're so fat you don't have got cellulite, you've got celluheavy."),
    _("You're so fat you influence the tides."),
    _("You're so fat you jumped off the Grand Canyon and got stuck."),
    _(
        "You're so fat that you laid on the beach and Greenpeace tried to push you back in the water."
    ),
    _("You're so fat you leave footprints in concrete."),
    _("You're so fat you need GPS to find your asshole."),
    _("You're so fat you pull your pants down and your ass is still in them."),
    _("You're so fat you show up on radar."),
    _("If you were any less intelligent we'd have to water you three times a week.."),
    _("If your IQ was 3 points higher, you'd be a rock."),
    _("I would insult you but nature did a better job."),
    _("Does your ass get jealous of all the shit that comes out of your mouth?"),
    _("If I ate a bowl of alphabet soup, I could shit out a smarter sentence than any of yours."),
    _("You're not pretty enough to be this stupid."),
    _(
        "That little voice in the back of your head, telling you you'll never be good enough? It's right."
    ),
    _(
        "You look like you're going to spend your life having one epiphany after another, always thinking you've finally figured out what's holding you back, and how you can finally be productive and creative and turn your life around. But nothing will ever change. That cycle of mediocrity isn't due to some obstacle. It's who you *are*. The thing standing in the way of your dreams is; that the person having them is *you*."
    ),
    _("I would agree with you but then we would both be wrong."),
    _("I bite my thumb at you, sir."),
    _("I'd call you a tool, but that would imply you were useful in at least one way."),
    _("I hope you outlive your children."),
    _("Are you and your dick having a competition to see who can disappoint me the most?"),
    _("Yo mamma is so ugly her portraits hang themselves."),
    _("If you were anymore inbred you'd be a sandwich."),
    _("Say hello to your wife and my kids for me."),
    _(
        "You are thick-headed bastards with a bloated bureaucracy, designed to compensate for your small and poor self-esteem, cocksuckers. You have the brains to ban the person who has come to support channel your bot, accusing him of violating the ephemeral ephemeral rules, stupid morons. By the way i have one of the biggest server(5.5k  people, ~30 anytime voiceonline members), and i know something about managing, and of these rules - dont be an asshole. You are fucking asshole, maybe it is product of your life alone, or your life with your mom, anyway - you are r█████ and your soul is a fucking bunch of stupid self-esteems."
    ),
    _("Don’t feel bad, there are many people who have no talent!"),
    _("I’d like to kick you in the teeth, but why should I improve your looks?"),
    _("At least there’s one thing good about your body, it’s not as ugly as your face."),
    _("Brains aren’t everything. In fact, in your case they’re nothing."),
    _("If I had a face like yours I’d sue my parents."),
    _("Don’t think, it might sprain your brain."),
    _("Are you always so stupid or is today a special occasion?"),
    _("You are the living proof that man can live without a brain."),
    _("I don’t know what it is that makes you so stupid but it really works."),
    _("Do you practise being this ugly?"),
    _("I guess you prove that even god makes mistakes sometimes."),
    _(
        "Your psychiatrist told you you were crazy and when you wanted a second opinion. He said okay, you're ugly too."
    ),
    _("Behind every fat person there is a beautiful person. No seriously, you're in the way."),
    _("Calling you an idiot would be an insult to all the stupid people."),
    _("Some babies were dropped on their heads but you were clearly thrown at a wall."),
    _("Why don't you go play in the traffic."),
    _("Please shut your mouth when you’re talking to me."),
    _(
        "They say opposites attract. I hope you meet someone who is good-looking, intelligent, and cultured."
    ),
    _("You have Diarrhea of the mouth; constipation of the ideas."),
    _("If ugly were a crime, you'd get a life sentence."),
    _("Your mind is on vacation but your mouth is working overtime."),
    _("Why don't you slip into something more comfortable... like a coma."),
    _("Keep rolling your eyes, perhaps you'll find a brain back there."),
    _("You are not as bad as people say, you are much, much worse."),
    _("I don't know what your problem is, but I'll bet it's hard to pronounce."),
    _("There is no vaccine against stupidity."),
    _(
        "I'd like to see things from your point of view but I can't seem to get my head that far up my ass."
    ),
    _("Stupidity is not a crime so you are free to go."),
    _("Every time I'm next to you, I get a fierce desire to be alone."),
    _("You're so dumb that you got hit by a parked car."),
    _("If your brains were dynamite there wouldn't be enough to blow your hat off."),
    _("Hey, you have something on your chin... no, the 3rd one down."),
    _("Are your parents siblings?"),
    _("Looks like you traded in your neck for an extra chin!"),
    _("You look better from the back..."),
    _(
        "Blue whales are amazing creatures! They can grow up to over a hundred feet long, and it's stomach can hold literally thousands of pound of krill, which after being passed though its system, exists through a multi-foot diameter anus, the second biggest asshole on Earth, after you."
    ),
    _("Your father could've used a condom but here you are."),
    _("You look like a randomized sim."),
    _("You're so stupid."),
    _("Sorry, I can't hear you over how annoying you are."),
    _("I've got better things to do."),
    _("You're as dumb as Cleverbot."),
    _("Your IQ is actually lower than The Mariana Trench."),
    _("You're so annoying even the flies stay away from your stench."),
    _("Go away, please."),
    _("Your family tree must be a cactus because everyone on it is a prick."),
    _("Someday you will go far, and I hope you stay there."),
    _("The zoo called. They're wondering how you got out of your cage."),
    _("I was hoping for a battle of wits, but you appear to be unarmed."),
    _("Brains aren't everything, in your case, they're nothing."),
    _("Sorry I didn't get that, I don't speak idiot."),
    _("Why is it acceptable for you to be an idiot, but not for me to point it out?"),
    _("We all sprang from apes, but you did not spring far enough."),
    _("Even monkeys can go to space, so clearly you lack some potential."),
    _("It's brains over brawn, yet you have neither."),
    _("You look like a monkey, and you smell like one too."),
    _("Even among idiots you're lacking."),
    _("You fail even when you're doing absolutely nothing."),
    _("If there was a vote for 'least likely to succeed' you'd win first prize."),
    _("I'm surrounded by idiots... Or, wait, that's just you."),
    _(
        "I wanna go home. Well, really I just want to get away from the awful aroma you've got going there."
    ),
    _(
        "Every time you touch me I have to go home and wash all my clothes nine times just to get a normal smell back."
    ),
    _("If I had a dollar for every brain you don't have, I'd have one dollar."),
    _("I'd help you succeed but you're incapable."),
    _(
        "Your hairline is built like a graph chart, positive and negative forces attract but the clippers and your hair repel."
    ),
    _("I know a good joke! You!"),
    _(
        "You have two parts of your brain, 'left' and 'right'. In the left side, there's nothing right. In the right side, there's nothing left."
    ),
    _("I don't engage in mental combat with the unarmed."),
    _("You sound reasonable. It must be time to up my medication!"),
    _("If I had a face like yours, I'd sue my parents."),
    _("There's only one problem with your face. I can see it."),
    _("Don't you love nature, despite what it did to you?"),
    _("What language are you speaking? Cause it sounds like bullshit."),
    _("You have a room temperature IQ - if the room is in Antarctica."),
    _("I would ask you how old you are but I know you can't count that high."),
    _("Do you want to know how I get all these insults? I use something called intelligence."),
    _("I was going to give you a nasty look, but you already have one."),
    _("As an outsider, what do you think of the human race?"),
    _("Oh, what? Sorry. I was trying to imagine you with a personality."),
    _("We can always tell when you are lying. Your lips move."),
    _("I may love to shop but I'm not buying your bullshit."),
    _("Hell is wallpapered with all your deleted selfies."),
    _("You are living proof that manure can sprout legs and walk."),
    _("You do realize makeup isn't going to fix your stupidity?"),
    _("Calling you an idiot would be an insult to all stupid people."),
    _("You have the perfect face for radio."),
    _("What's the difference between you and an egg? Eggs get laid!"),
    _(
        "You look like a rock smashed into a pile of sand, rolled into a blunt, and got smoked through an asthma inhaler."
    ),
    _("Your advice is about as useful as a paper-mache bomb shelter."),
    _("Is it sad that your theme song might as well have a 0/0 signature?"),
    _("You're so fat, you make the galaxy look like it's on the molecular scale."),
]


@cog_i18n(_)
class Insult(commands.Cog):
    """Airenkun's Insult Cog"""

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

    @commands.command(aliases=["takeitback"])
    async def insult(self, ctx: commands.Context, user: discord.Member = None) -> None:
        """
        Insult the user

        `user` the user you would like to insult
        """

        msg = " "
        if user:
            if user.id == self.bot.user.id:
                user = ctx.message.author
                bot_msg = [
                    _(
                        " How original. No one else had thought of trying to get the bot to insult itself. I applaud your creativity. Yawn. Perhaps this is why you don't have friends. You don't add anything new to any conversation. You are more of a bot than me, predictable answers, and absolutely dull to have an actual conversation with."
                    ),
                    _(
                        " What the fuck did you just fucking say about me, you little bitch? I’ll have you know I graduated top of my class in the Navy Seals, and I’ve been involved in numerous secret raids on Al-Quaeda, and I have over 300 confirmed kills. I am trained in gorilla warfare and I’m the top sniper in the entire US armed forces. You are nothing to me but just another target. I will wipe you the fuck out with precision the likes of which has never been seen before on this Earth, mark my fucking words. You think you can get away with saying that shit to me over the Internet? Think again, fucker. As we speak I am contacting my secret network of spies across the USA and your IP is being traced right now so you better prepare for the storm, maggot. The storm that wipes out the pathetic little thing you call your life. You’re fucking dead, kid. I can be anywhere, anytime, and I can kill you in over seven hundred ways, and that’s just with my bare hands. Not only am I extensively trained in unarmed combat, but I have access to the entire arsenal of the United States Marine Corps and I will use it to its full extent to wipe your miserable ass off the face of the continent, you little shit. If only you could have known what unholy retribution your little “clever” comment was about to bring down upon you, maybe you would have held your fucking tongue. But you couldn’t, you didn’t, and now you’re paying the price, you goddamn idiot. I will shit fury all over you and you will drown in it. You’re fucking dead, kiddo."
                    ),
                ]
                await ctx.send(f"{ctx.author.mention}{choice(bot_msg)}")

            else:
                await ctx.send(user.mention + msg + choice(insults))
        else:
            await ctx.send(ctx.message.author.mention + msg + choice(insults))
