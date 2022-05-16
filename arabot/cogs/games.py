import asyncio
import random
import re
from collections import defaultdict, deque
from functools import partial

import disnake
from arabot.core import AnyMember, Ara, Category, Cog, Context, CustomEmoji
from disnake.ext import commands

COLUMN_EMOJI = "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"
CANCEL_EMOJI = "🚪"
BACKGROUND = "⚫"
TOKENS = "🟡", "🔴", "🟠", "🟣", "🟤", "🔵", "⚪"
LAST_COLUMN_INDICATOR = "⬇️"
FILLER = "➖"  # ⬛
BOARD_EMOJI = *COLUMN_EMOJI, CANCEL_EMOJI, BACKGROUND, LAST_COLUMN_INDICATOR, FILLER


class Connect4Engine:
    MOVE_ACCEPTED = 0
    PLAYER1_WINNER = 1
    PLAYER2_WINNER = 2
    INVALID_MOVE = 3
    WRONG_PLAYER = 4
    DRAW = 5

    def __init__(self, player1, player2):
        self._player1 = player1
        self._player2 = player2
        self._state = [0] * 6 * 7

    @property
    def _next_up(self):
        return self._player1 if self._state.count(0) % 2 == 0 else self._player2

    def _play_move(self, player, column):
        # Wrong player
        if self._next_up != player:
            return self.WRONG_PLAYER

        # Invalid column
        if not 1 <= column <= 7:
            return self.INVALID_MOVE

        # Column full
        if self._state[column - 1]:
            return self.INVALID_MOVE

        return self._apply_move(player, column)

    def _apply_move(self, player, column):
        next_empty = self._find_next_empty(column)
        self._state[next_empty] = 1 if player == self._player1 else 2
        if self._check_4_in_a_row(next_empty):
            return self.PLAYER1_WINNER if player == self._player1 else self.PLAYER2_WINNER
        return self.MOVE_ACCEPTED if 0 in self._state else self.DRAW

    def _check_4_in_a_row(self, last_added):
        target_value = self._state[last_added]

        space_right = 6 - last_added % 7
        space_left = last_added % 7
        space_down = 5 - last_added // 7
        space_up = last_added // 7
        directions = {
            +1: space_right,
            -1: space_left,
            +7: space_down,
            -7: space_up,
            +6: min(space_down, space_left),
            -6: min(space_up, space_right),
            +8: min(space_down, space_right),
            -8: min(space_up, space_left),
        }

        in_a_row = {}
        for direction, distance in directions.items():
            distance = min(distance, 3)
            current = last_added
            while distance > 0:
                current += direction
                if self._state[current] == target_value:
                    in_a_row[abs(direction)] = in_a_row.get(abs(direction), 1) + 1
                    distance -= 1
                else:
                    break
        return any(x >= 4 for x in in_a_row.values())

    def _find_next_empty(self, column):
        current = column - 1
        while current <= 34 and not self._state[current + 7]:
            current += 7
        return current


class Connect4Game(Connect4Engine):
    def __init__(
        self, player1: disnake.Member, player2: disnake.Member, p1_token: str, p2_token: str
    ):
        self.player1 = player1
        self.player2 = player2
        self.tokens = (BACKGROUND, p1_token, p2_token)
        self.last_column = None
        super().__init__(player1.id, player2.id)

    def play_move(self, player, column):
        self.last_column = column
        return self._play_move(player.id, column)

    @property
    def next_up(self):
        return self.player1 if self._next_up == self.player1.id else self.player2

    @property
    def state(self):
        return self._state

    def get_embed(self, custom_footer=False):
        title = (
            f"Connect 4: {self.player1.display_name} ({self.tokens[1]}) "
            f"VS {self.player2.display_name} ({self.tokens[2]})"
        )
        if c := self.last_column:
            content = FILLER * (c - 1) + LAST_COLUMN_INDICATOR + (FILLER * (7 - c)) + "\n"
        else:
            content = ""

        for line in range(6):
            line_state = self.state[line * 7 : (line + 1) * 7]  # noqa: E203
            content += "".join(str(self.tokens[x]) for x in line_state) + "\n"

        content += "".join(COLUMN_EMOJI)

        e = disnake.Embed(
            title=title,
            description=content,
            color=0x2ECC71,
        )
        if custom_footer:
            e.set_footer(text=custom_footer)
        else:
            token = self.tokens[1] if self.next_up == self.player1 else self.tokens[2]
            e.set_footer(text=f"Next Up: {self.next_up.display_name} ({token})")

        return e


