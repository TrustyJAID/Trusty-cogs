import asyncio
from copy import copy
from io import BytesIO
from typing import List, Literal, Optional, Tuple, Union

import aiohttp
import discord
import tekore
import yaml
from discord import app_commands
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.utils.views import SetApiView

from .abc import SpotifyMixin
from .components import SpotifySelectDevice
from .helpers import (
    SPOTIFY_RE,
    InvalidEmoji,
    NotPlaying,
    RecommendationsFlags,
    ScopeConverter,
    SearchTypes,
    SpotifyURIConverter,
    song_embed,
    spotify_emoji_handler,
    time_convert,
)
from .menus import (
    SpotifyAlbumPages,
    SpotifyArtistPages,
    SpotifyBaseMenu,
    SpotifyDeviceView,
    SpotifyEpisodePages,
    SpotifyNewPages,
    SpotifyPages,
    SpotifyPlaylistPages,
    SpotifyPlaylistsPages,
    SpotifyRecentSongPages,
    SpotifySearchMenu,
    SpotifyShowPages,
    SpotifyTopArtistsPages,
    SpotifyTopTracksPages,
    SpotifyTrackPages,
    SpotifyUserMenu,
)

# from redbot.core.utils.views import SetApiView


log = getLogger("red.trusty-cogs.spotify")
_ = Translator("Spotify", __file__)

ActionConverter = commands.get_dict_converter(
    *spotify_emoji_handler.emojis.keys(), delims=[" ", ",", ";"]
)

KEY_CHOICES = [
    app_commands.Choice(name="C (also B♯, Ddouble flat)", value=0),
    app_commands.Choice(name="C♯, D♭ (also Bdouble sharp)", value=1),
    app_commands.Choice(name="D (also Cdouble sharp, Edouble flat)", value=2),
    app_commands.Choice(name="D♯, E♭ (also Fdouble flat)", value=3),
    app_commands.Choice(name="E (also Ddouble sharp, F♭)", value=4),
    app_commands.Choice(name="F (also E♯, Gdouble flat)", value=5),
    app_commands.Choice(name="F♯, G♭ (also Edouble sharp)", value=6),
    app_commands.Choice(name="G (also Fdouble sharp, Adouble flat)", value=7),
    app_commands.Choice(name="G♯, A♭", value=8),
    app_commands.Choice(name="A (also Gdouble sharp, Bdouble flat)", value=9),
    app_commands.Choice(name="A♯, B♭ (also Cdouble flat)", value=10),
    app_commands.Choice(name="B (also Adouble sharp, C♭)", value=11),
]


