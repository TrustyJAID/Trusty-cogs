import json
from pathlib import Path

from discord import Object

from .spotify import Spotify

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = Spotify(bot)
    await bot.add_cog(cog)
    global_slash = await cog.config.enable_slash()
    global_context = await cog.config.enable_context()
    all_guilds = await cog.config.all_guilds()

    for g_id, data in all_guilds.items():
        if data["enable_slash"] and not global_slash:
            bot.tree.add_command(cog, guild=Object(id=g_id))
        if data["enable_context"] and not global_context:
            bot.tree.add_command(cog.play_from_message_ctx, guild=Object(id=g_id))
            bot.tree.add_command(cog.queue_from_message_ctx, guild=Object(id=g_id))
    if not global_slash:
        bot.tree.remove_command("spotify")
    if global_context:
        bot.tree.add_command(cog.play_from_message_ctx)
        bot.tree.add_command(cog.queue_from_message_ctx)