class Connect4(Cog, category=Category.GAMES):
    def __init__(self, client):
        self.client = client
        self.waiting_games = {}
        self.active_games = {}

    async def start_invite(self, ctx: Context):
        await ctx.message.delete()
        message = await ctx.send(
            f"{ctx.author.display_name} wants to start a game of Connect 4\n"
            f"Waiting for {ctx.author.display_name} to pick a color!"
        )
        self.waiting_games[message.id] = (message, ctx.author, None)
        for emoji in TOKENS:
            await message.add_reaction(emoji)
        await message.add_reaction(CANCEL_EMOJI)

    async def p1_token_pick(self, message: disnake.Message, token):
        message, player1, _ = self.waiting_games[message.id]
        self.waiting_games[message.id] = (message, player1, token)
        await message.clear_reaction(token)
        content = message.content.split("\n")[0]
        await message.edit(f"{content} - They have chosen {token}\nPick a color to join")

    async def start_game(
        self,
        player1: disnake.Member,
        player2: disnake.Member,
        p1_token: str,
        p2_token: str,
        message: disnake.Message,
    ):
        await message.clear_reactions()
        notification = await message.channel.send(
            f"Hey {player1.mention} - {player2.display_name} has joined your game!"
        )
        await message.edit("Loading ....")
        for emoji in COLUMN_EMOJI:
            await message.add_reaction(emoji)
        await message.add_reaction(CANCEL_EMOJI)
        game = Connect4Game(player1, player2, p1_token, p2_token)
        self.active_games[message.id] = (game, message)
        await message.edit(None, embed=game.get_embed())
        await notification.delete()

    async def finish_game(self, game, message: disnake.Message, result):
        await message.clear_reactions()
        if result == game.DRAW:
            footer = "The game was a draw!!"
        elif result == game.PLAYER1_WINNER:
            footer = f"{game.player1.display_name} has won the game"
        elif result == game.PLAYER2_WINNER:
            footer = f"{game.player2.display_name} has won the game"

        await message.edit(embed=game.get_embed(custom_footer=footer))
        del self.active_games[message.id]

    async def cancel_invite(self, message: disnake.Message):
        await message.delete()
        del self.waiting_games[message.id]

    async def cancel_game(self, game, message: disnake.Message, user):
        await message.clear_reactions()
        footer = f"The game has been cancelled by {user.display_name}"
        await message.edit(embed=game.get_embed(custom_footer=footer))
        del self.active_games[message.id]

    @commands.command(aliases=["c4"], brief="Start a game of Connect 4")
    async def connect4(self, ctx: Context):
        await self.start_invite(ctx)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: disnake.Reaction, user: disnake.abc.User):
        if user.id == self.client.user.id:
            return
        if reaction.message.id in self.waiting_games:
            message, player1, p1_token = self.waiting_games[reaction.message.id]

            if user.id == player1.id:
                emoji = reaction.emoji
                if emoji == CANCEL_EMOJI:
                    await self.cancel_invite(message)
                    return
                if emoji not in BOARD_EMOJI and isinstance(emoji, str) and p1_token is None:
                    await self.p1_token_pick(message, emoji)

            elif p1_token:
                emoji = reaction.emoji
                if emoji not in BOARD_EMOJI and emoji != p1_token and isinstance(emoji, str):
                    player2 = user
                    p2_token = reaction.emoji
                    del self.waiting_games[reaction.message.id]
                    await self.start_game(player1, player2, p1_token, p2_token, message)
                    return

            await message.remove_reaction(reaction.emoji, user)

        elif reaction.message.id in self.active_games:
            game, message = self.active_games[reaction.message.id]
            if game.next_up != user or reaction.emoji not in {*COLUMN_EMOJI, CANCEL_EMOJI}:
                await message.remove_reaction(reaction.emoji, user)
                return

            if reaction.emoji == CANCEL_EMOJI:
                await self.cancel_game(game, message, user)
                return

            result = game.play_move(user, COLUMN_EMOJI.index(reaction.emoji) + 1)
            if result in {game.PLAYER1_WINNER, game.PLAYER2_WINNER, game.DRAW}:
                await self.finish_game(game, message, result)
            elif result == 0:
                await message.edit(embed=game.get_embed())

            await message.remove_reaction(reaction.emoji, user)


