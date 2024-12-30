import logging
from collections.abc import Generator

from disnake import DiscordException
from disnake.ext.commands import BadArgument, BucketType, MissingRequiredArgument, command, cooldown
from gacha.logging import LogBase, LogLevel
from gacha.models import VirtualItem
from gacha.models.pulls import Pull
from gacha.persistence.json import JsonEntityProvider
from gacha.persistence.json.converters import (
    ItemConverter,
    ItemRankConverter,
    ItemTypeConverter,
    PoolConverter,
)
from gacha.providers import EntityProviderInterface, SimplePullProvider
from gacha.resolvers import ItemResolverInterface
from gacha.utils.entity_provider_utils import get_item, get_item_rank, get_item_type

from arabot.core import Ara, Category, Cog, Context
from arabot.utils import bold, time_in, underline

DATABASE_FILE_PATH = "resources/database.json"
LOG_LEVEL = LogLevel.WARNING

STIGMATA_PARTS = "T", "M", "B"
STIGMATA_PARTS_FULL = tuple(f"({part})" for part in STIGMATA_PARTS)


class ItemResolver(ItemResolverInterface):
    def __init__(self, entity_provider: EntityProviderInterface, log: LogBase):
        super().__init__(entity_provider)
        self._log = log

    def resolve(self, item_id: int) -> Generator[VirtualItem]:
        item = get_item(self._entity_provider, item_id)
        if not item:
            self._log.warning(f"The configured item identified by '{item_id}' doesn't exist.")
            return
        item_type = get_item_type(self._entity_provider, item.item_type_id)
        if not item_type:
            self._log.warning(
                f"The configured item type identified by '{item.item_type_id}' doesn't exist."
            )
            return
        item_rank = get_item_rank(self._entity_provider, item.rank_id)
        if not item_rank:
            self._log.warning(
                f"The configured item rank identified by '{item.rank_id}' doesn't exist."
            )
            return
        if item_type.name == "Stigmata" and not item.name.endswith(STIGMATA_PARTS_FULL):
            item_names = [f"{item.name} ({part})" for part in STIGMATA_PARTS]
        else:
            item_names = [item.name]
        for item_name in item_names:
            yield VirtualItem(item.id, item_name)


class Gacha(Cog, category=Category.FUN):
    def __init__(self, ara: Ara):
        self.ara = ara
        self._pull_provider = Gacha._initialize_pull_provider()

    @cooldown(1, 60, BucketType.user)
    @command(aliases=["pull"], brief="Try out your luck for free", cooldown_after_parsing=True)
    async def gacha(self, ctx: Context, supply_type: str, pull_count: int = 10):
        supply_type = supply_type.casefold()
        if not self._pull_provider.has_pool(supply_type):
            await ctx.reply_("supply_not_found")
            ctx.reset_cooldown()
            return
        pulls = self._pull_provider.pull(supply_type, pull_count)
        formatted_pulls = self._format_pulls(pulls)

        supply_name = bold(self._pull_provider.get_pool_name(supply_type))
        header = underline(ctx._("supply_drops").format(supply_name) + ":\n")
        await ctx.reply(header + "\n".join(formatted_pulls))

    @gacha.error
    async def on_error(self, ctx: Context, error: DiscordException):
        last_param = ctx.command.clean_params.popitem()[1]
        match error:
            case MissingRequiredArgument():
                pools = [
                    f"{bold(pool_code)} - {self._pull_provider.get_pool_name(pool_code)}"
                    for pool_code in self._pull_provider.get_pool_codes()
                ]
                await ctx.send(ctx._("available_supplies") + ":\n" + "\n".join(pools))
                return True
            case BadArgument() if last_param.name in str(
                error
            ) and last_param.annotation.__name__ in str(error):
                if self.gacha.is_on_cooldown(ctx):
                    remaining = time_in(self.gacha.get_cooldown_retry_after(ctx))
                    await ctx.reply(ctx._("cooldown_expires", False).format(remaining))
                else:
                    await ctx.reply_("invalid_amount")
                return True
            case _:
                ctx.reset_cooldown()
                return False

    @staticmethod
    def _initialize_pull_provider() -> SimplePullProvider:
        log = logging
        entity_provider = JsonEntityProvider(
            DATABASE_FILE_PATH,
            log,
            [
                ItemConverter(),
                ItemRankConverter(),
                ItemTypeConverter(),
                PoolConverter(),
            ],
        )
        item_resolver = ItemResolver(entity_provider, log)
        return SimplePullProvider(entity_provider, item_resolver, log)

    @staticmethod
    def _format_pulls(pulls: Generator[Pull]) -> Generator[str]:
        for pull in pulls:
            formatted_pull = pull.name
            if pull.count > 1:
                formatted_pull = f"{formatted_pull} x{pull.count}"
            if pull.is_rare:
                formatted_pull = bold(formatted_pull)
            yield formatted_pull


def setup(ara: Ara):
    ara.add_cog(Gacha(ara))
