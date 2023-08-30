from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

if TYPE_CHECKING:
    from .abc import RoleToolsMixin

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsView(discord.ui.View):
    def __init__(self, cog: RoleToolsMixin, *, timeout: Optional[float] = None):
        self.cog = cog
        super().__init__(timeout=timeout)
        self.buttons = set()
        self.selects = set()

    def __repr__(self):
        return f"<RoleToolsView buttons={self.buttons} selects={self.selects}>"

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: Union[SelectRole, ButtonRole],
    ):
        # await interaction.response.send_message(
        #     _("An error occured trying to apply a role to you."), ephemeral=True
        # )
        log.error("An error occured %s with interaction %s: %s", item, interaction, error)

    def add_item(self, item: Union[SelectRole, ButtonRole]):
        rt_type = getattr(item, "_rt_type", None)
        if rt_type == "select":
            self.selects.add(item.custom_id)
        elif rt_type == "button":
            self.buttons.add(item.custom_id)
        else:
            raise TypeError("This view can only contain `SelectRole` or `ButtonRole` items.")
        super().add_item(item)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.guild.id == 574071914415259648:
            log.debug(
                "buttons %s - menus %s on interaction ID: %s",
                self.buttons,
                self.selects,
                interaction.id,
            )
        return True

    async def edit_components(self, interaction: discord.Interaction):
        await interaction.message.edit(view=self)


