from discord.ext import commands
from discord.ext.commands import Cog
from discord.ext.commands.errors import (
	CommandOnCooldown, MissingPermissions, CheckFailure, BadArgument, MissingRequiredArgument, ExpectedClosingQuoteError
)
from ._utils import setPresence

class Listeners(Cog):
	def __init__(self, client):
		self.bot = client

	@Cog.listener()
	async def on_ready(self):
		await setPresence(self.bot, 3, "#lewd")
		print("Ready!")

	@Cog.listener()
	async def on_command_error(self, ctx, error):
		if isinstance(error, CommandOnCooldown):
			await ctx.send(f"Cooldown expires in {error.retry_after:.0f} seconds")
			return
		if isinstance(error, MissingPermissions):
			await ctx.send("Missing permissions")
			return
		if hasattr(ctx.command, "on_error") or isinstance(
			error,
			( # Ignore following errors
			commands.CommandNotFound,
			CheckFailure,
			BadArgument,
			MissingRequiredArgument,
			ExpectedClosingQuoteError
			)
		):
			return
		raise error

def setup(client):
	client.add_cog(Listeners(client))