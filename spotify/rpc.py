from dashboard.rpc.utils import rpccheck
from red_commons.logging import getLogger
from redbot.core.bot import Red
from redbot.core.commands import commands

log = getLogger("red.trusty-cogs.spotify")


class DashboardRPC_Spotify:
    def __init__(self, cog: commands.Cog):
        self.bot: Red = cog.bot
        self.cog: commands.Cog = cog

        self.bot.register_rpc_handler(self.authenticate_user)

    def unload(self):
        self.bot.unregister_rpc_handler(self.authenticate_user)

    @rpccheck()
    async def authenticate_user(self, user: int, code: str, state: str):
        if not self.bot.get_cog("Spotify"):
            return {"status": 0, "message": "Spotify cog is not loaded."}

        user = int(user)  # Blame socket communication for this

        userobj = self.bot.get_user(user)
        if not userobj:
            return {"status": 0, "message": "Unknown user."}
        if not self.cog._credentials:
            return {"status": 0, "message": "Bot owner has not set credentials."}
        log.verbose("DashboardRPC_Spotify user: %s", user)
        try:
            auth = self.cog.temp_cache[userobj.id]
        except KeyError:
            return {
                "status": 0,
                "message": "You must authenticate using a link given by bot. If this fails try posting the full URL inside discord.",
            }

        user_token = await auth.request_token(code=code, state=state)
        await self.cog.save_token(userobj, user_token)

        del self.cog.temp_cache[userobj.id]
        self.cog.dashboard_authed.append(userobj.id)

        return {"status": 1}