class SpotifyCommands(SpotifyMixin):
    @commands.hybrid_group(name="spotify", aliases=["sp"])
    async def spotify_com(self, ctx: commands.Context):
        """
        Spotify commands
        """

    @spotify_com.group(name="set")
    async def spotify_set(self, ctx: commands.Context):
        """
        Setup Spotify cog
        """

    @spotify_com.group(name="playlist", aliases=["playlists"])
    async def spotify_playlist(self, ctx: commands.Context):
        """
        View Spotify Playlists
        """

    @spotify_com.group(name="artist", aliases=["artists"])
    async def spotify_artist(self, ctx: commands.Context):
        """
        View Spotify Artist info
        """

    @spotify_com.group(name="device")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_device(self, ctx: commands.Context):
        """
        Spotify device commands
        """

    async def not_authorized(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("I am not authorized to perform this action for you.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        else:
            await ctx.reply(msg, mention_author=False, ephemeral=True)

    async def not_playing(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("It appears you're not currently listening to Spotify.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        else:
            await ctx.reply(msg, mention_author=False, ephemeral=True)

    async def no_user_token(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("You need to authorize me to interact with spotify.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        else:
            await ctx.reply(msg, mention_author=False, ephemeral=True)

    async def no_device(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("I could not find an active device to play songs on.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        else:
            await ctx.reply(msg, mention_author=False, ephemeral=True)

    async def forbidden_action(
        self, ctx: Union[commands.Context, discord.Interaction], error: Exception
    ) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        if "non-premium" in str(error):
            msg = _("This action is prohibited for non-premium users.")
        else:
            msg = _("I couldn't perform that action for you.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        await ctx.reply(msg, mention_author=False, ephemeral=True)

    async def unknown_error(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Simple handler for not having authorized Spotify messages
        """
        msg = _("An exception has occured, please contact the bot owner for more assistance.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
            return
        await ctx.reply(msg, mention_author=False, ephemeral=True)

    async def get_menu_settings(
        self, guild: Optional[discord.Guild] = None
    ) -> Tuple[bool, bool, int]:
        delete_after, clear_after, timeout = False, True, 120
        if guild:
            delete_after = await self.config.guild(guild).delete_message_after()
            clear_after = await self.config.guild(guild).clear_reactions_after()
            timeout = await self.config.guild(guild).menu_timeout()

        return delete_after, clear_after, timeout

    @spotify_set.command(name="showsettings", aliases=["settings"])
    @commands.mod_or_permissions(manage_messages=True)
    async def show_settings(self, ctx: commands.Context):
        """
        Show settings for menu timeouts
        """
        async with ctx.typing():
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            msg = _(
                "Delete After: {delete_after}\nClear After: {clear_after}\nTimeout: {timeout}"
            ).format(delete_after=delete_after, clear_after=clear_after, timeout=timeout)
        await ctx.maybe_send_embed(msg)

    @spotify_set.command(name="showprivate")
    async def show_private(self, ctx: commands.Context, show_private: bool):
        """
        Set whether or not to show private playlists

        This will also display your spotify username and a link
        to your profile if you use `[p]spotify me` command in public channels.
        """
        async with ctx.typing():
            await self.config.user(ctx.author).show_private.set(show_private)
            if show_private:
                msg = _("I will show private playlists now.")
            else:
                msg = _("I will stop showing private playlists now.")
        await ctx.send(msg)

    @spotify_set.command(name="clearreactions")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_clear_reactions(self, ctx: commands.Context, clear_after: bool):
        """
        Set whether or not to clear reactions after sending the message

        Note: the bot requires manage messages for this to work
        """
        async with ctx.typing():
            await self.config.guild(ctx.guild).clear_reactions_after.set(clear_after)
            if clear_after:
                msg = _("I will now clear reactions after the menu has timed out.\n")
            else:
                msg = _("I will stop clearing reactions after the menu has timed out.\n")
            if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                msg += _(
                    "I don't have manage messages permissions so this might not work as expected."
                )
        await ctx.send(msg)

    @spotify_set.command(name="deletemessage")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_delete_message_after(self, ctx: commands.Context, delete_after: bool):
        """
        Set whether or not to delete the spotify message after timing out

        """
        async with ctx.typing():
            await self.config.guild(ctx.guild).delete_message_after.set(delete_after)
            if delete_after:
                msg = _("I will now delete the menu message after timeout.\n")
            else:
                msg = _("I will stop deleting the menu message after timeout.\n")
        await ctx.send(msg)

    @spotify_set.command(name="menutimeout")
    @commands.mod_or_permissions(manage_messages=True)
    async def guild_menu_timeout(self, ctx: commands.Context, timeout: int):
        """
        Set the timeout time for spotify menus

        `<timeout>` The time until the menu will timeout. This does not affect
        interacting with the menu.
        Note: This has a maximum of 10 minutes and a minimum of 30 seconds.
        """
        async with ctx.typing():
            timeout = max(min(600, timeout), 30)
            await self.config.guild(ctx.guild).menu_timeout.set(timeout)
            msg = _("I will timeout menus after {time} seconds.\n").format(time=timeout)
        await ctx.send(msg)

    @spotify_set.command(name="resetemojis", aliases=["resetemoji"])
    @commands.is_owner()
    async def spotify_reset_emoji(self, ctx: commands.Context):
        """
        Resets the bot to use the default emojis
        """
        async with ctx.typing():
            await self.config.emojis.clear()
            await self.config.emojis_author.clear()
            spotify_emoji_handler.reload_emojis()
        await ctx.send(_("I will now use the default emojis."))

    @spotify_set.command(name="showemojis")
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def spotify_show_emojis(self, ctx: commands.Context):
        """
        Show information about the currently set emoji pack
        """
        async with ctx.typing():
            emojis = await self.config.emojis()
            emojis_author = await self.config.emojis_author()
            yaml_str = f"author: {emojis_author}\n"
            for name, emoji in emojis.items():
                yaml_str += f"{name}: {emoji}\n"
            file = discord.File(BytesIO(yaml_str.encode("utf8")), filename="spotify_emojis.yaml")
        await ctx.send(files=[file])

    @spotify_set.command(name="emojis", with_app_command=False)
    @commands.is_owner()
    async def spotify_emojis(
        self,
        ctx: commands.Context,
        *,
        new_emojis: Optional[Union[ActionConverter, str]],
    ):
        """
        Change the emojis used by the bot for various actions

        `[new_emojis]` Is a space or comma separated list of name followed by emoji
        for example `[p]spotify set emojis playpause 😃` will then replace ⏯
        usage with the 😃 emoji.

        This command also accepts a .yaml file containing emojis
        if using custom emojis they must be in the format
        `a:name:12345` or `:name:12345`

        Example: ```yaml
        playpause: ⏯
        pause: ⏸
        repeat: 🔁
        repeatone: 🔂
        next: ⏭
        previous: ⏮
        like: 💚
        fastforward: ⏩
        rewind: ⏪
        volume_down: 🔉
        volume_up: 🔊
        volume_mute: 🔇
        playall: ⏏
        shuffle: 🔀
        back_left: ◀
        forward_right: ▶
        play: ▶
        queue: 🇶
        ```
        """
        async with ctx.typing():
            if new_emojis is None or isinstance(new_emojis, str):
                yaml_error = _("There was an error reading your yaml file.")
                if ctx.message.attachments:
                    if not ctx.message.attachments[0].filename.endswith(".yaml"):
                        await ctx.send(_("You must provide a `.yaml` file to use this command."))
                        return
                    try:
                        new_emojis = yaml.safe_load(await ctx.message.attachments[0].read())
                    except yaml.error.YAMLError:
                        await ctx.send(yaml_error)
                        return
                elif not new_emojis:
                    await ctx.send_help()
                    return
                else:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(new_emojis) as resp:
                                try:
                                    new_emojis = yaml.safe_load(await resp.read())
                                except yaml.error.YAMLError:
                                    await ctx.send(yaml_error)
                                    return
                    except Exception:
                        log.info("There was an error reading the url.", exec_info=True)
                        await ctx.send(yaml_error)
                        return
                if isinstance(new_emojis, str):
                    await ctx.send(yaml_error)
                    return

            emojis_changed = {}
            async with self.config.emojis() as emojis:
                for name, raw_emoji in new_emojis.items():
                    if name.lower() == "author":
                        await self.config.emojis_author.set(raw_emoji)
                        continue
                    emoji = discord.PartialEmoji.from_str(raw_emoji)
                    if emoji.is_unicode_emoji():
                        try:
                            await ctx.message.add_reaction(str(emoji))
                            spotify_emoji_handler.replace_emoji(name, str(emoji))
                            emojis[name] = str(emoji)
                            emojis_changed[name] = str(emoji)
                        except (InvalidEmoji, discord.errors.HTTPException):
                            pass
                    else:
                        animated = "a" if emoji.animated else ""
                        emoji_str = f"<{animated}:{emoji.name}:{emoji.id}>"
                        spotify_emoji_handler.replace_emoji(name, emoji_str)
                        emojis[name] = emoji_str
                        emojis_changed[name] = str(emoji)
            view = discord.ui.View()
            select = discord.ui.Select(placeholder=_("New Emojis"))
            msg = _("The following emojis have been replaced:\n")
            for name, emoji in emojis_changed.items():
                original = spotify_emoji_handler.default[name]
                msg += f"{original} -> {emoji}\n"
                select.add_option(label=name, emoji=discord.PartialEmoji.from_str(emoji))
            view.add_item(select)
            try:
                await ctx.send(msg, view=view)
            except Exception:
                await ctx.send(_("Emojis were reset as there was an error with one of them."))
                await self.config.emojis.clear()
                await self.config.emojis_author.clear()
                spotify_emoji_handler.reload_emojis()
                return

    @spotify_set.command(name="scope", aliases=["scopes"], with_app_command=False)
    @commands.is_owner()
    async def spotify_api_scope(self, ctx: commands.Context, *scopes: ScopeConverter):
        """
        Set customized scope for what you want your bot to allow

        Available options are:
        user-read-private
        user-top-read
        user-read-recently-played
        user-follow-read
        user-library-read
        user-read-currently-playing
        user-read-playback-state
        user-read-playback-position
        playlist-read-collaborative
        playlist-read-private
        user-follow-modify
        user-library-modify
        user-modify-playback-state
        playlist-modify-public
        playlist-modify-private

        You can find more information here:
        https://developer.spotify.com/documentation/general/guides/scopes/
        """
        async with ctx.typing():
            added = []
            removed = []
            async with self.config.scopes() as current_scope:
                for scope in scopes:
                    if scope in current_scope:
                        current_scope.remove(scope)
                        removed.append(scope)
                    else:
                        current_scope.append(scope)
                        added.append(scope)
            add = humanize_list(added)
            rem = humanize_list(removed)
            msg = ""
            if add:
                msg += _("The following scopes were added: {added}\n").format(added=add)
            if rem:
                _("The following scopes were removed: {removed}\n").format(removed=rem)
        if msg:
            await ctx.maybe_send_embed(msg)
        else:
            await ctx.send(_("No Scope settings have been changed."))

    @spotify_set.command(name="currentscope", aliases=["currentscopes"], with_app_command=False)
    @commands.is_owner()
    async def spotify_view_api_scope(self, ctx: commands.Context):
        """
        View the current scopes being requested
        """
        async with ctx.typing():
            scope = humanize_list(await self.config.scopes())
        await ctx.maybe_send_embed(_("Current scopes:\n{scopes}").format(scopes=scope))

    @spotify_set.command(name="creds", with_app_command=False)
    @commands.is_owner()
    async def spotify_api_credential_set(self, ctx: commands.Context):
        """Instructions to set the Spotify API tokens."""
        async with ctx.typing(ephemeral=True):
            message = _(
                "1. Go to Spotify developers and log in with your Spotify account.\n"
                "(https://developer.spotify.com/dashboard/applications)\n"
                '2. Click "Create An App".\n'
                "3. Fill out the form provided with your app name, etc.\n"
                '4. When asked if you\'re developing commercial integration select "No".\n'
                "5. Accept the terms and conditions.\n"
                "6. Copy your client ID and your client secret into:\n"
                "`{prefix}set api spotify client_id <your_client_id_here> "
                "client_secret <your_client_secret_here>`\n"
                "You may also provide `redirect_uri` in this command with "
                "a different redirect you would like to use but this is optional. "
                "the default redirect_uri is https://localhost/\n\n"
                "Note: The redirect URI Must be set in the Spotify Dashboard and must "
                "match either `https://localhost/` or the one you set with the `[p]set api` command"
            ).format(prefix=ctx.prefix)
            keys = {"client_id": "", "client_secret": "", "redirect_uri": "https://localhost/"}
            view = SetApiView("spotify", keys)
            if await ctx.embed_requested():
                em = discord.Embed(description=message)
                msg = await ctx.send(embed=em, view=view)
                # await ctx.send(embed=em)
            else:
                msg = await ctx.send(message, view=view)
                # await ctx.send(message)
        await view.wait()
        await msg.edit(view=None)

    @spotify_set.command(name="forgetme")
    async def spotify_forgetme(self, ctx: commands.Context):
        """
        Forget all your spotify settings and credentials on the bot
        """
        async with ctx.typing():
            author = ctx.author
            await self.config.user(author).clear()
            if author.id in self.dashboard_authed:
                self.dashboard_authed.remove(author.id)
            msg = _("All your spotify data deleted from my settings.")
        await ctx.send(msg)

    @spotify_com.command(name="me")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_me(self, ctx: commands.Context):
        """
        Shows your current Spotify Settings
        """
        async with ctx.typing(ephemeral=True):
            author = ctx.author
            is_slash = ctx.interaction is not None
            em = discord.Embed(color=discord.Colour(0x1DB954))
            em.set_author(
                name=author.display_name + _(" Spotify Profile"), icon_url=author.display_avatar
            )
            msg = ""
            cog_settings = await self.config.user(author).all()
            show_private = cog_settings["show_private"] or isinstance(
                ctx.channel, discord.DMChannel
            )
            msg += _("Show Private Playlists: {show_private}\n").format(show_private=show_private)
            if not cog_settings["token"]:
                em.description = msg
                await ctx.send(embed=em)
                return
            cur = None
            user_token = await self.get_user_auth(ctx)
            if user_token:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.current_user()
                    device_id = await self.config.user(author).default_device()
                    devices = await user_spotify.playback_devices()
                    device_name = "None"
                    for d in devices:
                        if d.id == device_id:
                            device_name = d.name
                    msg += _("Default Spotify Device: {device}").format(device=device_name)
            if cur is not None and show_private:
                msg += _(
                    "Spotify Name: [{display_name}](https://open.spotify.com/user/{user_id})\n"
                    "Subscription: {product}\n"
                ).format(display_name=cur.display_name, product=cur.product, user_id=cur.id)
            if cur is not None and (isinstance(ctx.channel, discord.DMChannel) or is_slash):
                private = _("Country: {country}\nSpotify ID: {id}\nEmail: {email}\n").format(
                    country=cur.country, id=cur.id, email=cur.email
                )
                em.add_field(name=_("Private Data"), value=private)
            if cur is not None and cur.images:
                em.set_thumbnail(url=cur.images[0].url)
            em.description = msg
        await ctx.send(embed=em)

    @spotify_com.command(name="now", aliases=["np"])
    async def spotify_now(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        member: Optional[discord.Member] = None,
        public: bool = True,
    ):
        """
        Displays your currently played spotify song

        `[member]` Optional discord member to show their current spotify status
        if they're displaying it on Discord.
        """
        async with ctx.typing(ephemeral=not public):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)

            if member and isinstance(member, discord.Member):
                if not [c for c in member.activities if c.type == discord.ActivityType.listening]:
                    msg = _("That user is not currently listening to Spotify on Discord.")
                    await ctx.send(msg)
                    return
                else:
                    activity = [
                        c for c in member.activities if c.type == discord.ActivityType.listening
                    ][0]
                    user_spotify = tekore.Spotify(sender=self._sender)
                    with user_spotify.token_as(user_token):
                        track = await user_spotify.track(activity.track_id)
            else:
                member = None
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
        try:
            if member is None:
                x = SpotifyUserMenu(
                    source=SpotifyPages(
                        user_token=user_token, sender=self._sender, detailed=detailed
                    ),
                    delete_message_after=delete_after,
                    clear_buttons_after=clear_after,
                    timeout=timeout,
                    cog=self,
                    user_token=user_token,
                    ctx=ctx,
                )
            else:
                x = SpotifySearchMenu(
                    source=SpotifyTrackPages(items=[track], detailed=detailed),
                    delete_message_after=delete_after,
                    clear_buttons_after=clear_after,
                    timeout=timeout,
                    cog=self,
                    user_token=user_token,
                )

            await x.send_initial_message(ctx, ephemeral=not public)
        except NotPlaying:
            await self.not_playing(ctx)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)

    @spotify_com.command(name="share", with_app_command=False)
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_share(self, ctx: commands.Context):
        """
        Tell the bot to play the users current song in their current voice channel
        """
        if not self.bot.get_cog("Audio"):
            await ctx.send(
                "Audio is not loaded so I cannot play your current Spotify track in a voice channel."
            )
            return

        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.playback()
                    if not cur:
                        await ctx.send(_("It appears you're not currently listening to Spotify."))
                    elif isinstance(cur.item, tekore.model.FullEpisode):
                        return await ctx.send(_("I cannot play podcasts from spotify."))
                    elif cur.is_playing and not getattr(cur.item, "is_local", False):
                        msg = copy(ctx.message)
                        prefixes = await self.bot.get_valid_prefixes(ctx.guild)
                        msg.content = f"{prefixes[0]}play {cur.item.uri}"
                        self.bot.dispatch("message", msg)
                        if not ctx.interaction:
                            await ctx.tick()
                        else:
                            await ctx.send(_("Now playing your current track"))
                    else:
                        return await ctx.send(
                            _("You don't appear to be listening to something I can play in audio.")
                        )
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_com.command(name="search")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_search(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        search_type: Optional[SearchTypes] = "track",
        *,
        query: str,
    ):
        """
        Search Spotify for things to play

        `[detailed=False]` Show detailed information for individual tracks.
        `[search_type=track]` The search type, available options are:
         - `track(s)`
         - `artist(s)`
         - `album(s)`
         - `playlist(s)`
         - `show(s)`
         - `episode(s)`
        `<query>` What you want to search for.
        """
        search_types = {
            "track": SpotifyTrackPages,
            "artist": SpotifyArtistPages,
            "album": SpotifyAlbumPages,
            "episode": SpotifyEpisodePages,
            "playlist": SpotifyPlaylistPages,
            "show": SpotifyShowPages,
        }
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)

            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                search = await user_spotify.search(query, (search_type,), "from_token", limit=50)
                items = search[0].items
            if not search[0].items:
                msg = _("No {search_type} could be found matching that query.").format(
                    search_type=search_type
                )
                await ctx.send(msg)
                return
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            x = SpotifySearchMenu(
                source=search_types[search_type](items=items, detailed=detailed),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_com.command(name="genres", aliases=["genre"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_genres(self, ctx: commands.Context):
        """
        Display all available genres for the recommendations
        """
        async with ctx.typing():
            try:
                self.GENRES = await self._spotify_client.recommendation_genre_seeds()
            except Exception:
                log.exception("Error grabbing genres.")
                msg = _(
                    "The bot owner needs to set their Spotify credentials "
                    "before this command can be used."
                    " See `{prefix}spotify set creds` for more details."
                ).format(prefix=ctx.clean_prefix)
                await ctx.send(msg)
            msg = _(
                "The following are available genres for Spotify's recommendations:\n\n {genres}"
            ).format(genres=humanize_list(self.GENRES))
        await ctx.maybe_send_embed(msg)

    @spotify_com.command(name="recommendations", aliases=["recommendation", "recommend"])
    @app_commands.choices(
        key=KEY_CHOICES,
    )
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_recommendations(
        self,
        ctx: commands.Context,
        detailed: Optional[bool] = False,
        *,
        recommendations: RecommendationsFlags,
    ):
        """
        Get Spotify Recommendations

        `<recommendations>` Requires at least 1 of the following matching objects:
         - `genre:` Must be a valid genre type. Do `[p]spotify genres` to see what's available.
         - `tracks:` Any spotify URL or URI leading to tracks will be added to the seed
         - `artists:` Any spotify URL or URI leading to artists will be added to the seed

         The following target parameters also exist and must include some additional value:
         `acousticness:`, `danceability:`, `energy:`, `instrumentalness:`,
         `liveness:`, `popularity:`, `speechiness:`, and/or `valence:` + a value from 0-100

         `key:` + A value from 0-11 representing Pitch Class notation
         `loudness:` + A value from -60 to 0 represending dB
         `mode:` + either major or minor
         `tempo:` + the tempo in BPM
         `time_signature:` + the measure of bars e.g. `3` for `3/4` or `6/8`
         `duration_ms:` the duration target of the tracks

         e.g. `[p]spotify recommendations genre: edm electronic valence: 100 mode: major`
        """
        async with ctx.typing():
            log.verbose("spotify_recommendations recommendations: %s", recommendations)
            # user_spotify = await self.get_user_spotify(ctx)
            if not any([recommendations.genres, recommendations.artists, recommendations.tracks]):
                await ctx.send(
                    _(
                        "You must provide either genres, tracks, or artists to seed the recommendations."
                    )
                )
                return
            recs = {
                "genres": recommendations.genres,
                "track_ids": recommendations.tracks,
                "artist_ids": recommendations.artists,
                "limit": 100,
                "market": "from_token",
                "target_acousticness": recommendations.acousticness,
                "target_danceability": recommendations.danceability,
                "target_energy": recommendations.energy,
                "target_instrumentalness": recommendations.instrumentalness,
                "target_key": recommendations.key,
                "target_liveness": recommendations.liveness,
                "target_loudness": recommendations.loudness,
                "target_mode": str(recommendations.mode) if recommendations.mode else None,
                "target_popularity": recommendations.popularity,
                "target_speechiness": recommendations.speechiness,
                "target_tempo": recommendations.tempo,
                "target_time_signature": recommendations.time_signature,
                "target_valence": recommendations.valence,
            }
            async with self.get_user_spotify(ctx) as user_spotify:
                try:
                    search = await user_spotify.recommendations(**recs)
                except Exception:
                    log.exception("Error getting recommendations")
                    msg = _("I could not find any recommendations with those parameters")
                    await ctx.reply(msg)
                    return
                items = search.tracks
            if not items:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            x = SpotifySearchMenu(
                source=SpotifyTrackPages(items=items, detailed=detailed, recommendations=recs),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=await self.get_user_auth(ctx),
            )
        await x.send_initial_message(ctx)

    @spotify_com.command(name="recent")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_recently_played(
        self, ctx: commands.Context, detailed: Optional[bool] = False
    ):
        """
        Displays your most recently played songs on Spotify
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    search = await user_spotify.playback_recently_played(limit=50)
                    tracks = search.items
            except tekore.Unauthorised:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            x = SpotifySearchMenu(
                source=SpotifyRecentSongPages(tracks=tracks, detailed=detailed),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_com.command(name="toptracks")
    @commands.bot_has_permissions(embed_links=True)
    async def top_tracks(self, ctx: commands.Context):
        """
        List your top tracks on spotify
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.current_user_top_tracks(limit=50)
            except tekore.Unauthorised:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            tracks = cur.items
            x = SpotifyBaseMenu(
                source=SpotifyTopTracksPages(tracks),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_com.command(name="topartists")
    @commands.bot_has_permissions(embed_links=True)
    async def top_artists(self, ctx: commands.Context):
        """
        List your top artists on spotify
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.current_user_top_artists(limit=50)
            except tekore.Unauthorised:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            artists = cur.items
            x = SpotifyBaseMenu(
                source=SpotifyTopArtistsPages(artists),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_com.command(name="new")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_new(self, ctx: commands.Context):
        """
        List new releases on Spotify
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                playlists = await user_spotify.new_releases(limit=50)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            playlist_list = playlists.items
            x = SpotifySearchMenu(
                source=SpotifyNewPages(playlist_list),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_com.command(name="pause")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_pause(self, ctx: commands.Context):
        """
        Pauses spotify for you
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_pause()
            if ctx.interaction:
                await ctx.send(_("Pausing playback."), ephemeral=True)
            else:
                await ctx.react_quietly(spotify_emoji_handler.get_emoji("pause", True))
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="resume")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_resume(self, ctx: commands.Context):
        """
        Resumes spotify for you
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            device_id = None
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                device = await self.get_device(ctx, user_spotify)
                device_id = device.id if device is not None else None
                if not cur or not cur.is_playing:
                    await user_spotify.playback_resume(device_id=device_id)
                else:
                    msg = _("You are already playing music on Spotify.")
                    await ctx.reply(msg)
            if ctx.interaction:
                await ctx.send(_("Resuming playback."))
            else:
                await ctx.react_quietly(spotify_emoji_handler.get_emoji("play", True))
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="next", aliases=["skip"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_next(self, ctx: commands.Context):
        """
        Skips to the next track in queue on Spotify
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_next()
            if ctx.interaction:
                await ctx.send(_("Skipping to next track."), ephemeral=True)
            else:
                await ctx.react_quietly(spotify_emoji_handler.get_emoji("next", True))
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="previous", aliases=["prev"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_previous(self, ctx: commands.Context):
        """
        Skips to the previous track in queue on Spotify
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                await user_spotify.playback_previous()
            if ctx.interaction:
                await ctx.send(_("Skipping to previous track."), ephemeral=True)
            else:
                await ctx.react_quietly(spotify_emoji_handler.get_emoji("previous", True))
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    async def spotify_play_tracks(
        self,
        ctx: commands.Context,
        client: tekore.Spotify,
        tracks: List[str],
        device_id: Optional[str],
    ):
        await client.playback_start_tracks(tracks, device_id=device_id)
        if ctx.interaction:
            all_tracks = await client.tracks(tracks)
            track = all_tracks[0]
            track_name = track.name
            artists = getattr(track, "artists", [])
            artist = humanize_list([a.name for a in artists])
            em = await song_embed(track, False)
            await ctx.send(
                _("Now playing {track} by {artist}").format(track=track_name, artist=artist),
                embed=em,
                ephemeral=True,
            )
        else:
            await ctx.react_quietly(
                spotify_emoji_handler.get_emoji(
                    "next",
                    True,
                )
            )

    async def spotify_play_context(
        self,
        ctx: commands.Context,
        client: tekore.Spotify,
        new_uri: str,
        uri_type: str,
        device_id: Optional[str],
    ):
        await client.playback_start_context(new_uri, device_id=device_id)
        if ctx.interaction:
            if uri_type == "playlist":
                cur_tracks = await client.playlist(new_uri)
                track_name = cur_tracks.name
                await ctx.send(
                    _("Now playing {track}").format(track=track_name),
                    ephemeral=True,
                )
            if uri_type == "artist":
                artist_id = new_uri.split(":")[-1]
                cur_tracks = await client.artist(artist_id)
                track_name = cur_tracks.name
                await ctx.send(
                    _("Now playing top tracks by {track}").format(track=track_name),
                    ephemeral=True,
                )
            if uri_type == "album":
                album_id = new_uri.split(":")[-1]
                cur_tracks = await client.album(album_id)
                track_name = cur_tracks.name
                artists = getattr(cur_tracks, "artists", [])
                track_artist = humanize_list([a.name for a in artists])
                await ctx.send(
                    _("Now playing {track} by {artist}.").format(
                        track=track_name, artist=track_artist
                    ),
                    ephemeral=True,
                )
        else:
            await ctx.react_quietly(
                spotify_emoji_handler.get_emoji(
                    "next",
                    True,
                )
            )
        return

    async def spotify_play_search(
        self,
        ctx: commands.Context,
        client: tekore.Spotify,
        url_or_playlist_name: str,
        device_id: Optional[str],
    ) -> bool:
        cur = await client.followed_playlists(limit=50)
        playlists = cur.items
        while len(playlists) < cur.total:
            new = await client.followed_playlists(limit=50, offset=len(playlists))
            for p in new.items:
                playlists.append(p)
        for playlist in playlists:
            if url_or_playlist_name.lower() in playlist.name.lower():
                await client.playback_start_context(playlist.uri, device_id=device_id)
                if ctx.interaction:
                    await ctx.send(
                        _("Now playing {playlist}").format(playlist=playlist.name),
                        ephemeral=True,
                    )
                else:
                    await ctx.react_quietly(
                        spotify_emoji_handler.get_emoji(
                            "next",
                            ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                        )
                    )
                return True
        saved_tracks = await client.saved_tracks(limit=50)
        for track in saved_tracks.items:
            if (
                url_or_playlist_name.lower() in track.track.name.lower()
                or url_or_playlist_name.lower() in ", ".join(a.name for a in track.track.artists)
            ):
                await client.playback_start_tracks([track.track.id], device_id=device_id)
                if ctx.interaction:
                    track_name = track.track.name
                    artists = getattr(track.track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    em = await song_embed(track.track, False)
                    await ctx.send(
                        _("Now playing {track} by {artist}").format(
                            track=track_name, artist=artist
                        ),
                        embed=em,
                        ephemeral=True,
                    )
                else:
                    await ctx.react_quietly(
                        spotify_emoji_handler.get_emoji(
                            "next",
                            ctx.channel.permissions_for(ctx.guild.me).use_external_emojis,
                        )
                    )
                return True
        return False

    async def spotify_play_liked_songs(
        self, ctx: commands.Context, client: tekore.Spotify, device_id: Optional[str]
    ):
        cur = await client.saved_tracks(limit=50)
        await client.playback_start_tracks([t.track.id for t in cur.items], device_id=device_id)
        # wait 2 seconds to let Spotify catch up with the newly added tracks
        await asyncio.sleep(2)
        user_token = await self.get_user_auth(ctx)
        user_menu = SpotifyUserMenu(
            source=SpotifyPages(user_token=user_token, sender=self._sender, detailed=False),
            cog=self,
            user_token=user_token,
            ctx=ctx,
        )
        await user_menu.send_initial_message(
            ctx, content=_("Now playing your last 50 liked songs."), ephemeral=True
        )
        return

    @spotify_com.command(name="play")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_play(
        self,
        ctx: commands.Context,
        *,
        url_or_playlist_name: Optional[str] = "",
    ):
        """
        Play a track, playlist, or album on Spotify

        `<url_or_playlist_name>` can be multiple spotify track URL *or* URI or
        a single album or playlist link

        if something other than a spotify URL or URI is provided
        the bot will search through your playlists and start playing
        the playlist with the closest matching name
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        url_or_playlist_name = url_or_playlist_name.replace("🧑‍🎨", ":artist:")
        # because discord will replace this in URI's automatically 🙄
        song_data = SPOTIFY_RE.finditer(url_or_playlist_name)
        tracks = []
        new_uri = ""
        uri_type = ""
        if song_data:
            for match in song_data:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                uri_type = match.group(2)
                if match.group(2) == "track":
                    tracks.append(match.group(3))
            log.verbose("spotify_play new_uri: %s", new_uri)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                device = await self.get_device(ctx, user_spotify)
                device_id = device.id if device is not None else None
                if tracks:
                    await self.spotify_play_tracks(ctx, user_spotify, tracks, device_id)
                    return
                if new_uri:
                    await self.spotify_play_context(
                        ctx, user_spotify, new_uri, uri_type, device_id
                    )
                    return
                if url_or_playlist_name:
                    if not await self.spotify_play_search(
                        ctx, user_spotify, url_or_playlist_name, device_id
                    ):
                        msg = _("I could not find any URL's or matching playlist names.")
                        await ctx.send(msg)
                    return
                else:
                    await self.spotify_play_liked_songs(ctx, user_spotify, device_id)
                    return

        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            log.debug("Error playing song", exc_info=True)
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="queue")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_queue_add(self, ctx: commands.Context, *, songs: SpotifyURIConverter):
        """
        Queue a song to play next in Spotify

        `<songs>` is one or more spotify URL or URI leading to a single track that will
        be added to your current queue
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            tracks = set()
            track_ids = set()
            for song in songs:
                if song.group(2) == "track":
                    tracks.add(f"spotify:{song.group(2)}:{song.group(3)}")
                    track_ids.add(song.group(3))
            if not tracks:
                msg = _("I can only add tracks to your spotify queue.")
                await ctx.send(msg, ephemeral=True)
                return
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    for uri in tracks:
                        log.trace("Queueing uri=%s", uri)
                        await user_spotify.playback_queue_add(uri)
                    all_tracks = await user_spotify.tracks(track_ids)
                if ctx.interaction:
                    log.debug(all_tracks)
                    track = all_tracks[0]
                    track_name = track.name
                    artists = getattr(track, "artists", [])
                    artist = humanize_list([a.name for a in artists])
                    em = await song_embed(track, False)
                    await ctx.send(
                        _("Queueing {track} by {artist}").format(track=track_name, artist=artist),
                        embed=em,
                        ephemeral=True,
                    )
                else:
                    await ctx.react_quietly(spotify_emoji_handler.get_emoji("next", True))
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    async def get_device(
        self, ctx: commands.Context, user_spotify: tekore.Spotify
    ) -> Optional[tekore.model.Device]:
        cur = await user_spotify.playback()
        if not cur:
            device_id = await self.config.user(ctx.author).default_device()
            devices = await user_spotify.playback_devices()
            device = None
            for d in devices:
                if d.id == device_id:
                    device = d
            if not device:
                await self.no_device(ctx)
                return None
            return device
        else:
            return cur.device

    @spotify_com.command(name="repeat")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_repeat(
        self, ctx: commands.Context, state: Optional[Literal["off", "track", "context"]]
    ):
        """
        Repeats your current song on spotify

        `["off"|"track"|"context"]` must accept one of `off`, `track`, or `context`.
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)

        if state and state.lower() not in ["off", "track", "context"]:
            msg = _("Repeat must accept either `off`, `track`, or `context`.")
            await ctx.send(msg, ephemeral=True)
            return
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                device = await self.get_device(ctx, user_spotify)
                device_id = device.id if device is not None else None
                if state:
                    lookup = {
                        "off": "off",
                        "context": "repeat",
                        "track": "repeatone",
                    }
                    emoji = spotify_emoji_handler.get_emoji(
                        lookup[state.lower()],
                        True,
                    )
                else:
                    if cur and cur.repeat_state == "off":
                        state = "context"
                        emoji = spotify_emoji_handler.get_emoji("repeat", True)
                    if cur and cur.repeat_state == "context":
                        state = "track"
                        emoji = spotify_emoji_handler.get_emoji(
                            "repeatone",
                            True,
                        )
                    if cur and cur.repeat_state == "track":
                        state = "off"
                        emoji = spotify_emoji_handler.get_emoji("off", True)
                    if state is None:
                        state = "off"
                        emoji = spotify_emoji_handler.get_emoji("off", True)
                await user_spotify.playback_repeat(str(state).lower(), device_id=device_id)
            if ctx.interaction:
                await ctx.send(
                    _("Setting Spotify repeat to {state} on {device}.").format(
                        state=state.title(), device=device.name
                    ),
                    ephemeral=True,
                )
            else:
                await ctx.react_quietly(emoji)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="shuffle")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_shuffle(self, ctx: commands.Context, state: Optional[bool] = None):
        """
        Shuffles your current song list

        `<state>` either true or false. Not providing this will toggle the current setting.
        """
        await ctx.defer(ephemeral=True)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                if state is None:
                    cur = await user_spotify.playback()
                    device = await self.get_device(ctx, user_spotify)
                    device_id = device.id if device is not None else None
                    if not cur:
                        state = False
                    else:
                        state = not cur.shuffle_state
                await user_spotify.playback_shuffle(state, device_id=device_id)
            if ctx.interaction:
                if state:
                    await ctx.send(_("Shuffling songs on Spotify."), ephemeral=True)
                else:
                    await ctx.send(_("Turning off shuffle on Spotify."), ephemeral=True)
            else:
                await ctx.react_quietly(spotify_emoji_handler.get_emoji("shuffle", True))
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="seek")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_seek(self, ctx: commands.Context, seconds: str):
        """
        Seek to a specific point in the current song

        `<seconds>` Accepts seconds or a value formatted like
        00:00:00 (`hh:mm:ss`) or 00:00 (`mm:ss`).
        """
        await ctx.defer(ephemeral=True)
        try:
            int(seconds)
            abs_position = False
        except ValueError:
            abs_position = True
            seconds = time_convert(seconds)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)

        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                now = cur.progress_ms
                total = cur.item.duration_ms
                emoji = spotify_emoji_handler.get_emoji("fastforward", True)
                log.verbose("spotify_seek seconds: %s", seconds)
                if abs_position:
                    to_seek = seconds * 1000
                else:
                    to_seek = seconds * 1000 + now
                if to_seek < now:
                    emoji = spotify_emoji_handler.get_emoji("rewind", True)
                if to_seek > total:
                    emoji = spotify_emoji_handler.get_emoji("next", True)
                await user_spotify.playback_seek(to_seek)
            if ctx.interaction:
                await ctx.send(_("Seeking to {time}.").format(time=seconds), ephemeral=True)
            else:
                await ctx.react_quietly(emoji)
        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_com.command(name="volume", aliases=["vol"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_volume(self, ctx: commands.Context, volume: commands.Range[int, 0, 100]):
        """
        Set your spotify volume percentage

        `<volume>` a number between 0 and 100 for volume percentage.
        """
        await ctx.defer(ephemeral=True)
        volume = max(min(100, volume), 0)  # constrains volume to be within 100
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        try:
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                cur = await user_spotify.playback()
                device = await self.get_device(ctx, user_spotify)
                device_name = device.name if device is not None else None
                await user_spotify.playback_volume(volume)
                if volume == 0:
                    emoji = spotify_emoji_handler.get_emoji(
                        "volume_mute",
                        True,
                    )
                elif cur and volume > cur.device.volume_percent:
                    emoji = spotify_emoji_handler.get_emoji(
                        "volume_up",
                        True,
                    )
                else:
                    emoji = spotify_emoji_handler.get_emoji(
                        "volume_down",
                        True,
                    )

            if ctx.interaction:
                await ctx.send(
                    _("Setting the volume on {device} to {volume}.").format(
                        volume=volume, device=device_name
                    ),
                    ephemeral=True,
                )
            else:
                await ctx.react_quietly(emoji)

        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_device.command(name="transfer")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_device_transfer(
        self,
        ctx: commands.Context,
        *,
        device_name: Optional[str] = None,
    ):
        """
        Change the currently playing spotify device

        `<device_name>` The name of the device you want to switch to.
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                is_playing = False
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    devices = await user_spotify.playback_devices()
                    now = await user_spotify.playback()
                    if now and now.is_playing:
                        is_playing = True
                new_device = None
                if device_name:
                    for d in devices:
                        if device_name.lower() in d.name.lower() or device_name == d.id:
                            log.debug("Transferring playback to %s", d.name)
                            new_device = d
                else:
                    new_view = SpotifyDeviceView(ctx)
                    options = []
                    for device in devices[:25]:
                        options.append(
                            discord.SelectOption(
                                label=device.name[:100],
                                description=str(device.type),
                                value=device.id,
                            )
                        )
                    select_view = SpotifySelectDevice(options, user_token, self._sender)
                    new_view.add_item(select_view)
                    msg = _("Pick the device you want to transfer playback to")
                    await ctx.send(msg, view=new_view)
                    # new_device = await self.spotify_pick_device(ctx, devices)
                    return
                if not new_device:
                    msg = _("I will not transfer spotify playback for you.")
                    await ctx.send(msg)
                    return
                with user_spotify.token_as(user_token):
                    await user_spotify.playback_transfer(new_device.id, is_playing)
                if ctx.interaction:
                    await ctx.send(
                        _("Transferring playback to {device}").format(device=new_device.name),
                        ephemeral=True,
                    )
                else:
                    await ctx.tick()
            except tekore.Unauthorised:
                log.debug("Error transferring playback", exc_info=True)
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_device.command(name="default")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_device_default(
        self,
        ctx: commands.Context,
        *,
        device_name: Optional[str] = None,
    ):
        """
        Set your default device to attempt to start playing new tracks on
        if you aren't currently listening to Spotify.

        `<device_name>` The name of the device you want to switch to.
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                is_playing = False
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    devices = await user_spotify.playback_devices()
                    now = await user_spotify.playback()
                    if now and now.is_playing:
                        is_playing = True
                new_device = None
                if device_name:
                    for d in devices:
                        if device_name.lower() in d.name.lower() or device_name == d.id:
                            log.debug("Transferring playback to %s", d.name)
                            new_device = d
                else:
                    new_view = SpotifyDeviceView(ctx)
                    options = []
                    for device in devices[:25]:
                        options.append(
                            discord.SelectOption(label=device.name[:25], value=device.id)
                        )
                    options.insert(0, discord.SelectOption(label="None", value="None"))
                    select_view = SpotifySelectDevice(
                        options, user_token, self._sender, send_callback=False
                    )
                    new_view.add_item(select_view)
                    msg = _("Pick the device you want to set as your default player")
                    await ctx.send(msg, view=new_view)
                    await new_view.wait()
                    device_id = select_view.device_id if select_view.device_id != "None" else None

                    if device_id:
                        for d in devices:
                            if d.id == device_id:
                                device_name = d.name
                        await self.config.user(ctx.author).default_device.set(device_id)
                    else:
                        await self.config.user(ctx.author).default_device.clear()
                        device_name = "None"
                    msg = _("Saving default device as {device}.").format(device=device_name)
                    await ctx.send(msg)
                    # new_device = await self.spotify_pick_device(ctx, devices)
                    return
                if not new_device:
                    msg = _("I will not save your default device for you.")
                    await ctx.send(msg)
                    await self.config.user(ctx.author).default_device.clear()
                    return
                await self.config.user(ctx.author).default_device.set(new_device.id)
                if ctx.interaction:
                    await ctx.send(
                        _("Saving default device as {device}.").format(device=new_device.name),
                        ephemeral=True,
                    )
                else:
                    await ctx.tick()
            except tekore.Unauthorised:
                log.debug("Error transferring playback", exc_info=True)
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_device_transfer.autocomplete("device_name")
    @spotify_device_default.autocomplete("device_name")
    async def device_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        if not await self.config.user(interaction.user).token():
            # really don't want to force users to auth from autocomplete
            log.debug("No tokens.")
            return
        ctx = await interaction.client.get_context(interaction)
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            log.debug("STILL No tokens.")
            return
        if interaction.user.id not in self._temp_user_devices:
            try:
                user_devices = []
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    devices = await user_spotify.playback_devices()
                for d in devices:
                    # user_devices.append({"name": d.name, "value": d.id})
                    user_devices.append(app_commands.Choice(name=d.name, value=d.id))
                self._temp_user_devices[interaction.user.id] = user_devices
            except Exception:
                log.exception("uhhhhhh")
                return

        choices = [
            i for i in self._temp_user_devices[interaction.user.id] if current in i.name.lower()
        ]
        return choices[:25]

    @spotify_device.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_device_list(self, ctx: commands.Context):
        """
        List all available devices for Spotify
        """
        user_token = await self.get_user_auth(ctx)
        if not user_token:
            return await self.no_user_token(ctx)
        await ctx.defer(ephemeral=True)
        try:
            is_playing = False
            user_spotify = tekore.Spotify(sender=self._sender)
            with user_spotify.token_as(user_token):
                devices = await user_spotify.playback_devices()
                now = await user_spotify.playback()
                if now and now.is_playing:
                    is_playing = True
            devices_msg = _("{author}'s Spotify Devices:\n").format(author=ctx.author.display_name)
            for c, d in enumerate(devices):
                devices_msg += f"{c+1}. `{d.name}` - {d.type} - {d.volume_percent}% "
                if d.is_active:
                    devices_msg += str(
                        spotify_emoji_handler.get_emoji(
                            "playpause",
                            True,
                        )
                    )
                devices_msg += "\n"
            await ctx.send(embed=discord.Embed(description=devices_msg), ephemeral=True)

        except tekore.Unauthorised:
            await self.not_authorized(ctx)
        except tekore.NotFound:
            await self.no_device(ctx)
        except tekore.Forbidden as e:
            await self.forbidden_action(ctx, e)
        except tekore.HTTPError:
            log.exception("Error grabing user info from spotify")
            await self.unknown_error(ctx)

    @spotify_playlist.command(name="featured")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_featured(self, ctx: commands.Context):
        """
        List your Spotify featured Playlists
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    playlists = await user_spotify.featured_playlists(limit=50)
            except tekore.Unauthorised:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            playlist_list = playlists[1].items
            x = SpotifySearchMenu(
                source=SpotifyNewPages(playlist_list),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_playlist.command(name="list", aliases=["ls"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_list(self, ctx: commands.Context):
        """
        List your Spotify Playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)

            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.followed_playlists(limit=50)
                    playlists = cur.items
                    while len(playlists) < cur.total:
                        new = await user_spotify.followed_playlists(
                            limit=50, offset=len(playlists)
                        )
                        for p in new.items:
                            playlists.append(p)
            except tekore.Unauthorised:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            show_private = await self.config.user(ctx.author).show_private() or isinstance(
                ctx.channel, discord.DMChannel
            )
            if show_private:
                playlist_list = playlists
            else:
                playlist_list = [p for p in playlists if p.public is not False]
            if len(playlist_list) == 0:
                msg = _("You don't have any saved playlists I can show here.")
                await ctx.send(msg)
                return
            x = SpotifyBaseMenu(
                source=SpotifyPlaylistsPages(playlist_list),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_playlist.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_view(self, ctx: commands.Context):
        """
        View details about your spotify playlists

        If this command is done in DM with the bot it will show private playlists
        otherwise this will not display private playlists unless showprivate
        has been toggled on.
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.followed_playlists(limit=50)
                    playlists = cur.items
                    while len(playlists) < cur.total:
                        new = await user_spotify.followed_playlists(
                            limit=50, offset=len(playlists)
                        )
                        for p in new.items:
                            playlists.append(p)
            except tekore.Unauthorised:
                return await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            show_private = await self.config.user(ctx.author).show_private() or isinstance(
                ctx.channel, discord.DMChannel
            )
            show_private = await self.config.user(ctx.author).show_private() or isinstance(
                ctx.channel, discord.DMChannel
            )
            if show_private:
                playlist_list = playlists
            else:
                playlist_list = [p for p in playlists if p.public is not False]
            if len(playlist_list) == 0:
                msg = _("You don't have any saved playlists I can show here.")
                await ctx.send(msg)
                return
            x = SpotifySearchMenu(
                source=SpotifyPlaylistPages(playlist_list, False),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)

    @spotify_playlist.command(name="create")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_create(
        self,
        ctx: commands.Context,
        name: str,
        public: Optional[bool] = False,
        *,
        description: Optional[str] = "",
    ):
        """
        Create a Spotify Playlist

        `<name>` The name of the newly created playlist
        `[public]` Wheter or not the playlist should be public, defaults to False.
        `[description]` The description of the playlist you're making.
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)

            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    user = await user_spotify.current_user()
                    await user_spotify.playlist_create(user.id, name, public, description)
                msg = _("Created {public} playlist named: {name}").format(
                    public=_("Public") if public else _("Private"), name=name
                )
                await ctx.send(msg, ephemeral=True)
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_playlist.command(name="add")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_add(
        self,
        ctx: commands.Context,
        name: str,
        *,
        to_add: SpotifyURIConverter,
    ):
        """
        Add 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to add songs to
        `<to_add>` The song links or URI's you want to add
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            tracks = []
            new_uri = ""
            for match in to_add:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                if match.group(2) == "track":
                    tracks.append(new_uri)
            if not tracks:
                msg = _("You did not provide any tracks for me to add to the playlist.")
                await ctx.send(msg, ephemeral=True)
                return
            try:
                added = False
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.followed_playlists(limit=50)
                    full_tracks = await user_spotify.tracks([m.group(3) for m in to_add])
                    playlists = cur.items
                    while len(playlists) < cur.total:
                        new = await user_spotify.followed_playlists(
                            limit=50, offset=len(playlists)
                        )
                        for p in new.items:
                            playlists.append(p)
                    for playlist in playlists:
                        if name.lower() == playlist.name.lower():
                            await user_spotify.playlist_add(playlist.id, tracks)
                            added = True
                if not added:
                    msg = _("I could not find a playlist matching {name}.").format(name=name)
                else:
                    track_names = ""
                    for track in full_tracks:
                        artists = humanize_list([a.name for a in track.artists])
                        track_names += _("- [{track_name} by {artists}]({link})\n").format(
                            track_name=track.name,
                            artists=artists,
                            link=track.external_urls.get("spotify"),
                        )
                    msg = _("I have added the following tracks to {playlist}:\n{tracks}").format(
                        playlist=name, tracks=track_names
                    )
                await ctx.send(msg)
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_playlist.command(name="remove")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_remove(
        self,
        ctx: commands.Context,
        name: str,
        *,
        to_remove: SpotifyURIConverter,
    ):
        """
        Remove 1 (or more) tracks to a spotify playlist

        `<name>` The name of playlist you want to remove songs from
        `<to_remove>` The song links or URI's you want to have removed
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            tracks = []
            new_uri = ""
            for match in to_remove:
                new_uri = f"spotify:{match.group(2)}:{match.group(3)}"
                if match.group(2) == "track":
                    tracks.append(new_uri)
            if not tracks:
                msg = _("You did not provide any tracks for me to add to the playlist.")
                await ctx.send(msg)
            try:
                added = False
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    cur = await user_spotify.followed_playlists(limit=50)
                    full_tracks = await user_spotify.tracks([m.group(3) for m in to_remove])
                    playlists = cur.items
                    while len(playlists) < cur.total:
                        new = await user_spotify.followed_playlists(
                            limit=50, offset=len(playlists)
                        )
                        for p in new.items:
                            playlists.append(p)
                    for playlist in playlists:
                        if name.lower() == playlist.name.lower():
                            await user_spotify.playlist_remove(playlist.id, tracks)
                            added = True

                if not added:
                    msg = _("I could not find a playlist matching {name}.").format(name=name)
                else:
                    track_names = ""
                    for track in full_tracks:
                        artists = humanize_list([a.name for a in track.artists])
                        track_names += _("- [{track_name} by {artists}]({link})\n").format(
                            track_name=track.name,
                            artists=artists,
                            link=track.external_urls.get("spotify"),
                        )
                    msg = _(
                        "I have removed the following tracks from {playlist}:\n{tracks}"
                    ).format(playlist=name, tracks=track_names)
                await ctx.send(msg)
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_playlist.command(name="follow")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_playlist_follow(
        self,
        ctx: commands.Context,
        public: Optional[bool] = False,
        *,
        to_follow: SpotifyURIConverter,
    ):
        """
        Add a playlist to your spotify library

        `[public]` Whether or not the followed playlist should be public after
        `<to_follow>` The song links or URI's you want to have removed
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            tracks = []
            for match in to_follow:
                if match.group(2) == "playlist":
                    tracks.append(match.group(3))
            if not tracks:
                msg = _("You did not provide any playlists for me to add to your library.")
                await ctx.send(msg)
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    for playlist in tracks:
                        await user_spotify.playlist_follow(playlist, public)
                    if not ctx.interaction:
                        await ctx.tick()
                    else:
                        await ctx.send(_("You are now following those playlists."))
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_artist.command(name="follow")
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_artist_follow(
        self,
        ctx: commands.Context,
        *,
        to_follow: SpotifyURIConverter,
    ):
        """
        Add an artist to your spotify library

        `<to_follow>` The song links or URI's you want to have removed
        """
        async with ctx.typing(ephemeral=True):
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)
            tracks = []
            for match in to_follow:
                if match.group(2) == "artist":
                    tracks.append(match.group(3))
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    for playlist in tracks:
                        await user_spotify.artist_follow(playlist)
                        msg = _("Now following {artist}").format(artist=playlist)
                await ctx.send(msg)
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            except tekore.NotFound:
                await self.no_device(ctx)
            except tekore.Forbidden as e:
                await self.forbidden_action(ctx, e)
            except tekore.HTTPError:
                log.exception("Error grabing user info from spotify")
                await self.unknown_error(ctx)

    @spotify_artist.command(name="albums", aliases=["album"])
    @commands.bot_has_permissions(embed_links=True)
    async def spotify_artist_albums(
        self,
        ctx: commands.Context,
        *,
        to_follow: SpotifyURIConverter,
    ):
        """
        View an artists albums

        `<to_follow>` The artis links or URI's you want to view the albums of
        """
        async with ctx.typing():
            user_token = await self.get_user_auth(ctx)
            if not user_token:
                return await self.no_user_token(ctx)

            tracks = []
            for match in to_follow:
                if match.group(2) == "artist":
                    tracks.append(match.group(3))
            if not tracks:
                msg = _("You did not provide an artist link or URI.")
                await ctx.send(msg, ephemeral=True)
                return
            try:
                user_spotify = tekore.Spotify(sender=self._sender)
                with user_spotify.token_as(user_token):
                    search = await user_spotify.artist_albums(tracks[0], limit=50)
                    tracks = search.items
            except tekore.Unauthorised:
                await self.not_authorized(ctx)
            delete_after, clear_after, timeout = await self.get_menu_settings(ctx.guild)
            x = SpotifySearchMenu(
                source=SpotifyAlbumPages(tracks, False),
                delete_message_after=delete_after,
                clear_buttons_after=clear_after,
                timeout=timeout,
                cog=self,
                user_token=user_token,
            )
        await x.send_initial_message(ctx)