class TicTacToeButton(disnake.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=disnake.ButtonStyle.grey, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, inter: disnake.MessageInteraction):
        view: TicTacToe = self.view
        if view.board[self.y][self.x] is not None:
            return

        if view.current_player is None:
            if view.p1 is None:
                if inter.author == view.p2:
                    await inter.response.send_message("It's not your turn!", ephemeral=True)
                    return
                view.p1 = view.current_player = inter.author
            else:
                if inter.author == view.p1:
                    await inter.response.send_message("It's not your turn!", ephemeral=True)
                    return
                view.p2 = view.current_player = inter.author

        if view.current_player != inter.author:
            if inter.author in {view.p1, view.p2}:
                await inter.response.send_message("It's not your turn!", ephemeral=True)
            else:
                await inter.response.send_message("You are not part of this game!", ephemeral=True)
            return

        if view.current_player is view.p1:
            self.style = disnake.ButtonStyle.red
            self.label = "X"
            view.board[self.y][self.x] = view.p1
            view.current_player = view.p2
            content = f"It is now {view.p2.mention if view.p2 else 'O'}'s turn"
        else:
            self.style = disnake.ButtonStyle.green
            self.label = "O"
            view.board[self.y][self.x] = view.p2
            view.current_player = view.p1
            content = f"It is now {view.p1.mention}'s turn"
        self.disabled = True

        loser = None
        if winner := view.check_board_winner():
            if winner is True:
                content = "It's a tie!"
            else:
                content = f"{winner.mention} has won!"
                loser = view.p1 if winner is view.p2 else view.p2

            for child in view.children:
                child.disabled = True

            view.stop()

        await inter.response.edit_message(content, view=view)
        if loser:
            await inter.followup.send(f"{loser.mention} loser has been muted for 1 minute!")
            await inter.channel.temp_mute_member(loser, reason="Tic Tac Toe loser")


class TicTacToe(disnake.ui.View):
    def __init__(self, p1: disnake.abc.User, p2: disnake.abc.User):
        super().__init__()
        self.p1 = self.current_player = p1
        self.p2 = p2
        self.board = [
            [None, None, None],
            [None, None, None],
            [None, None, None],
        ]

        for x in range(3):
            for y in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_board_winner(self) -> disnake.abc.User | bool:
        # Check horizontal
        for across in self.board:
            if across[0] and len(set(across)) == 1:
                return across[0]

        # Check vertical
        for line in range(3):
            if self.board[0][line] is self.board[1][line] is self.board[2][line]:
                return self.board[0][line]

        # Check diagonal
        if (
            self.board[0][2] is self.board[1][1] is self.board[2][0]
            or self.board[0][0] is self.board[1][1] is self.board[2][2]
        ):
            return self.board[1][1]

        # Check tie
        if all(cell for row in self.board for cell in row):
            return True

        return False


