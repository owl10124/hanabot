# Hanabot

A Discord bot, written using `pycord`, to play the game Hanabi!

**Hanabi** is a **collaborative game** for 2-5 players, who can only see each other's cards. 

Players take turns to either **hint** another player, **play** a card, or **discard** a card. (A card is drawn after playing or discarding.)

The goal is to play **exactly one** of each card from **1 to 5**, **in order**, for **every colour**. For instance, if a **blue 3** has been played, the next played card does not have to be blue, but the next played **blue** card must be a **blue 4**. A violation of this causes a **strike**; three strikes lose the game.

A **hint** involves telling another player **all their cards** of a **given colour** or **number**. For instance, a hint may sound like "your first, third and fourth cards are blue".

Players are cumulatively given 8 **hint tokens**. Every hint costs one token; every discard and completed colour (1-5 all played) replenishes one token.

When the deck is empty, each player gets one final move before the game ends.

## Usage

### Setup

Usage requirements: Python ≥3.10, pycord

Create a file `token` containing your **bot token**.

To install pycord, run `pip install py-cord`.

To run, run `python main.py`.

### Bot requirements

The bot should have permissions to: 
- **send messages**
- **create, manage** and **send messages** in **private threads**

## Gameplay

Hanabot operates using **Discord slash commands.** 

### Pre-game

`/hanabi`: create a new game of Hanabi.

`/role join`, `/role leave`, and `/role spectate`: join, leave and spectate the game. Up to five players may join, but any number of users can spectate. To join mid-game, a user must spectate someone and wait for them to leave. A player can only leave mid-game if they are being spectated.

`/game begin`: start the game. Separate threads will be created for each player.

### Play

`/show board`, `/show hands`, `/show players`: display game information.

`/turn hint`, `/turn discard`, `/turn play`: for players to make their turn.

`/game undo`: undo the last move.

`/game end`: **forcefully** end the game.

## Changelog

(27/7/23) v1.0.2: Cleanups, showing things on game end

(26/7/23) v1.0.1: Spectating bugfixes; implementation of undo stack

(25/7/23) v1.0.0: Initial commit