class ButtonRole(discord.ui.Button):
    def __init__(
        self,
        style: int,
        label: str,
        emoji: Union[discord.PartialEmoji, str],
        custom_id: str,
        role_id: int,
        name: str,
    ):
        self._original_label = label
        super().__init__(
            style=discord.ButtonStyle(style), label=label, emoji=emoji, custom_id=custom_id
        )
        self.role_id = role_id
        self.name = name
        self._rt_type = "button"  # to prevent circular import

    def replace_label(self, guild: discord.Guild):
        role = guild.get_role(self.role_id)
        if role is None:
            return
        if self._original_label is not None:
            label = self._original_label.replace("{count}", str(len(role.members)))
            self.label = label

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.message.guild
        if self.disabled:
            await interaction.response.send_message(
                _("This button has been disabled from giving roles."), ephemeral=True
            )
            return
        role = guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message(
                _("The role assigned for this button does not appear to exist anymore."),
                ephemeral=True,
            )
            return
        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots are not allowed to assign their own roles."
            )
            return
        config = self.view.cog.config
        if role not in interaction.user.roles:
            if not await config.role(role).selfassignable():
                await interaction.response.send_message(
                    _("{role} is not currently self assignable.").format(role=role.mention),
                    ephemeral=True,
                )
                return
            if wait_time := await self.view.cog.check_guild_verification(interaction.user, guild):
                # log.debug("Ignoring user due to verification check.")
                if wait_time:
                    wait = datetime.now(timezone.utc) + timedelta(seconds=wait_time)
                    await interaction.response.send_message(
                        _(
                            "I cannot assign roles to you until you have spent more time in this server. Try again {time}."
                        ).format(time=discord.utils.format_dt(wait)),
                        ephemeral=True,
                    )
                return
            if getattr(interaction.user, "pending", False):
                await interaction.response.send_message(
                    _(
                        "You need to finish your member verification before I can assign you a role."
                    ),
                    ephemeral=True,
                )
                return
            # log.debug(f"Adding role to {interaction.user.name} in {guild}")
            response = await self.view.cog.give_roles(interaction.user, [role], _("Button Role"))
            if response:
                await interaction.response.send_message(
                    _("I could not assign {role} for the following reasons: {reasons}").format(
                        role=role.mention, reasons="\n".join(r.reason for r in response)
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                _("I have given you the {role} role.").format(role=role.mention), ephemeral=True
            )
        elif role in interaction.user.roles:
            if not await config.role(role).selfremovable():
                await interaction.response.send_message(
                    _("{role} is not currently self removable.").format(role=role.mention),
                    ephemeral=True,
                )
                return
            # log.debug(f"Removing role from {interaction.user.name} in {guild}")
            await self.view.cog.remove_roles(interaction.user, [role], _("Button Role"))
            await interaction.response.send_message(
                _("I have removed the {role} role from you.").format(role=role.mention),
                ephemeral=True,
            )
        self.replace_label(guild)
        await self.view.edit_components(interaction)


class SelectRoleOption(discord.SelectOption):
    def __init__(
        self,
        name: str,
        label: str,
        value: str,
        role_id: int,
        description: Optional[str],
        emoji: Optional[Union[discord.PartialEmoji, str]],
    ):
        super().__init__(label=label, emoji=emoji, description=description, value=value)
        self.role_id = role_id
        self.name = name
        self.disabled: bool = False


class SelectRole(discord.ui.Select):
    def __init__(
        self,
        name: str,
        custom_id: str,
        min_values: int,
        max_values: int,
        placeholder: Optional[str],
        options: List[SelectRoleOption],
        disabled: List[str] = [],
    ):
        super().__init__(
            options=options,
            min_values=min_values,
            max_values=max_values,
            placeholder=placeholder,
            custom_id=custom_id,
        )
        self._original_labels: Dict[str, Dict[str, Optional[str]]] = {
            o.value: {"label": o.label, "description": o.description} for o in options
        }
        self.name = name
        self.disabled_options: List[str] = disabled
        self.view: RoleToolsView
        self._rt_type = "select"  # to prevent circular import

    def update_options(self, guild: discord.Guild):
        for option in self.options:
            role_id = option.value.split("-")[-1]
            role = guild.get_role(int(role_id))
            original = self._original_labels[option.value]
            if role is not None:
                if not original["label"]:
                    original["label"] = "\u200b"
                if original["label"]:
                    option.label = original["label"].replace("{count}", str(len(role.members)))
                if original["description"]:
                    option.description = original["description"].replace(
                        "{count}", str(len(role.members))
                    )

    async def callback(self, interaction: discord.Interaction):
        no_selection = self.values == []
        role_ids = []
        disabled_role = False
        for option in self.values:
            if option.split("-")[1] in self.disabled_options:
                disabled_role = True
                continue
            role_ids.append(int(option.split("-")[-1]))

        await interaction.response.defer(ephemeral=True, thinking=True)
        msg = ""
        if disabled_role:
            msg += _("One or more of the selected roles are no longer available.\n")
        elif self.disabled:
            await interaction.response.send_message(
                _("This selection has been disabled from giving roles."), ephemeral=True
            )
            await interaction.message.edit()
            return
        guild = interaction.guild
        added_roles = []
        removed_roles = []
        missing_role = False
        pending = False
        wait = None
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role is None:
                missing_role = True
                continue
            if interaction.user.bot:
                # how? This is what happens when you copy/paste code lol
                # # even if it's your own code
                # ## Especially if it's your own code
                continue
            config = self.view.cog.config
            if role not in interaction.user.roles:
                if not await config.role(role).selfassignable():
                    msg += _(
                        "{role} Could not be assigned because it is not self assignable."
                    ).format(role=role.mention)
                    continue

                if wait_time := await self.view.cog.check_guild_verification(
                    interaction.user, guild
                ):
                    # log.debug("Ignoring %s due to verification check.", interaction.user.name)
                    if wait_time:
                        wait = datetime.now(timezone.utc) + timedelta(seconds=wait_time)
                    continue
                if getattr(interaction.user, "pending", False):
                    pending = True
                    continue
                # log.debug("Adding role to %s in %s", interaction.user.name, guild)
                response = await self.view.cog.give_roles(
                    interaction.user, [role], _("Role Selection")
                )
                if response:
                    continue
                added_roles.append(role)
            elif role in interaction.user.roles:
                if not await config.role(role).selfremovable():
                    msg += _(
                        "{role} Could not be removed because it is not self assignable."
                    ).format(role=role.mention)
                    continue
                # log.debug("Removing role from %s in %s", interaction.user.name, guild)
                await self.view.cog.remove_roles(interaction.user, [role], _("Role Selection"))
                removed_roles.append(role)
        if wait is not None:
            msg += _(
                "I cannot assign roles to you until you have spent more time in this server. Try again {time}."
            ).format(time=discord.utils.format_dt(wait))
        if pending:
            msg += _("You need to finish your member verification before I can assign you a role.")
        if missing_role:
            msg += _("One or more of the selected roles no longer exists.\n")
        if added_roles:
            msg += _("I have given you the following roles: {roles}\n").format(
                roles=humanize_list([i.mention for i in added_roles])
            )
        if removed_roles:
            msg += _("I have removed the following roles from you: {roles}\n").format(
                roles=humanize_list([i.mention for i in removed_roles])
            )
        if msg:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            msg = _("I have not made any role changes to you.\n")
            if no_selection:
                msg += _("You have made no selections; try again to change your roles.")
            await interaction.followup.send(msg, ephemeral=True)
        self.update_options(guild)
        await self.view.edit_components(interaction)
