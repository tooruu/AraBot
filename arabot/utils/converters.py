from __future__ import annotations

import re
from collections.abc import Callable
from string import whitespace
from types import UnionType

import disnake
from aiohttp import ClientSession
from disnake.ext import commands
from disnake.utils import find

from .regexes import CUSTOM_EMOJI_RE

__all__ = [
    "AnyChl",
    "AnyEmoji",
    "AnyEmojis",
    "AnyGuild",
    "AnyMember",
    "AnyMemberOrUser",
    "AnyRole",
    "AnyTChl",
    "AnyUser",
    "AnyVChl",
    "CIEmoji",
    "CIGuild",
    "CIMember",
    "CIRole",
    "CITextChl",
    "CIVoiceChl",
    "clean_content",
    "Codeblocks",
    "Empty",
    "Twemoji",
]

type AnyMember = disnake.Member | CIMember | Empty
type AnyUser = disnake.User | UserFromCIMember | Empty
type AnyMemberOrUser = disnake.Member | CIMember | disnake.User | Empty
type AnyEmoji = disnake.Emoji | CIEmoji | disnake.PartialEmoji | Twemoji | Empty
type AnyTChl = disnake.TextChannel | CITextChl | Empty
type AnyVChl = disnake.VoiceChannel | CIVoiceChl | Empty
type AnyChl = AnyTChl | AnyVChl | Empty
type AnyRole = disnake.Role | CIRole | Empty
type AnyGuild = disnake.Guild | CIGuild | Empty


arg_ci_re_search = lambda arg: re.compile(re.escape(arg), re.IGNORECASE).search


class clean_content(commands.clean_content):  # noqa: N801
    def __init__(self, fix_emojis: bool = True, **kwargs: bool):
        self.fix_emojis = fix_emojis
        super().__init__(**kwargs)

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        argument = await super().convert(ctx, argument)
        return CUSTOM_EMOJI_RE.sub(r"\g<name>", argument) if self.fix_emojis else argument


class Twemoji(commands.Converter):
    base_url = "https://twemoji.maxcdn.com/v/latest/72x72/{}.png"

    def __init__(self, emoji: str):
        self.emoji = emoji
        self.codepoint = "-".join(f"{ord(char):x}" for char in emoji)
        self.url = self.base_url.format(self.codepoint)
        self.name = self.codepoint

    def __str__(self) -> str:
        return self.emoji

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Twemoji:
        emoji = cls(argument)
        if await emoji.read(ctx.bot.session, ensure_only=True):
            return emoji
        raise commands.EmojiNotFound(argument)

    async def read(self, session: ClientSession, *, ensure_only: bool = False) -> bytes | bool:
        async with session.get(self.url) as resp:
            if resp.ok:
                return True if ensure_only else await resp.read()
            return False


class CIMember(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.Member:
        member_search = arg_ci_re_search(argument)
        if found := find(
            lambda member: member_search(member.display_name), ctx.guild.members
        ) or find(lambda member: member_search(member.name), ctx.guild.members):
            return found
        raise commands.MemberNotFound(argument)


class UserFromCIMember(CIMember):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.User:
        try:
            member = await super().convert(ctx, argument)
        except commands.MemberNotFound:
            raise commands.UserNotFound(argument) from None
        return member._user


class CIEmoji(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.Emoji:
        emoji_search = arg_ci_re_search(argument)
        guilds = ctx.bot.guilds
        guilds.insert(0, guilds.pop(guilds.index(ctx.guild)))  # Move ctx.guild to the beginning
        for guild in guilds:
            if emoji := find(lambda emoji: emoji_search(emoji.name), guild.emojis):
                return emoji
        raise commands.EmojiNotFound(argument)


class CITextChl(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.TextChannel:
        t_channel_search = arg_ci_re_search(argument)
        if found := find(lambda channel: t_channel_search(channel.name), ctx.guild.text_channels):
            return found
        raise commands.ChannelNotFound(argument)


class CIVoiceChl(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.VoiceChannel:
        v_channel_search = arg_ci_re_search(argument)
        if found := find(lambda channel: v_channel_search(channel.name), ctx.guild.voice_channels):
            return found
        raise commands.ChannelNotFound(argument)


class CIRole(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.Role:
        role_search = arg_ci_re_search(argument)
        if found := find(lambda role: role_search(role.name), ctx.guild.roles):
            return found
        raise commands.RoleNotFound(argument)


class Empty(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> None:
        return None


class Codeblocks(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> list[tuple[str, str]]:
        blocks: list[str] = re.findall(
            r"```(?:([+\w-]+)\n+|\n*)(.*?)\n*```|`(.*?)`", argument, re.DOTALL
        )
        return [
            (lang, (codeblock or inlineblock).strip(whitespace))
            for lang, codeblock, inlineblock in blocks
        ]


class CIGuild(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> disnake.Guild:
        guild_search = arg_ci_re_search(argument)
        if found := find(lambda guild: guild_search(guild.name), ctx.bot.guilds):
            return found
        raise commands.GuildNotFound(argument)


async def convert_union[T, T2: str](
    ctx: commands.Context, argument: T2, union: UnionType
) -> T | None:
    converters: tuple[
        type[T | commands.Converter[T]] | commands.Converter[T] | Callable[[T2], T], ...
    ] = union.__args__
    parameter = ctx.current_parameter
    for converter in converters:
        try:
            return await commands.converter._actual_conversion(ctx, converter, argument, parameter)
        except commands.CommandError:
            pass
    return None


class AnyEmojis(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> list[AnyEmoji]:
        argument = argument.replace("<", " <").replace(">", "> ")
        argument = re.sub(r"(?<!<a)(?<!<):(?!\d{17,20}>)", " ", argument, flags=re.ASCII)
        return [await convert_union(ctx, arg, AnyEmoji) for arg in argument.split()]
