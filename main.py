import discord
import random
import copy
from typing import TypeAlias
from enum import Enum

PROD = True

if not PROD:
	with open("test_data") as f:
		TEST_GUILD = int(f.readline())
		TEST_UID = int(f.readline())
		TEST_UNAME = f.readline()

NUMS = 5
COLS = 5
HINTS = 8
STRIKES = 3
HISTORY = 5
NUMS_EMOTES = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
COLS_EMOTES = ["⬜","🟦","🟥","🟩","🟨"]
CARD_EMOTES = ["🇦","🇧","🇨","🇩","🇪"]
HINT_EMOTES = ["▫️","🔸"]
HIDDEN_EMOTE = "⬛"
BULB_EMOTE = ":bulb:"
TEST_PARAMS = {} if PROD else {"guild_ids":[TEST_GUILD], "guild_only":True}
HINT_TYPES = [
	['⬜ white', '🟦 blue', '🟥 red', '🟩 green', '🟨 yellow', '[1] one', '[2] two', '[3] three', '[4] four', '[5] five'],
	[(i,-1) for i in range(COLS)] + [(-1,i) for i in range(NUMS)]
]

NO_GAME_MSG = "There isn't a game going on now. Start one with `/hanabi`?"
NOT_THREAD_MSG = "This command must be executed in a game thread!"
WRONG_THREAD_MSG = "This thread isn't for a current game!"
NOT_PLAYING_MSG = "You aren't currently in the game!"
NOT_TURN_MSG = "It isn't your turn right now!"

CARD_CHOICE_OPTION = discord.Option(int,choices=[discord.OptionChoice(f"[{chr(ord('A')+i)}]",i) for i in range(len(CARD_EMOTES))])

card:TypeAlias = tuple[int,int] #col, num
h_card:TypeAlias = tuple[card,list[bool,bool]]

def get_hand_size(players:int): return 4 if players>3 else 5
def show_card(c:card): return COLS_EMOTES[c[0]]+NUMS_EMOTES[c[1]]
def show_hand(h:list[h_card]) -> str:
	c_str = "   ".join([CARD_EMOTES[i]+show_card(h[i][0]) for i in range(len(h))])
	h_str = "   ".join([BULB_EMOTE+HINT_EMOTES[c[1][0]]+HINT_EMOTES[c[1][1]] for c in h])
	return c_str+"\n"+h_str
def show_own_hand(h:list[h_card])->str:
	return "   ".join([CARD_EMOTES[i]+(COLS_EMOTES[h[i][0][0]] if h[i][1][0] else HINT_EMOTES[0])+(NUMS_EMOTES[h[i][0][1]] if h[i][1][1] else HINT_EMOTES[0]) for i in range(len(h))])#-1,-1,-1)])
async def update_activity(): await bot.change_presence(activity=discord.Activity(name=f"/hanabi in {len(all_games)} channel{'' if len(all_games)==1 else 's'}",type=discord.ActivityType.playing))

class Game_State(Enum):
	WAITING=0
	ONGOING=1
	OVER=2

