SLASH_COMMANDS = {
    "name": "roletools",
    "description": "Commands for creating custom role settings",
    "options": [
        {
            "name": "exclude",
            "description": "Set role exclusions",
            "type": 2,
            "options": [
                {
                    "name": "remove",
                    "description": "Remove role exclusion",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "exclude", "description": ".", "type": 8, "required": True},
                    ],
                },
                {
                    "name": "add",
                    "description": "Add role exclusion (This will remove if the designated role is acquired",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "exclude", "description": ".", "type": 8, "required": True},
                    ],
                },
            ],
        },
        {
            "name": "sticky",
            "description": "Set whether or not a role will be re-applied when a user leaves and rejoins the server.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "true_or_false", "description": ".", "type": 5, "required": False},
            ],
        },
        {
            "name": "react",
            "description": "Create a reaction role",
            "type": 1,
            "options": [
                {"name": "message", "description": ".", "type": 3, "required": True},
                {"name": "emoji", "description": ".", "type": 3, "required": True},
                {"name": "role", "description": ".", "type": 8, "required": True},
            ],
        },
        {
            "name": "selfrem",
            "description": "Set whether or not a user can remove the role from themselves.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "true_or_false", "description": ".", "type": 5, "required": False},
            ],
        },
        {
            "name": "buttons",
            "description": "Setup role buttons",
            "type": 2,
            "options": [
                {
                    "name": "view",
                    "description": "View current buttons setup for role assign in this server.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "send",
                    "description": "Send buttons to a specified channel with optional message.",
                    "type": 1,
                    "options": [
                        {"name": "channel", "description": ".", "type": 7, "required": True},
                        {"name": "buttons", "description": ".", "type": 3, "required": True, "autocomplete": True},
                        {"name": "message", "description": ".", "type": 3, "required": True},
                    ],
                },
                {
                    "name": "create",
                    "description": "Create a role button",
                    "type": 1,
                    "options": [
                        {"name": "name", "description": ".", "type": 3, "required": True},
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "emoji", "description": ".", "type": 3, "required": False},
                        {"name": "label", "description": ".", "type": 3, "required": False},
                        {"name": "style", "description": ".", "type": 3, "required": False},
                    ],
                },
                {
                    "name": "delete",
                    "description": "Delete a saved button.",
                    "type": 1,
                    "options": [
                        {"name": "name", "description": ".", "type": 3, "required": True}
                    ],
                },
                {
                    "name": "edit",
                    "description": "Edit a bots message to include Role Buttons",
                    "type": 1,
                    "options": [
                        {"name": "message", "description": ".", "type": 3, "required": True},
                        {"name": "buttons", "description": ".", "type": 3, "required": True, "autocomplete": True},
                    ],
                },
            ],
        },
        {
            "name": "giverole",
            "description": "Gives a role to designated members.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "who", "description": ".", "type": 9, "required": True},
            ],
        },
        {
            "name": "viewroles",
            "description": "View current roletools setup for each role in the server",
            "type": 1,
            "options": [{"name": "role", "description": ".", "type": 8, "required": False}],
        },
        {
            "name": "select",
            "description": "Setup role select menus",
            "type": 2,
            "options": [
                {
                    "name": "create",
                    "description": "Create a select menu",
                    "type": 1,
                    "options": [
                        {"name": "name", "description": ".", "type": 3, "required": True},
                        {"name": "options", "description": ".", "type": 3, "required": True, "autocomplete": True},
                        {
                            "name": "min_values",
                            "description": ".",
                            "type": 4,
                            "required": False,
                        },
                        {
                            "name": "max_values",
                            "description": ".",
                            "type": 4,
                            "required": False,
                        },
                        {
                            "name": "placeholder",
                            "description": ".",
                            "type": 3,
                            "required": False,
                        },
                    ],
                },
                {
                    "name": "viewoptions",
                    "description": "View current select menus setup for role assign in this server.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "deleteoption",
                    "description": "Delete a saved option.",
                    "type": 1,
                    "options": [
                        {"name": "name", "description": ".", "type": 3, "required": True, "autocomplete": True}
                    ],
                },
                {
                    "name": "view",
                    "description": "View current select menus setup for role assign in this server.",
                    "type": 1,
                    "options": [],
                },
                {
                    "name": "createoption",
                    "description": "Create a select menu option",
                    "type": 1,
                    "options": [
                        {"name": "name", "description": ".", "type": 3, "required": True},
                        {"name": "role", "description": ".", "type": 3, "required": True},
                        {"name": "emoji", "description": ".", "type": 3, "required": True},
                        {"name": "label", "description": ".", "type": 3, "required": False},
                        {
                            "name": "description",
                            "description": ".",
                            "type": 3,
                            "required": False,
                        },
                    ],
                },
                {
                    "name": "delete",
                    "description": "Delete a saved select menu.",
                    "type": 1,
                    "options": [
                        {"name": "name", "description": ".", "type": 3, "required": True, "autocomplete": True}
                    ],
                },
                {
                    "name": "edit",
                    "description": "Edit a bots message to include Role select menus",
                    "type": 1,
                    "options": [
                        {"name": "message", "description": ".", "type": 3, "required": True},
                        {"name": "menus", "description": ".", "type": 3, "required": True, "autocomplete": True},
                    ],
                },
                {
                    "name": "send",
                    "description": "Send a select menu to a specified channel for role assignment",
                    "type": 1,
                    "options": [
                        {"name": "channel", "description": ".", "type": 7, "required": True},
                        {"name": "menus", "description": ".", "type": 3, "required": True, "autocomplete": True},
                        {"name": "message", "description": ".", "type": 3, "required": True},
                    ],
                },
            ],
        },
        {
            "name": "forcerole",
            "description": "Force a sticky role on one or more users.",
            "type": 1,
            "options": [
                {"name": "users", "description": ".", "type": 6, "required": True},
                {"name": "role", "description": ".", "type": 8, "required": True},
            ],
        },
        {
            "name": "selfrole",
            "description": "Add or remove a defined selfrole",
            "type": 2,
            "options": [
                {
                    "name": "remove",
                    "description": "Remove a role from yourself",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True}
                    ],
                },
                {
                    "name": "add",
                    "description": "Give yourself a role",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True}
                    ],
                }
            ],
        },
        {
            "name": "include",
            "description": "Set role inclusion",
            "type": 2,
            "options": [
                {
                    "name": "remove",
                    "description": "Remove role inclusion",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "include", "description": ".", "type": 8, "required": True},
                    ],
                },
                {
                    "name": "add",
                    "description": "Add role inclusion (This will add roles if the designated role is acquired",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "include", "description": ".", "type": 8, "required": True},
                    ],
                },
            ],
        },
        {
            "name": "cleanup",
            "description": "Cleanup old/missing reaction roles and settings.",
            "type": 1,
            "options": [],
        },
        {
            "name": "autorole",
            "description": "Set a role to be automatically applied when a user joins the server.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "true_or_false", "description": ".", "type": 5, "required": False},
            ],
        },
        {
            "name": "selfadd",
            "description": "Set whether or not a user can apply the role to themselves.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "true_or_false", "description": ".", "type": 5, "required": False},
            ],
        },
        {
            "name": "required",
            "description": "Set role requirements",
            "type": 2,
            "options": [
                {
                    "name": "add",
                    "description": "Add role requirements",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "required", "description": ".", "type": 8, "required": True},
                    ],
                },
                {
                    "name": "remove",
                    "description": "Remove role requirements",
                    "type": 1,
                    "options": [
                        {"name": "role", "description": ".", "type": 8, "required": True},
                        {"name": "required", "description": ".", "type": 8, "required": True},
                    ],
                },
            ],
        },
        {
            "name": "forceroleremove",
            "description": "Force remove sticky role on one or more users.",
            "type": 1,
            "options": [
                {"name": "users", "description": ".", "type": 6, "required": True},
                {"name": "role", "description": ".", "type": 8, "required": True},
            ],
        },
        {
            "name": "reactroles",
            "description": "View current bound roles in the server",
            "type": 1,
            "options": [],
        },
        {
            "name": "cost",
            "description": "Set whether or not a user can remove the role from themselves.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "cost", "description": ".", "type": 4, "required": False},
            ],
        },
        {
            "name": "removerole",
            "description": "Removes a role from the designated members.",
            "type": 1,
            "options": [
                {"name": "role", "description": ".", "type": 8, "required": True},
                {"name": "who", "description": ".", "type": 9, "required": True},
            ],
        },
        {
            "name": "remreact",
            "description": "Remove a reaction role",
            "type": 1,
            "options": [
                {"name": "message", "description": ".", "type": 3, "required": True},
                {"name": "role_or_emoji", "description": ".", "type": 3, "required": True},
            ],
        },
        {
            "name": "clearreact",
            "description": "Clear the reactions for reaction roles. This will remove",
            "type": 1,
            "options": [
                {"name": "message", "description": ".", "type": 3, "required": True},
                {"name": "emojis", "description": ".", "type": 3, "required": False},
            ],
        },
        {
            "name": "atomic",
            "description": "Set the atomicity of role assignment.",
            "type": 1,
            "options": [
                {"name": "true_or_false", "description": ".", "type": 5, "required": True}
            ],
        },
    ],
}