class Games(Cog, category=Category.GAMES):
    def __init__(self, ara: Ara):
        self.ara = ara
        self.rr_barrel: dict[int, int] = defaultdict(lambda: [1, random.randint(1, 6)])
        self.rr_last_user: dict[int, int] = {}
        self.rr_last_deaths: dict[int, deque[int]] = defaultdict(partial(deque, maxlen=2))

    @commands.command(name="rr", brief="People get killed here, careful")
    @commands.cooldown(1, 2, commands.BucketType.guild)
    async def russian_roulette(self, ctx: Context):
        if self.rr_last_user.get(ctx.guild.id) == ctx.author.id:
            await ctx.reply("You have to pass the gun to someone else")
            return

        self.rr_last_user[ctx.guild.id] = ctx.author.id
        barrel = self.rr_barrel[ctx.guild.id]
        if barrel[0] != barrel[1]:
            barrel[0] += 1
            await ctx.reply("_\\*click*_")
            return

        del self.rr_barrel[ctx.guild.id]
        del self.rr_last_user[ctx.guild.id]
        ctx.command._buckets.update_rate_limit(ctx.message, ctx.message.created_at.timestamp() + 60)

        last_deaths = self.rr_last_deaths[ctx.guild.id]
        if last_deaths.count(ctx.author.id) < last_deaths.maxlen:
            last_deaths.append(ctx.author.id)
            await ctx.reply("***BOOM***")  # TODO: Make it look better, maybe with an emoji or a gif
            await ctx.send("Cooling down and reloading barrel...")
            await ctx.temp_channel_mute_author(reason="Russian Roulette")
            return

        # Same user loses 3 times in a row
        last_deaths.clear()
        await ctx.reply("***__KABOOM__***")
        try:
            await ctx.author.kick(reason="Russian Roulette")
        except disnake.Forbidden:
            await ctx.temp_channel_mute_author(180, reason="Russian Roulette")

    @commands.command(brief="Guess a number")
    @commands.cooldown(1, 90, commands.BucketType.channel)
    async def guess(self, ctx: Context, *ceiling):
        # Initializing
        try:
            ceiling = max(abs(int(ceiling[-1])), 2)
        except (ValueError, IndexError):
            ceiling = 20
        number = random.randint(1, ceiling)
        await ctx.send(f"🎲 Guess a number between 1-{ceiling}")

        # Voting phase
        guesses = {}

        def is_valid_guess(vote):
            if vote.channel == ctx.channel and vote.author not in guesses:
                try:
                    return (
                        int(vote.content) not in guesses.values()
                        and 1 <= int(vote.content) <= ceiling
                    )
                except ValueError:
                    return False
            return False

        async def voting():
            while True:
                vote = await ctx.ara.wait_for("message", check=is_valid_guess)
                try:
                    await vote.add_reaction("☑️")
                except disnake.Forbidden:
                    pass
                guess = int(vote.content)
                guesses[vote.author] = guess
                if guess == number:
                    return True

        try:
            exact_guess = await asyncio.wait_for(voting(), timeout=20)
        except asyncio.TimeoutError:
            exact_guess = False

        # Winner phase
        if not exact_guess and len(guesses) < 2:
            ctx.reset_cooldown()
            await ctx.send("No one has won")
            return
        winner = min(guesses, key=lambda m: abs(guesses[m] - number))
        await ctx.send(
            f"{winner.mention} "
            + ("guessed" if exact_guess else "was the closest to")
            + f" number {number}\n"
            f"Enjoy your 1 minute mute! {CustomEmoji.TeriCelebrate}"
        )
        await ctx.channel.temp_mute_member(winner, reason="Guessed the number")

    @commands.check(
        lambda msg: (vc := getattr(msg.author.voice, "channel", None))
        and [m.bot for m in vc.members].count(False) > 2  # pylint: disable=used-before-assignment
    )
    @commands.command(aliases=["impostor", "impasta"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    async def imposter(self, ctx: Context):
        vote_timeout = 20

        # Initializing
        vc = ctx.author.voice.channel
        await ctx.send(CustomEmoji.KonoDioDa)
        await ctx.send(
            f"You have {vote_timeout} seconds to find the imposter!\n"
            "*Ping the person you think the imposter is to vote*"
        )

        # Voting phase
        voted: list[disnake.abc.User] = []
        votes: dict[disnake.abc.User, int] = defaultdict(int)

        def is_valid_vote(vote):
            return (
                vote.author not in voted
                and vote.mentions
                and re.fullmatch(r"<@!?\d{15,21}>", vote.content)
                and vote.channel == ctx.channel
                and vote.author in vc.members
                and vote.mentions[0] in vc.members
                and not vote.mentions[0].bot
            )

        async def voting():
            while True:
                vote = await ctx.ara.wait_for("message", check=is_valid_vote)
                await vote.delete()
                mentioned = vote.mentions[0]
                # Punish who voted for a streamer
                if mentioned.voice.self_stream:
                    mentioned = vote.author
                votes[mentioned] += 1
                voted.append(vote.author)

        try:
            await asyncio.wait_for(voting(), timeout=vote_timeout)
        except asyncio.TimeoutError:
            pass

        # Ejection phase
        if (
            len(voted) < 2
            or not (imposter := max(votes, key=lambda m: votes[m]))
            or imposter not in vc.members
            # Check if only one person has the highest amount of votes
            or list(votes.values()).count(votes[imposter]) != 1
        ):
            await ctx.send("No one was ejected")
            return
        await imposter.move_to(None, reason="Imposter")
        await ctx.send(f"{imposter.mention} was ejected")

    @commands.command(brief="Start a game of Tic-Tac-Toe")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def ttt(self, ctx: Context, *, opponent: AnyMember = False):
        if opponent is None:
            ctx.reset_cooldown()
            await ctx.reply("User not found")
            return
        if ctx.author == opponent:
            ctx.reset_cooldown()
            await ctx.reply("Can't play against yourself")
            return
        if opponent and opponent.bot:
            ctx.reset_cooldown()
            await ctx.reply("Can't play against bots")
            return
        players = [ctx.author, opponent or None]
        random.shuffle(players)
        first = players[0]
        await ctx.send(
            f"Tic Tac Toe: {getattr(first, 'mention', 'X')} goes first", view=TicTacToe(*players)
        )


def setup(ara: Ara):
    ara.add_cog(Connect4(ara))
    ara.add_cog(Games(ara))
