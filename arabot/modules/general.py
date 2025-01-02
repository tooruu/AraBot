import random
import re
from functools import partial
from types import NoneType

import disnake
from disnake.ext import commands
from disnake.utils import MISSING

from arabot.core import Ara, Category, Cog, Context
from arabot.utils import (
    CUSTOM_EMOJI_RE,
    AnyEmoji,
    AnyEmojis,
    AnyMember,
    AnyMemberOrUser,
    AnySounds,
    Twemoji,
    bold,
)

HTTP_CATS_VALID_CODES = {
    100, 101, 102,
    200, 201, 202, 203, 204, 206, 207,
    300, 301, 302, 303, 304, 305, 307, 308,
    400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416,
    417, 418, 420, 421, 422, 423, 424, 425, 426, 429, 431, 444, 450, 451, 497, 498, 499,
    500, 501, 502, 503, 504, 506, 507, 508, 509, 510, 511, 521, 523, 525, 599,
}  # fmt: skip

WEBHOOK_RESERVED_NAMES = {"everyone": "everyоne", "here": "hеrе"}


class General(Cog, category=Category.GENERAL):
    NOT_ENOUGH_OPTIONS = f"{__module__}.not_enough_options"

    def __init__(self, ara: Ara):
        self.ara = ara

    @commands.command(
        aliases=["emote", "e", "sticker"],
        brief="Show links to full-sized versions of emojis and stickers",
        usage="<emojis or stickers...>",
    )
    async def emoji(self, ctx: Context, *, emojis: AnyEmojis = None):
        if not (stickers := ctx.message.stickers) and emojis is None:
            ref_msg = await ctx.getch_reference_message()
            custom_emojis = ref_msg and [m[0] for m in CUSTOM_EMOJI_RE.finditer(ref_msg.content)]
            stickers = getattr(ref_msg, "stickers", stickers)
            if not custom_emojis and not stickers:
                await ctx.reply_("no_input")
                return
            converter = commands.PartialEmojiConverter()
            emojis = [await converter.convert(ctx, ce) for ce in custom_emojis]

        filtered_emojis = list[AnyEmoji](dict.fromkeys(e for e in emojis if e)) if emojis else []
        if not filtered_emojis and not stickers:
            await ctx.reply_("not_found", False)
            return

        await ctx.reply(
            embed=disnake.Embed(
                description="\n".join(
                    f"{item} - [{ctx._('link', False)}]({item.url}?quality=lossless&size=4096)"
                    for item in filtered_emojis + stickers
                )
            )
        )

    @commands.command(brief="Show original files of soundboard sounds", usage="<sounds...>")
    async def sound(self, ctx: Context, *, sounds: AnySounds = False):
        if sounds is False:
            await ctx.reply_("specify_sounds")
            return
        filtered_sounds: list[disnake.SoundboardSound] = (
            list(dict.fromkeys(s for s in sounds if s)) if sounds else []
        )
        if not filtered_sounds:
            await ctx.reply_("not_found", False)
            return
        await ctx.send(files=[await s.to_file(filename=f"{s.name}.ogg") for s in filtered_sounds])

    @commands.command(aliases=["r"], brief="React to a message", usage="<emojis...>")
    async def react(self, ctx: Context, *, emojis: AnyEmojis = False):
        if emojis is False:
            await ctx.reply_("specify_emojis")
            return
        emojis = [e for e in emojis if not isinstance(e, disnake.PartialEmoji | NoneType)]
        if not emojis:
            await ctx.reply_("emoji_not_found")
            return

        await ctx.message.delete()

        if not (ref_msg := await ctx.getch_reference_message()) and not (
            ref_msg := await anext(ctx.history(before=ctx.message, limit=1), None)
        ):
            return

        try:
            for emoji in emojis:
                await ref_msg.add_reaction(emoji.emoji if isinstance(emoji, Twemoji) else emoji)
        except disnake.Forbidden:
            await ctx.reply_ping_(ctx._("cant_react_to", False).format(ref_msg.author.mention))

    @commands.cooldown(1, 60, commands.BucketType.member)
    @commands.command(brief="DM user to summon them", usage="<member> [text]")
    async def summon(self, ctx: Context, member: AnyMember = False, *, text: str = ""):
        if member is False:
            ctx.reset_cooldown()
            await ctx.send_("specify_user")
            return
        if member is None:
            ctx.reset_cooldown()
            await ctx.send_("user_not_found", False)
            return
        if member.bot:
            ctx.reset_cooldown()
            await ctx.send_("cant_summon_bots")
            return
        if member not in ctx.channel.members:
            ctx.reset_cooldown()
            await ctx.send_ping(ctx._("user_no_channel_access", False).format(member.mention))
            return

        embed = disnake.Embed(
            description=ctx._("summon_message").format(
                ctx.author.mention,
                ctx.channel.mention,
                text and f"\n{bold(text)}\n",
                ctx.message.jump_url,
            )
        ).set_author(
            name=ctx.guild,
            url=await ctx.guild.get_unlimited_invite_link() or None,
            icon_url=ctx.guild.icon and ctx.guild.icon.as_icon,
        )
        try:
            await member.send(embed=embed)
        except disnake.Forbidden:
            ctx.reset_cooldown()
            await ctx.send_ping(ctx._("cant_send_to", False).format(member.mention))
        else:
            await ctx.send_ping(ctx._("summoning_user").format(member.mention))

    @commands.command(brief="Suggest server emoji", usage="<server emoji> <new emoji>", hidden=True)
    async def chemoji(self, ctx: Context, em_before: AnyEmoji, em_after: str | None = None):
        if em_before not in ctx.guild.emojis:
            await ctx.send_("choose_valid")
            return
        if em_after and ctx.message.attachments:
            await ctx.send_("one_type")
            return
        if not (em_after or ctx.message.attachments):
            await ctx.send_("include_one")
            return

        if ctx.message.attachments:
            em_after = ctx.message.attachments[0].url

        if re.fullmatch(r"https?://(-\.)?([^\s/?\.#]+\.?)+(/\S*)?", em_after):
            async with ctx.ara.session.get(em_after) as resp:
                if not (resp.ok and resp.content_type.startswith("image/")):
                    await ctx.send(ctx._("link_valid_image_to_replace").format(em_before))
                    return
        elif re.fullmatch(r"<a?:\w{2,32}:\d{18,22}>", em_after, re.ASCII):
            emoji = await commands.PartialEmojiConverter().convert(ctx, em_after)
            if emoji in ctx.guild.emojis:
                await ctx.send(ctx._("already_exists").format(em_after))
                return
            em_after = emoji.url
        else:
            await ctx.send(ctx._("choose_valid_to_replace").format(em_before))
            return

        if not ctx.message.attachments:
            await ctx.message.delete()

        message = await ctx.send(
            embed=disnake.Embed(title=ctx._("change_this"), description=ctx._("change_to_that"))
            .set_thumbnail(url=em_before.url)
            .set_image(em_after)
            .with_author(ctx.author)
        )
        await message.add_reaction("👍")
        await message.add_reaction("👎")

    @commands.command(brief="Make Ara say something", extras={"note": "Cannot ping roles"})
    async def say(self, ctx: Context, *, text: str):
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        am = disnake.AllowedMentions(users=True)
        if ref := await ctx.getch_reference_message():
            if ref.author in ctx.message.mentions:
                am.replied_user = True
            silent = disnake.MessageFlags(
                suppress_notifications=ctx.message.flags.suppress_notifications
            )
            await ref.reply(text, allowed_mentions=am, flags=silent)
        else:
            await ctx.send(text, allowed_mentions=am)

    @commands.command(name="8ball", aliases=["8b"], brief="Ask the magic 8 ball")
    async def eight_ball(self, ctx: Context):
        answer = random.choice(("yes", "no"))
        await ctx.reply(f"🎱 | {ctx._(answer, False)}")

    @commands.command(
        aliases=["pick"], brief="Make a choice for you", usage="<option 1>|<option 2>|..."
    )
    async def choose(self, ctx: Context, *, options: str):
        options = options.split("|")
        if len(options) < 2:
            await ctx.send_(General.NOT_ENOUGH_OPTIONS, False)
            return
        pick = random.choice(options).strip()
        await ctx.reply(ctx._("i_pick").format(pick))

    @commands.bot_has_permissions(add_reactions=True)
    @commands.command(
        aliases=["vote", "survey"],
        brief="Create a poll",
        usage="<topic> OR <topic>|<option 1>|<option 2>|...",
    )
    async def poll(self, ctx: Context, *, options: str):
        options = [opt.strip() for opt in options.split("|")]
        if not options:
            await ctx.send_("topic_required")
            return
        topic = options.pop(0)
        if len(options) == 1:
            await ctx.send_(General.NOT_ENOUGH_OPTIONS, False)
            return
        if len(options) > 10:
            await ctx.send_("too_many_options")
            return
        options = options or [ctx._("yes", False), ctx._("no", False)]

        await ctx.message.delete()
        indices = "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"
        body = "\n".join(f"{n} {option}" for n, option in zip(indices, options, strict=False))
        embed = disnake.Embed(title=topic, description=body).with_author(ctx.author)
        poll = await ctx.send(embed=embed)
        for i in indices[: len(options)]:
            await poll.add_reaction(i)

    @commands.command(brief="Show HTTP status code cat picture")
    async def http(self, ctx: Context, http_status_code: int):
        await ctx.send(
            f"https://http.cat/{http_status_code}"
            if http_status_code in HTTP_CATS_VALID_CODES
            else ctx._("invalid_http_code")
        )

    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.command(
        aliases=["imp"],
        brief="Pretend to be somebody else",
        extras={"note": "Cannot ping roles"},
    )
    async def impersonate(self, ctx: Context, user: AnyMemberOrUser, *, text: str):
        if user == ctx.me:
            await self.say(ctx, text=text)
            return
        if not ctx.channel.permissions_for(ctx.me).manage_webhooks:
            await ctx.send(ctx._("no_perms_to", False).format("manage webhooks"))
            return
        if not user:
            await ctx.reply_("user_not_found", False)
            return

        await ctx.message.delete()
        webhook = await self.ara.fetch_webhook("impersonate", ctx.message)

        send = partial(
            webhook.send,
            flags=disnake.MessageFlags(
                suppress_notifications=ctx.message.flags.suppress_notifications
            ),
            thread=ctx.channel if isinstance(ctx.channel, disnake.Thread) else MISSING,
        )
        await send(
            text,
            avatar_url=user.display_avatar,
            username=WEBHOOK_RESERVED_NAMES.get(user.display_name, user.display_name),
            allowed_mentions=disnake.AllowedMentions(users=True),
        )


def setup(ara: Ara):
    ara.add_cog(General(ara))