class board_state:
	def __init__(self,p_count:int):
		self.locked=True
		self.p_count=p_count
		self.deck=[(i,max(0,(j-1)//2)) for i in range(COLS) for j in range(NUMS*2)]
		random.shuffle(self.deck)
		self.stacks:list[int]=[0 for i in range(COLS)]
		self.discard:list[list[int]]=[[] for i in range(COLS)]
		self.overtime=0
		self.hints=HINTS
		self.strikes=0
		self.turn=-1
		self.hands:list[list[h_card]]=[[] for i in range(p_count)]
		self.deal()

	def deal(self):
		d = True
		hs = get_hand_size(self.p_count)
		while d and len(self.deck):
			d=False
			for h in self.hands:
				if hs>len(h) and len(self.deck):
					h.append(self.draw())
					d=True

	def draw(self):
		if not len(self.deck): return None
		c = self.deck.pop()
		return (c,[False,False])
	
	def get_card(self,p_id:int,c_id:int) -> card:
		return self.hands[p_id][c_id][0]

	def comp_card(self,c:card):
		return 0 if self.stacks[c[0]]==c[1] else -1 if self.stacks[c[0]]<c[1] else 1
	
	def pop_card(self,p_id:int,c_id:int) -> card:
		c = self.hands[p_id].pop(c_id)[0]
		nc = self.draw()
		if nc: self.hands[p_id].append(nc)
		return c
	
	def add_to_discard(self,c:card):
		self.discard[c[0]].append(c[1])
		self.discard[c[0]].sort()

class game:
	def __init__(self,channel:discord.TextChannel):
		self.channel = channel
		self.threads:list[discord.Thread] = None
		self.players:list[list[tuple[int,str]]] = []
		self.state:board_state = None
		self.history:list[board_state] = [] #last 3?? moves
		self.intro_msg:discord.Message = None
		self.board_msg:discord.Message = None
		self.all_players_msg:discord.Message = None
		self.player_msgs:list[discord.Message] = None
		self.hand_msgs:list[discord.Message] = None
		self.active = True

	async def begin(self):
		if self.state: return
		self.state = board_state(len(self.players))
		self.player_msgs:list[discord.Message] = [None for i in self.players]
		self.hand_msgs:list[discord.Message] = [None for i in self.players]
		self.threads = []
		for i in range(len(self.players)):
			p = self.players[i]
			t = await self.channel.create_thread(name=f"{p[0][1]}'s POV",auto_archive_duration=60,type=discord.ChannelType.private_thread)
			for p in self.players[i]: await t.add_user(await bot.fetch_user(p[0]))
			self.threads.append(t)
		await self.next()
		
	def get_hinted(self,t_id:int,h_id:int):
		s:board_state = self.state
		c_or_n:bool = h_id>=COLS
		t_hand = s.hands[t_id]
		return [i for i in range(len(t_hand)) if t_hand[i][0][c_or_n]==HINT_TYPES[1][h_id][c_or_n]]

	async def move_hint(self,p_id:int,t_id:int,h_id:int):
		s:board_state = self.state
		if not s.hints: return
		c_or_n:bool = h_id>=COLS
		t_hand = s.hands[t_id]
		marked = self.get_hinted(t_id,h_id)
		if not len(marked): return False
		for i in marked:
			t_hand[i][1][c_or_n]=1
		s.hints-=1
		one = len(marked)==1
		await self.threads[t_id].send(f"**{self.players[p_id][0][1]}** hinted card{'' if one else 's'} {', '.join([CARD_EMOTES[x] for x in marked])} to you as **{HINT_TYPES[0][h_id]}**!")
		await self.channel.send(f"Card{'' if one else 's'} {', '.join([CARD_EMOTES[x] for x in marked])} of **{self.players[t_id][0][1]}** {'was' if one else 'were'} **hinted** as **{HINT_TYPES[0][h_id]}** by **{self.players[p_id][0][1]}**! *(-1 hint, {s.hints} left)*")
		await self.next()

	async def move_discard(self,p_id:int,c_id:int):
		s = self.state
		c = s.pop_card(p_id,c_id)
		s.add_to_discard(c)
		s.hints+=1
		await self.channel.send(f"Card {CARD_EMOTES[c_id]}: {show_card(c)} was **discarded** by **{self.players[p_id][0][1]}**! *(+1 hint, {s.hints} left)*")
		await self.next()

	async def move_play(self,p_id:int,c_id:int):
		s = self.state
		c = s.pop_card(p_id,c_id)
		cc = s.comp_card(c)
		await self.channel.send(f"Card {CARD_EMOTES[c_id]}: {show_card(c)} was **played** by **{self.players[p_id][0][1]}**!")
		if cc==0:
			s.stacks[c[0]]+=1
			if s.stacks[c[0]]==NUMS:
				s.hints+=1
				await self.channel.send(f"**Colour {HINT_TYPES[0][c[0]]} completed!** :fireworks: *(+1 hint, {s.hints} left)*")
				if min(s.stacks)==NUMS: 
					await self.channel.send("**You win!** 🌺🔥🎆")
					await self.end()
		else:
			if cc<0: await self.channel.send(f"**Invalid card!** Card {show_card((c[0],c[1]-1))} has not been played!")
			else: await self.channel.send(f"**Invalid card!** Card {show_card(c)} has already been played!")
			await self.strike()
			s.discard[c[0]].append(c[1])
			s.discard[c[0]].sort()
		await self.next()

	async def strike(self):
		self.state.strikes+=1
		await self.channel.send(f"**Strike {self.state.strikes}/3!** :bomb:")
		if self.state.strikes==STRIKES:
			await self.channel.send(":boom:")
			await self.end()

	def intro_str(self) -> str:
		return f"**hanabi** 🌺🔥🎆\nCurrently **{len(self.players)}** player{'' if len(self.players)==1 else 's'} (2-5) registered!\n"+"`/role join` to join, and `/game begin` to start.\n\n**Players:**\n"+'\n'.join([
			f"{i+1}. **"+self.players[i][0][1]+"**"+(" *(spectated by "+', '.join(["**"+q[1]+"**" for q in self.players[i][1:]])+")*" if len(self.players[i])>1 else '') for i in range(len(self.players))
		])
	
	async def update_intro(self) -> str:
		try: await self.intro_msg.edit(self.intro_str())
		except: self.intro_msg = await self.channel.send(self.intro_str())

	def show_board(self) -> str:
		s = self.state
		if not s: return None
		return "\n".join([(COLS_EMOTES[i]*(s.stacks[i]))+(NUMS_EMOTES[s.stacks[i]-1]) for i in range(COLS) if s.stacks[i]])
	
	def show_discard(self) -> str:
		s = self.state
		if not s: return None
		return "\n".join([COLS_EMOTES[i]+"".join(NUMS_EMOTES[j] for j in s.discard[i]) for i in range(COLS) if len(s.discard[i])])
	
	def hand_str(self, p_id:int) -> str:
		if not self.state: return None
		return "**Hands** (in play order):\n"+"\n".join([f"**{self.players[j][0][1]}**'s hand:\n"+show_hand(self.state.hands[j]) for j in range(p_id-len(self.players)+1,p_id)])+f"\n**Your ({self.players[p_id][0][1]}'s) hand**:\n"+show_own_hand(self.state.hands[p_id])+f"\nNote: letters may change. Cards will **move towards** {CARD_EMOTES[0]}. New cards will **enter from** {CARD_EMOTES[get_hand_size(self.state.p_count)-1]}."
	
	def all_hands_str(self) -> str:
		if not self.state: return None
		return "**Final hands:**\n"+"\n".join([f"**{self.players[j][0][1]}**'s hand:\n"+show_hand(self.state.hands[j]) for j in range(len(self.players))])
	
	def all_players_str(self):
		return f"**Players:**\n"+'\n'.join([
			f"{i+1}. **"+self.players[i][0][1]+"**"+(" *(spectated by "+', '.join(["**"+q[1]+"**" for q in self.players[i][1:]])+")*" if len(self.players[i])>1 else '') for i in range(len(self.players))
		])+"\nOpen your respective thread (**split-view** recommended) to see hands and play.\n`/role spectate` to spectate someone."

	def player_str(self, p_id:int) -> str:
		return f"**hanabi** 🌺🔥🎆 (from **{self.players[p_id][0][1]}**'s POV)\nPlayer: <@!{self.players[p_id][0][0]}>\nSpectators: {(', '.join(f'<@!{self.players[p_id][i][0]}>' for i in range(1,len(self.players[p_id]))))}\nWhen it's your turn, you'll get pinged. Then `/turn hint`, `/turn play` or `/turn discard`!\n***Tip:** On desktop, you can open the thread in **split-view**! Click the **three dots** in the top-right corner beside the searchbar, and select **Open in split view**.*"

	def board_str(self) -> str:
		if not self.state: return None
		return "**Board:**\n"+self.show_board()+f"\n**{self.state.hints}** hint{'' if self.state.hints==1 else 's'} left / **{self.state.strikes}/{STRIKES}** strikes / **{len(self.state.deck)}** card{'' if len(self.state.deck)==1 else 's'} left in deck{f' *(**{self.state.p_count-self.state.overtime+1}/{self.state.p_count}** moves left)*' if self.state.overtime else ''} / **{self.players[self.state.turn][0][1]}**'s turn\n\n**Discard pile:**\n"+self.show_discard()

	async def next(self):
		s = self.state
		if not s: return
		s.turn+=1
		s.turn%=s.p_count
		if not len(s.deck): 
			if not s.overtime: await self.channel.send(f"**Out of cards!** Each player can take one more turn.")
			s.overtime+=1
		if s.overtime>s.p_count: 
			await self.channel.send("All players have taken their last turn.")
			return await self.end()
		self.history.append(copy.deepcopy(s))
		if len(self.history)>HISTORY+1: self.history.pop(0)
		await self.end_turn()

	async def undo(self, p_id:int):
		if len(self.history)<2: return
		self.history.pop()
		s = self.state = copy.deepcopy(self.history[-1])
		random.shuffle(s.deck)
		await self.channel.send(f"**{self.players[p_id][0][1]}** has **undone the last move!** (and reshuffled the deck) *({len(self.history)-1} left in undo stack)*")
		await self.end_turn()
	
	async def end_turn(self):
		s = self.state
		s.locked = False
		for i in range(len(self.players)):
			t = self.threads[i]
			try: await self.player_msgs[i].edit(self.player_str(i))
			except: self.player_msgs[i]=await t.send(self.player_str(i))
			try: await self.hand_msgs[i].edit(self.hand_str(i))
			except: self.hand_msgs[i]=await t.send(self.hand_str(i))
		try: await self.board_msg.edit(self.board_str())
		except: self.board_msg=await self.channel.send(self.board_str())
		try: await self.all_players_msg.edit(self.all_players_str())
		except: self.all_players_msg=await self.channel.send(self.all_players_str())
		await self.threads[s.turn].send(f"It's your turn, <@!{self.players[s.turn][0][0]}>!")
		
	async def end(self):
		all_games.pop(self.channel.id)
		if self.state:
			await self.channel.send(f"**Game ended!** Thank you for playing :)\nScore: **{sum(self.state.stacks)}/25**")
			self.board_msg=await self.channel.send(self.board_str())
			await self.channel.send(self.all_hands_str())
			if self.threads: 
				for i in range(len(self.players)):
					t = self.threads[i]
					await t.send(f"**Game over!** Thanks for playing, **{self.players[i][0][1]}**.")
					self.hand_msgs[i]=await t.send(self.hand_str(i))
					for p in self.players:
						for u in p: await t.add_user(await bot.fetch_user(u[0]))
					await t.archive(locked=True)
		self.state = None
		await update_activity()

all_games:dict[int,game] = {}
bot = discord.Bot()

@bot.slash_command(description="Create a new game of Hanabi! 🌺🔥🎆", **TEST_PARAMS)
async def hanabi(ctx:discord.ApplicationContext):
	if ctx.channel_id in all_games: return await ctx.respond("There's already an ongoing game!", ephemeral=True)
	g = game(ctx.channel)
	all_games[ctx.channel_id] = g
	g.players = [] if PROD else [[(TEST_UID,TEST_UNAME)],[(TEST_UID,TEST_UNAME),(TEST_UID,TEST_UNAME)]]
	g.intro_msg = await ctx.send(g.intro_str())
	await ctx.respond("Starting a new game!")
	await update_activity()

main = bot.create_group(name="game",description="Core game flow commands!")

@main.command(description="Begin the game!",**TEST_PARAMS)
async def begin(ctx:discord.ApplicationContext):
	try: g = all_games[ctx.channel_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if g.state: return await ctx.respond("The game's already in progress!", ephemeral=True)
	if len(g.players)<2: return await ctx.respond("You need at least 2 players! (haha lonely)", ephemeral=True)
	if len(g.players)>5: return await ctx.respond("Not sure how you got here, but you can't have >5 players.", ephemeral=True)
	await ctx.respond(f"**Beginning** the game with **{len(g.players)} players!**")
	await g.begin()

@main.command(description="End the game.",**TEST_PARAMS)
async def end(ctx:discord.ApplicationContext):#, nuke:discord.Option(bool,description="nuke the threads")=False):
	try: g = all_games[ctx.channel.parent_id]
	except: 
		try: g = all_games[ctx.channel_id] 
		except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	await ctx.respond("Ending the game.")
	await g.end()

@main.command(description="Undo last move.",**TEST_PARAMS)
async def undo(ctx:discord.ApplicationContext):
	try: g = all_games[ctx.channel.parent_id]
	except: 
		try: g = all_games[ctx.channel_id] 
		except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if not g.state: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	u = (ctx.author.id,ctx.author.display_name)
	if not u[0] in [p[0][0] for p in g.players]: await ctx.respond(NOT_PLAYING_MSG, ephemeral=True)
	u_id = [p[0][0] for p in g.players].index(u[0])
	if len(g.history)<2: return await ctx.respond("You're out of undo history!", ephemeral=True)
	if g.state.locked: return await ctx.respond("The game's still processing the last move!", ephemeral=True)
	await ctx.respond("You undid the last move!")
	await g.undo(u_id)

show = bot.create_group("show", "Commands relating to showing game info.")
@show.command(description="Show the board again. (in main channel)",**TEST_PARAMS)
async def board(ctx:discord.ApplicationCommand):
	try: g = all_games[ctx.channel_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if not g.state: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	await ctx.respond("Showing board…")
	g.board_msg=await g.channel.send(g.board_str())

@show.command(description="Show the hands again. (in thread)",**TEST_PARAMS)
async def hands(ctx:discord.ApplicationCommand):
	try: ctx.channel.parent_id
	except: return await ctx.respond(NOT_THREAD_MSG, ephemeral=True)
	try: g = all_games[ctx.channel.parent_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if not g.state: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	try: s = g.threads.index(ctx.channel)
	except: return await ctx.respond(WRONG_THREAD_MSG, ephemeral=True)
	await ctx.respond("Showing hands…")
	g.hand_msgs[s]=await g.threads[s].send(g.hand_str(s))

@show.command(description="Show the players and spectators again. (in channel or thread)",**TEST_PARAMS)
async def players(ctx:discord.ApplicationCommand):
	try: ctx.channel.parent_id
	except: 
		try: g = all_games[ctx.channel_id] 
		except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
		await ctx.respond("Showing all players…")
		g.all_players_msg=await g.channel.send(g.all_players_str())
	try: g = all_games[ctx.channel.parent_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	try: s = g.threads.index(ctx.channel)
	except: return await ctx.respond(WRONG_THREAD_MSG, ephemeral=True)
	await ctx.respond("Showing players in channel…")
	g.player_msgs[s]=await g.threads[s].send(g.player_str(s))

player = bot.create_group("role", "Commands related to joining and leaving.")
@player.command(description="Join the game. (Only possible before game start, or if spectated player leaves.)",**TEST_PARAMS)
async def join(ctx:discord.ApplicationContext):
	try: g = all_games[ctx.channel_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	u = (ctx.author.id,ctx.author.display_name)
	if g.state: 
		return await ctx.respond("We're in the middle of a game. `/role spectate @player` to spectate someone!", ephemeral=True)
	else:
		if u[0] in [p[0][0] for p in g.players]: return await ctx.respond("You're already in the game!", ephemeral=True)
		if len(g.players)>5: return await ctx.respond(f"Sorry, we're maxed out. `/role spectate @player` to spectate someone!", ephemeral=True)
		for p in g.players: 
			l = [x[0] for x in p]
			if u[0] in l: p.pop(l.index(u[0]))
		g.players.append([u])
		await ctx.respond(f"**{u[1]}** has joined the game!")
		await g.update_intro()

@player.command(description="Leave the game. (Someone must be spectating you.)",**TEST_PARAMS)
async def leave(ctx:discord.ApplicationContext):
	try: g = all_games[ctx.channel.parent_id]
	except: 
		try: g = all_games[ctx.channel_id] 
		except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	u = (ctx.author.id,ctx.author.display_name)
	if not u[0] in [q[0] for p in g.players for q in p]: await ctx.respond(NOT_PLAYING_MSG, ephemeral=True)
	p_id, n = [(i,j) for i in range(len(g.players)) for j in range(len(g.players[i])) if g.players[i][j][0]==u[0]][0]
	p:list[tuple[int,str]] = g.players[p_id]
	if not g.state or n or len(p)>1: 
		p.pop(n)
		await ctx.respond(f"**{u[1]}** has left the game. Goodbye!")
		if g.state: await g.threads[p_id].remove_user(await bot.fetch_user(u[0]))
		await g.update_intro()
	else: await ctx.respond(f"You're the only one here! Ask someone to spectate and replace you with `/role spectate`, or `/hanabi end` to end the game for everyone.", ephemeral=True)

@player.command(description="Spectate a specific player.",**TEST_PARAMS)
async def spectate(ctx:discord.ApplicationContext, player:discord.Option(discord.Member)):
	try: g = all_games[ctx.channel.parent_id]
	except: 
		try: g = all_games[ctx.channel_id] 
		except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	u = (ctx.author.id,ctx.author.display_name)
	if u[0] in [p[0][0] for p in g.players]:
		if g.state: return await ctx.respond(f"You're already playing!", ephemeral=True)
		else: g.players.pop([p[0][0] for p in g.players].index(u[0]))
	if player.id not in [q[0] for p in g.players for q in p]:
		return await ctx.respond(f"{player.display_name} isn't in the game!", ephemeral=True)
	p_id, n = [(i,j) for i in range(len(g.players)) for j in range(len(g.players[i])) if g.players[i][j][0]==player.id][0]
	for i in range(len(g.players)): 
		l = [x[0] for x in g.players[i]]
		if u[0] in l: 
			g.players[i].pop(l.index(u[0]))
			if g.state: await g.threads[i].remove_user(await bot.fetch_user(u[0]))
	g.players[p_id].append(u)
	await ctx.respond(f"**{u[1]}** is now spectating {player.display_name}!")
	if g.state: await g.threads[p_id].add_user(await bot.fetch_user(u[0]))
	await g.update_intro()


move = bot.create_group(name="turn",description="Commands related to taking your turn.")

@move.command(description="Give another player a hint.",**TEST_PARAMS)
async def hint(ctx:discord.ApplicationContext, player:discord.Option(discord.Member), hint:discord.Option(choices=HINT_TYPES[0])):
	try: ctx.channel.parent_id
	except: return await ctx.respond(NOT_THREAD_MSG, ephemeral=True)
	try: g = all_games[ctx.channel.parent_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if not g.state: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if g.state.locked: return await ctx.respond(NOT_TURN_MSG, ephemeral=True)
	try: s = g.threads.index(ctx.channel)
	except: return await ctx.respond(WRONG_THREAD_MSG, ephemeral=True)
	u, v = (ctx.author.id,ctx.author.display_name), (player.id,player.display_name)
	if u[0] != g.players[s][0][0]: return await ctx.respond(NOT_PLAYING_MSG, ephemeral=True)
	if s!=g.state.turn: return await ctx.respond(NOT_TURN_MSG, ephemeral=True)
	try: t = [g.players[i][0][0] if i!=s else 0 for i in range(len(g.players))].index(v[0])
	except: return await ctx.respond(f"**{v[1]}** isn't playing!", ephemeral=True)
	if s==t: return await ctx.respond(f"You can't hint yourself!", ephemeral=True)
	if not g.state.hints: return await ctx.respond(f"There aren't any hint tokens left! :(", ephemeral=True)
	h = HINT_TYPES[0].index(hint)
	marked = g.get_hinted(t,h)
	if not len(marked): return await ctx.respond(f"You have to hint at least one card.", ephemeral=True)
	g.state.locked=True
	await ctx.respond(f"You **hinted {v[1]}**'s card{'' if len(marked)==1 else 's'} {', '.join([CARD_EMOTES[x] for x in marked])} as **{HINT_TYPES[0][h]}**!")
	await g.move_hint(s,t,h)

@move.command(description="Discard a card of your choice.",**TEST_PARAMS)
async def discard(ctx:discord.ApplicationContext, c_id:CARD_CHOICE_OPTION):
	try: ctx.channel.parent_id
	except: return await ctx.respond(NOT_THREAD_MSG, ephemeral=True)
	try: g = all_games[ctx.channel.parent_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if not g.state: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if g.state.locked: return await ctx.respond(NOT_TURN_MSG, ephemeral=True)
	try: s = g.threads.index(ctx.channel)
	except: return await ctx.respond(WRONG_THREAD_MSG, ephemeral=True)
	u = (ctx.author.id,ctx.author.display_name)
	if u[0] != g.players[s][0][0]: return await ctx.respond(NOT_PLAYING_MSG, ephemeral=True)
	if s!=g.state.turn: return await ctx.respond(NOT_TURN_MSG, ephemeral=True)
	if g.state.hints>=HINTS: return await ctx.respond(f"The number of hint tokens is already maximum!", ephemeral=True)
	try: c = g.state.get_card(s,c_id)
	except: return await ctx.respond(f"You don't have that card!", ephemeral=True)
	g.state.locked=True
	await ctx.respond(f"You **discarded** card {CARD_EMOTES[c_id]}: **{show_card(c)}**!")
	await g.move_discard(s,c_id)

@move.command(description="Play a card of your choice,",**TEST_PARAMS)
async def play(ctx:discord.ApplicationContext, c_id:CARD_CHOICE_OPTION):
	try: ctx.channel.parent_id
	except: return await ctx.respond(NOT_THREAD_MSG, ephemeral=True)
	try: g = all_games[ctx.channel.parent_id] 
	except: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if not g.state: return await ctx.respond(NO_GAME_MSG, ephemeral=True)
	if g.state.locked: return await ctx.respond(NOT_TURN_MSG, ephemeral=True)
	try: s = g.threads.index(ctx.channel)
	except: return await ctx.respond(WRONG_THREAD_MSG, ephemeral=True)
	u = (ctx.author.id,ctx.author.display_name)
	if u[0] not in [x[0] for x in g.players[s]]: return await ctx.respond(NOT_PLAYING_MSG, ephemeral=True)
	if s!=g.state.turn: return await ctx.respond(NOT_TURN_MSG, ephemeral=True)
	try: c = g.state.get_card(s,c_id)
	except: return await ctx.respond(f"You don't have that card!", ephemeral=True)
	bad = g.state.comp_card(c)
	g.state.locked=True
	await ctx.respond(f"You **{'mis' if bad else ''}played** card {CARD_EMOTES[c_id]}: **{show_card(c)}**{'. :boom:' if bad else '!'}")
	await g.move_play(s,c_id)

if not PROD:
	dev = bot.create_group(name="dev",description="Development commands.",**TEST_PARAMS)
	@dev.command(description="nuke",**TEST_PARAMS)
	async def nuke(ctx:discord.ApplicationContext):
		for t in ctx.channel.threads: await t.delete()
		await ctx.respond("All threads in channel deleted!", ephemeral=True)

@bot.event
async def on_ready():
	await update_activity()
	print("Logged in as "+bot.user.name+"#"+bot.user.discriminator)

with open("token") as f:
	token = f.read()
bot.run(token)