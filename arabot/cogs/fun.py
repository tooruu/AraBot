from io import BytesIO
from random import choice
from urllib.parse import quote

import disnake
from aiohttp import ClientResponseError, ClientSession
from arabot.core import AnyMember, Ara, Category, Cog, Context, CustomEmoji
from disnake.ext import commands


class Fun(Cog, category=Category.FUN):
    def __init__(self, session: ClientSession):
        self.session = session

    @commands.command(brief="Get a random inspirational quote")
    async def inspire(self, ctx: Context):
        async with self.session.get("https://inspirobot.me/api?generate=true") as r:
            image_link = await r.text()
        await ctx.send(image_link)

    @commands.command(aliases=["person"], brief="Get a randomly generated face")
    async def face(self, ctx: Context):
        async with self.session.get("https://thispersondoesnotexist.com/image") as r:
            image = BytesIO(await r.read())
            await ctx.send(file=disnake.File(image, "face.png"))

    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.command(brief="Who asked?", hidden=True)
    async def wa(self, ctx: Context, msg: disnake.Message = None):
        await ctx.message.delete()
        if not msg:
            async for msg in ctx.history(limit=3):
                if msg.webhook_id or not msg.author.bot:
                    break
            else:
                return
        for i in "🇼", "🇭", "🇴", "🇦", "🇸", "🇰", "🇪", "🇩", CustomEmoji.FukaWhy:
            await msg.add_reaction(i)

    @commands.message_command(name="Who asked?")
    async def whoasked(self, inter: disnake.ApplicationCommandInteraction, msg: disnake.Message):
        await inter.response.send_message("Adding reactions", ephemeral=True)
        try:
            for i in "🇼", "🇭", "🇴", "🇦", "🇸", "🇰", "🇪", "🇩", CustomEmoji.FukaWhy:
                await msg.add_reaction(i)
        except disnake.Forbidden:
            await (await inter.original_message()).edit("I don't have permission to add reactions")
        else:
            await (await inter.original_message()).edit("Reactions added")

    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.command(brief="Who cares?", hidden=True)
    async def wc(self, ctx: Context, msg: disnake.Message = None):
        await ctx.message.delete()
        if not msg:
            async for msg in ctx.history(limit=3):
                if msg.webhook_id or not msg.author.bot:
                    break
            else:
                return
        for i in "🇼", "🇭", "🇴", "🇨", "🇦", "🇷", "🇪", "🇸", CustomEmoji.TooruWeary:
            await msg.add_reaction(i)

    @commands.message_command(name="Who cares?")
    async def whocares(self, inter: disnake.ApplicationCommandInteraction, msg: disnake.Message):
        await inter.response.send_message("Adding reactions", ephemeral=True)
        try:
            for i in "🇼", "🇭", "🇴", "🇨", "🇦", "🇷", "🇪", "🇸", CustomEmoji.TooruWeary:
                await msg.add_reaction(i)
        except disnake.Forbidden:
            await (await inter.original_message()).edit("I don't have permission to add reactions")
        else:
            await (await inter.original_message()).edit("Reactions added")

    @commands.cooldown(3, 90, commands.BucketType.guild)
    @commands.command(aliases=["whom", "whose", "who's", "whos"], brief="Pings random person")
    async def who(self, ctx: Context):
        member = choice(ctx.channel.members)
        user_profile = disnake.Embed().set_author(
            name=member.display_name,
            icon_url=member.avatar.compat.icon.url,
            url=f"https://discord.com/users/{member.id}",
        )
        await ctx.reply(embed=user_profile)

    @commands.command(aliases=["gp"], brief="Secretly ping a person", hidden=True)
    async def ghostping(self, ctx: Context, target: AnyMember, *, msg):
        await ctx.message.delete()
        if not target:
            return
        invis_bug = "||\u200b||" * 198 + "_ _"
        if len(message := msg + invis_bug + target.mention) <= 2000:
            await ctx.send_mention(message)

    @commands.command(name="8ball", aliases=["8b"], brief="Ask the magic 8 ball")
    async def eight_ball(self, ctx: Context, *, question=" "):
        try:
            url = "https://8ball.delegator.com/magic/JSON/" + quote(question, safe="")
            json = await self.session.fetch_json(url)
            answer = json["magic"]["answer"]
        except ClientResponseError:
            answer = choice(("Yes", "No"))
        await ctx.reply(f"🎱 | {answer}")

    @commands.command(aliases=["ren"], brief="Rename a person", cooldown_after_parsing=True)
    @commands.cooldown(1, 60 * 60 * 24 * 3.5, commands.BucketType.member)
    async def rename(self, ctx: Context, target: AnyMember, *, nick: str | None = None):
        if not target:
            ctx.reset_cooldown()
            await ctx.send("User not found")
            return
        if target == ctx.author:
            ctx.reset_cooldown()
            await ctx.send("Cannot rename yourself")
            return

        # Get highest role that has at least one permission to exclude dummy roles e.g. colors
        get_top_role = lambda r: r.permissions.value != 0
        author_role = next(filter(get_top_role, reversed(ctx.author.roles)), ctx.guild.default_role)
        target_role = next(filter(get_top_role, reversed(target.roles)), ctx.guild.default_role)

        if author_role < target_role:
            ctx.reset_cooldown()
            await ctx.send("Cannot rename users ranked higher than you")
            return
        if nick and len(nick) > 32:
            ctx.reset_cooldown()
            await ctx.send("Nickname too long")
            return

        try:
            await target.edit(nick=nick)
        except disnake.Forbidden:
            ctx.reset_cooldown()
            await ctx.send("I don't have permission to rename this user")
            return

        await ctx.tick()


def setup(ara: Ara):
    ara.add_cog(Fun(ara.session))
