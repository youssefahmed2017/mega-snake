# 🐍 Mega Snake Game!
<div align="center">

<table>
  <tr>
    <td colspan="2"><img src="https://github.com/user-attachments/assets/d27c2b40-d6b7-4105-b5ca-9ffd6a1d62b7" width="100%"></td>
  </tr>
  <tr>
    <td><img src="https://github.com/user-attachments/assets/99325c16-65b8-4188-a2b9-b846dcec77a7" width="100%"></td>
    <td><img src="https://github.com/user-attachments/assets/99153622-d791-4d2c-880d-acf272efa99a" width="100%"></td>
  </tr>
  <tr>
    <td><img src="https://github.com/user-attachments/assets/58b1ad77-d978-4265-a6cc-5a6498a2d789" width="100%"></td>
    <td><img src="https://github.com/user-attachments/assets/9088d858-3806-409b-bd71-65cc1adf7867" width="100%"></td>
  </tr>
</table>

</div>


Snake, but with way too many features: nine game modes, power-ups and downer-ups, chaos events, a roguelite
perk mode, achievements and quests, gamepad support, and LAN or online multiplayer for up to four players.

- **Play:** download the latest build for Windows, macOS or Linux from the
  [Releases page](https://github.com/youssefahmed2017/mega-snake/releases). The game updates itself from there.
- **Website:** https://mega-snake-game.vercel.app

## Game modes

| Mode | What it is |
| --- | --- |
| Classic | Wrap around the edges. Pure snake. |
| Walls | The edges kill you. |
| Maze | Walls, plus obstacles that grow over time. |
| Battle | Walls, plus two AI rivals that want your food. |
| Timed | 60-second score attack. |
| Hardcore | No power-ups, faster, one life. Meteors, tremors and speed surges strike at random. |
| Coop | Local two-player on a shared board. |
| Daily | The same layout and chaos events for everyone, today only. |
| Roguelite | Walls plus chaos events, and a pick-1-of-3 perk every 8 foods. |

Multiplayer (LAN, or online through a small relay server) supports up to four players. The host runs the game;
everyone else sends inputs and draws what the host sends back.

## Controls

| | Keyboard | Gamepad |
| --- | --- | --- |
| Move | Arrows, WASD or hjkl | D-pad or left stick |
| Confirm (menus) | Enter | A |
| Phase Dash (Roguelite perk) | Space | A |
| Back | Esc | B |
| Pause | P | Start |
| Quit to menu from Pause | Esc | Select |
| Settings tabs | Tab | LB / RB |

Other keys: M mutes, T opens chat in multiplayer, F11 toggles fullscreen.

## Run from source

```bash
pip install -r requirements.txt   # pygame-ce, numpy, certifi, websockets
python main.py
```

The online relay (a Cloudflare Worker) lives in `server/`; see `CLAUDE.md` for the development notes.

## Support

MEGA SNAKE is free. If you enjoy it and want to chip in, you can do that on Ko-fi:
https://ko-fi.com/youssefahmedabdou. Totally optional, and thank you.

## License

MEGA SNAKE is free software, licensed under the **GNU General Public License v3.0 only**. The full text is in
[`LICENSE`](LICENSE) and every source file carries a copyright and `SPDX-License-Identifier` header.

In short: you may use, study, change and share it. If you distribute it, including a modified or renamed
version, you must release the complete source under the same license and keep the copyright and license notices.

- **Code:** GPL-3.0-only.
- **Art** (`assets/art/`, `assets/source/`) and the art prompts: GPL-3.0-only, the same as the code.
  See [`assets/README.md`](assets/README.md).
- **Fonts** ([Lilita One](assets/fonts/OFL-LilitaOne.txt) and [Varela Round](assets/fonts/OFL-VarelaRound.txt)):
  not mine to relicense, so they stay under the SIL Open Font License 1.1.

Copyright (C) 2026 Youssef Ahmed.
