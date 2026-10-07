# itch.io setup and page copy

## One-time setup

1. **Create the project** at <https://itch.io/game/new>.
   - Kind of project: **Downloadable**. Classification: Games. Release status: Released.
   - Pricing: your call. "$0 or donate" suits an open-source game.
   - Tick the **Windows, macOS and Linux** boxes after the first upload (itch picks them up from the channel names).
   - The project URL slug becomes the second half of `ITCH_TARGET`, e.g. `mega-snake`.
2. **Create a butler API key** at <https://itch.io/user/settings/api-keys> ("Generate new API key").
3. **Add two things to the GitHub repo** (Settings > Secrets and variables > Actions):
   - Secret `BUTLER_API_KEY` = the key from step 2.
   - Variable `ITCH_TARGET` = `your-itch-username/your-game-slug` (for example `youssefahmed2017/mega-snake`).
4. **Dry run first.** Actions > "Publish to itch.io" > Run workflow, leave "Also publish" unticked. It builds the
   three packages and attaches them as artifacts (`itch-windows`, `itch-osx`, `itch-linux`) so you can try them
   without publishing anything. Check the itch build: it should start on the menu with no "Check for Updates".
5. **Publish.** Tag a release as usual (`git tag v3.2.0 && git push origin v3.2.0`). The GitHub release and the
   itch upload both run from that tag. Or run the workflow by hand with "Also publish" ticked.

Until `ITCH_TARGET` is set, the workflow does nothing, so it is safe to leave in the repo.

Builds are not code-signed: Windows SmartScreen and macOS Gatekeeper will warn on first launch. The package's
`README.txt` tells players how to get past that; say so on the page too (below).

## Page copy

**Title:** MEGA SNAKE

**Short description** (under 100 characters):
Snake with way too many features: chaos events, roguelite perks, gamepad and 4-player multiplayer.

**Suggested tags:** snake, arcade, roguelite, 2d, multiplayer, local-multiplayer, gamepad, open-source, singleplayer

**Genre:** Action (or Arcade, if listed)

**Description:**

> Snake, but with way too many features.
>
> Nine game modes, power-ups and downer-ups, achievements and daily quests, a coin shop with skins and trails,
> and LAN or online multiplayer for up to four players.
>
> **Modes**
> - **Classic** - wrap around the edges. Pure snake.
> - **Walls**, **Maze**, **Timed** (60-second score attack), **Battle** (two AI rivals want your food), **Coop** (local two-player)
> - **Hardcore** - no power-ups, faster, one life. Meteors, tremors and speed surges strike at random.
> - **Daily** - the same layout and chaos events for everyone, today only, with a featured event of the day.
> - **Roguelite** - walls plus rare chaos events (Food Frenzy, Gold Rush, Blackout, Mirror Mode, Hunter,
>   Earthquake) and a pick-1-of-3 perk every 8 foods.
>
> **Controls**
> Arrows, WASD or hjkl to move. P pauses. Gamepads work too: D-pad or left stick, A to confirm, Start to pause,
> with vibration. (Keyboard and mouse for menus.)
>
> **Multiplayer**
> Host or join a LAN game, or play online through a room code. The online relay is a small free server, so it
> may occasionally be slow or down.
>
> **Open source**
> MEGA SNAKE is free software under the GNU GPL v3. Source code: https://github.com/youssefahmed2017/mega-snake
>
> **Install notes**
> The builds aren't code-signed. Windows: "More info" > "Run anyway". macOS: right-click the app > Open.
> Linux: `chmod +x MegaSnake` if it won't start. Updates arrive through the itch app.

**Screenshots to take** (3 to 5; itch likes 16:9 and the cover image is 630x500): the menu, a Roguelite perk pick,
Blackout, a Hardcore meteor warning, and a multiplayer match. A short GIF of a Hunter chasing you works well as the cover.

**Devlog idea for launch day:** "What's new in 3.2" using the changelog entry.
