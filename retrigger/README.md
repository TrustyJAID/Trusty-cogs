# How to use ReTrigger

ReTrigger is a highly versatile cog that allows server moderators and administrators to automatically perform many tasks based on regular expressions (regex) in chat. https://regex101.com/ Is suggested to test out any regular expression patterns you want before adding to the bot. Some commonly used tools include:

 - `\b` meaning word boundaries usually used at the beginning and end of the word or sentence to avoid triggering on `testing` when you only want `test`. (e.g. regex of `\bhello, world\b` will __only__ trigger if someone says exactly `hello, world` and not `hello, worlds`.)
 - `(?i)` at the beginning of the regex will ignore cases in the search so `test`, `Test`, and `TEST` are treated the same.
 - **Groups** can be utilized to pick specific parts of the pattern to be used later. Groups look like `(^I wanna be )([^.]*)` where everything inside the `()` brackets are a group. Groups are numbered 0 and up where 0 is the full pattern, 1 would be `I wanna be` and 2 would be `[^.]*]`. In this example anything after the words `I wanna be` is captured and can then be used in the response of the trigger by using `{2}` to signify group 2.
 - More useful special characters:
    - `^` signifies the start of a string.
    - `$` signifies the end of a string.
    - `?` 0 or 1 of the previous character or group.
    - `+` 1 or more of the previous character or group.
    - `*` 0 or more of the previous character or group.
    - `.` any character other than newline.
    - `|` **or** statement meaning this **or** that.

Special replacement parameters are as follows:
- `{p}` can be used to replace the bots default prefix in the message.
- `{pp}` can be used to list all the bots prefixes available on the server.
- `{count}` can be used to show the number of times a trigger has been triggered.
- `{nummatch}` can be used to replace the number of matches the pattern found.
- `{lenmessage}` can be used to replace the length of the message.
- `{lenmatch}` can be used to replace the length of the largest match found.



## Basic Commands
### **text**
__Usage:__ `[p]retrigger text <name> <regex> <text>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `[delete_after]` Optionally have the text autodelete must include units e.g. 2m.
- `<text>` response of the trigger
This will send a message when the regex pattern supplied matches.
Text is the most basic response you can use and as such it has many options available to you.
Regex groups can be used to replace text in the response with a matched group just like the example above. Additionally other parameters are available such as `{author.name}`, `{message.jump_url}`, etc. [See Red's Customcom](https://red-discordbot.readthedocs.io/en/latest/cog_customcom.html#context-parameters) for more examples.

### **addrole**
__Usage:__ `[p]retrigger addrole <name> <regex> [roles...]`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will give a user a role when the regex pattern supplied matches.
**Note:** People with `Manage Roles` permission, modroles, adminroles, and automod immune are automatically ignored from retrigger addrole.

### **removerole**
__Usage:__ `[p]retrigger removerole <name> <regex> [roles...]`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will remove a role when the regex pattern supplied matches.
**Note:** People with `Manage Roles` permission, modroles, adminroles, and automod immune are automatically ignored from retrigger removerole.

### **ban**
__Usage:__ `[p]retrigger ban <name> <regex>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will ban a user when the regex pattern supplied matches.
**Note:** People with `Ban Members` permission, modroles, adminroles, and automod immune are automatically ignored from retrigger ban.

### **kick**
__Usage:__ `[p]retrigger kick <name> <regex>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will kick the user when the regex pattern supplied matches.
**Note:** People with `Kick Members` permission, modroles, adminroles, and automod immune are automatically ignored from retrigger kick.

### **command**
__Usage:__ `[p]retrigger command <name> <regex> <command>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `<command>` the command that will be run. You can utilize `<text>` groups and other replacements to build the command to function how you want.
- **Aliases:** `cmd`
This will perform the supplied command when the regex pattern supplied matches. The bots `[p]` prefix is not required for the command. The features from text responses are available inside the command formation here as well. For example `{author.name}` may be placed to have the user say something that triggers a command requiring a user be in the command structure. e.g. `[p]retrigger command test \btest\b insult {author}` would ensure whenever someone says `test` they get insulted by an insult command.

### **dm**
__Usage:__ `[p]retrigger dm <name> <regex> <text>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.

This will dm the user when the regex pattern supplied matches.
All text options are available here as well.

### **dmme**
__Usage:__ `[p]retrigger dmme <name> <regex> <text>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will dm *you* (the author of the trigger) when the regex pattern supplied matches.
All text options are available here as well.

### **filter**
__Usage:__ `retrigger filter <name> [check_filenames=False] <regex>`
- `<name>` is the name of the trigger.
`[check_filenames=False]` can be set to True or False (default is False) and will append any attached filenames in the message to the text for searching
- `<regex>` the regex that will determine when to respond.
- **Aliases:** `deletemsg`
This will delete the message when the regex pattern supplied matches.
**Note:** People with `Manage Messages` permission, modroles, adminroles, and automod immune are automatically ignored from retrigger filters.

### **image**
__Usage:__ `[p]retrigger image <name> <regex> [image_url]`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `[image_url]` is optional, if not supplied the bot will ask you to upload one.

This will upload an image when the regex pattern supplied matches.

### **imagetext**
__Usage:__ `[p]retrigger imagetext <name> <regex> <text> [image_url]`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `<text>` The text response for the trigger.
- `[image_url]` is optional, if not supplied the bot will ask you to upload one.

This will send text *and* upload an image when the regex pattern supplied matches.
All text options are available here as well.

### **random**
__Usage:__ `[p]retrigger random <name> <regex>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will send a random text response when the regex pattern supplied matches.
All text options are available here as well. After supplied the bot will ask you to start typing responses.
- **Aliases:** `randomtext`, and `rtext`.

### **randomimage**
__Usage:__ `[p]retrigger randomimage <name> <regex>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- **Aliases:** `randimage`, `randimg`, `rimage`, `rimg`
This will upload a random image when the regex pattern supplied matches. After supplied the bot will ask you to start uploading images to be used.

### **react**
__Usage:__ `[p]retrigger react <name> <regex> [emojis...]`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `[emojis...]` is all the emojis you want the bot to react with.
This will react with emojis when the regex pattern supplied matches.

### **rename**
__Usage:__ `[p]retrigger rename <name> <regex> <text>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `<text>` new users nickanme.
This will rename users nicknames.

### **resize**
**Requires that `pillow` be installed on the bot.**
__Usage:__ `[p]retrigger resize <name> <regex> [image_url]`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `[image_url]` is optional, if not supplied the bot will ask you to upload one.
This will upload varying sized images depending on the length of the matching trigger.
Example: `[p]retrigger resize reee (?i)\br+e{3,}\b` With the image ![https://i.imgur.com/ZG5saum.png](https://i.imgur.com/ZG5saum.png) will upload different sizes if somone types `REEE` or `reeeeeeeeeeeeeeeeeeeeeeee`.

### **Publish**
**Only functions inside news channels**
__Usage:__ `[p]retrigger publish <name> <regex>`
- `<name>` is the name of the trigger.
- `<regex>` the regex that will determine when to respond.
This will attempt to publish specific messages posted inside news channels based on matching patterns. Moreso for those lazy admins who forget to press the big shiny button or happened to disable it by mistake and keep forgetting. (Note: You're currently allowed 10 published messages per hour and this will attempt to wait until it can actually publish before completing or the bot restarts.)

### **multi**
__Usage:__ `[p]retrigger multi <name> <regex> [multi_response...]`
Add a multiple response trigger
- `<name>` name of the trigger.
- `<regex>` the regex that will determine when to respond.
- `[multi_response...]` the list of actions the bot will perform.
Multiple responses start with the name of the action which must be one of the listed options below, followed by a `;` if there is a followup response add a space for the next trigger response. If you want to add or remove multiple roles those may be
followed up with additional `;` separations.
e.g. `[p]retrigger multi test \btest\b "dm;You said a bad word!" filter "remove_role;Regular Member" add_role;Timeout`
Will attempt to DM the user, delete their message, remove their `@Regular Member` role and add the `@Timeout` role simultaneously.
Available options:
- dm
- dmme
- remove_role
- add_role
- ban
- kick
- text
- filter or delete
- react
- command
- rename
- publish



## Utility Commands
### **list**
__Usage:__ `[p]retrigger list [trigger]`

- `<trigger>` is the name of a trigger, if not supplied all triggers will be listed in a menu to see them all.
- ▶ will display the next trigger in the list
- ◀ will display the previous trigger in the list
- ⏭ will jump to the last trigger in the list
- ⏮ will jump to the first trigger in the list
- ⏯ will toggle the displayed triggers active setting
- ❎ will toggle the displayed trigger to be not active
- ✅ will toggle the displayed trigger to be active
- 🚮 will delete the displayed trigger


### **remove**
__Usage:__ `[p]retrigger remove <trigger>`
- `<trigger>` is the name of the trigger you want to delete.
This will delete a trigger.

### **cooldown**
__Usage:__ `[p]retrigger cooldown <trigger> <time> [style=guild]`
Set cooldown options for specified triggers. This can be used to ensure a trigger is not constantly spammed by giving some time until it is allowed to be triggered again. Time must be in seconds.

### **blacklist**
Set blacklist options for specified triggers.
Blacklist will ensure **everyone except** the objects added to the trigger blacklist will trigger. For example if you blacklist a role for the trigger anyone with that role will **not** trigger it. This can be useful for removing select bad actors from spamming specific triggers over and over. **Note:** If a whitelist is present on the trigger anything in the blacklist is ignored.
 - **add** Add a channel, user, or role to a triggers blacklist.
  __Usage:__ `[p]retrigger blacklist add <trigger> [channel_user_role...]`
 	multiple channels, users, or roles can be added at the same time.
 - **remove** Remove a channel, user, or role from a triggers blacklist.
  __Usage:__ `[p]retrigger blacklist remove <trigger> [channel_user_role...]`
 	multiple channels, users, or roles can be added at the same time.

### **whitelist**
Set whitelist options for specified triggers.
Whitelist will ensure **only** the objects added to the trigger whitelist will actually trigger. For example if you whitelist a role for the trigger only users with that role can actually trigger it. This can be useful for setting specific triggers to only occur in a specified channel and help with automatic moderation of specific channels/users/roles.
 - **add** Add a channel, user, or role to a triggers whitelist.
 __Usage:__ `[p]retrigger whitelist add <trigger> [channel_user_role...]`
 	multiple channels, users, or roles can be added at the same time.
 - **remove** Remove a channel, user, or role from a triggers whitelist.
 __Usage:__ `[p]retrigger whitelist remove <trigger> [channel_user_role...]`
 	multiple channels, users, or roles can be added at the same time.

### **edit**
Edit various settings in a set trigger.
 - **regex** Edit the regex of a saved trigger.
 - **edited** Toggle whether the bot will listen to edited messages as well as `on_message` for the specified trigger.
 - **ignorecommands** Toggle the regex matching inside normally ignored command messages.
 - **ocr** Toggle whether to use Optical Character Recognition to search for text within images. **Requires `pytesseract-ocr` and [google tesseract]([https://github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract)) be installed on the host machine.**
   images
 - **react** Edit the emoji reactions of a saved trigger. **Note:** This cannot be used on *multi* triggers.
 - **command** Edit the text of a saved trigger. **Note:** This cannot be used on *multi* triggers.
 - **role** Edit the added or removed roles of a saved trigger. **Note:** This cannot be used on *multi* triggers.
 - **text** Edit the response text of a saved trigger. **Note:** This cannot be used on *multi* triggers.
 - **readfilenames** Edit whether or not a trigger will append filenames of attachments to the search.
 - **deleteafter** Text triggers can have an optional delete_after time set, this can be used to edit it.
 - **chance** Triggers can be setup with a chance to occur in form of `1 in chance`.

### **modlog**
Set which events to record in the modlog. ReTrigger has a built in modlog setup which can be used to track when and how ReTrigger is performing automated moderation actions.

 - **addroles** Toggle custom add role messages in the modlog.
 - **bans** Toggle custom ban messages in the modlog.
 - **channel** Set the modlog channel for filtered words.
 - **filter** Toggle custom filter messages in the modlog.
 - **kicks** Toggle custom kick messages in the modlog.
 - **removeroles** Toggle custom add role messages in the modlog.
 - **settings** Show the current modlog settings for this server.



## F.A.Q.
__Can ReTrigger perform different actions if a user triggers it enough times?__
 - No. This is better suited for an entirely separate cog. This one is highly complex as it is and meant more as a versatile trigger system not automatic moderation although it can still be used as an automatic moderation tool.

__Can ReTrigger warn a user automatically?__
 - Yes! Although there is a risk involved in allowing this, as such it's hidden by normal usage. What you want to do is `[p] retrigger mock` which will then perform the same function as the `command` trigger but rather than run the command as the user who sent the message it runs the command as the user who *created* the trigger. Meaning that it's possible to supply someone full bot access if you're not careful with how you handle this and one could even force shutoff the bot. So be careful but the utility is there.

 __Can ReTrigger read the headers of files uploaded to see if they're malicious?__
  - No. This is something discord already handles for the most part and if it's an issue you have on a regular basis ensure you're reporting to discord. If you were looking instead to read the text inside an image for bad words that *is* do-able now through Optical Character Recognition support requiring that `pytesseract-ocr` and [google tesseract]([https://github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract)) are installed on the host machine. Then your trigger needs to have OCR toggled on.

__ReTrigger seems to be taking up a lot of ram, is this normal?__
 - Unfortunately yes it is. In order to allow *safe* regular expression searches with full features and not let bad users input a regex pattern that will take minutes-hours to fully search due to regression the cog utilizes multiprocessing which increases the memory usage. I would recommend adding more SWAP memory to alleviate some of these issues if you're tight on ram.

 __ReTrigger filter isn't working for me!__
  - Most likely the people you have testing it have Manage Messages permission. This was done because people with that permission are more than likely trusted not to post things they shouldn't be and they have the power to remove those messages from other people. No there's no way to bypass this, they're immune as an extra layer of protection alongside people with ban members permission so that people can't ban themselves or supply themselves roles they're not supposed to. Last thing you want is to accidentally ban someone for something silly like a bot function.

__ReTrigger stopped responding to one of my triggers, HALP!__
 - That's not a question? Anyways please share full details and tracebacks in my channel in the cog server. I suspect the issue might be that you ran out of memory and the trigger took too long to respond which will automatically kick out the trigger assuming it was poorly structured regex. Reloading the cog should fix this but if you're still having issues and increasing your SWAP space did not help you might look at `[p]retrigger bypass` which will allow you to disable the safe regex searching in servers you fully trust the mod team to not try and crash your bot.

 __Regex is hard, couldn't you just do a normal trigger option?__
  - I fully understand the learning curve of regex. When I started this cog I had no idea how to use regular expressions. That said I knew of its power and I hope by puting this cog out there more people can learn of its versatility. The tools are there and likely a lot easier than you might think. Play around with it and have fun!