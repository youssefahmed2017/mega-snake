# Trailer tools

Make a hook-first MEGA SNAKE trailer, with music, captions and the game's own sound effects.
Everything is Python: pygame-ce and numpy (already game dependencies) plus `ffmpeg` on your PATH.

`edit.py clips` (bot footage) cuts a ~2 minute trailer with every feature in it:

| part | what happens |
|---|---|
| **Cold open** | 4 bars of pure chaos on a drop (meteors, the Hunter, Blackout, Gold Rush, quakes at once) under *"POV: you just wanted to play Snake"*. |
| **Hard stop** | Record scratch, silence, a lonely 3-cell snake: *"it started as just snake." / "then I kept adding stuff."* |
| **Title slam** | Impact and flash, and the music starts. |
| **Acts** | The basics, 9 modes, chaos events + hazards, roguelite perks, 8 maps, multiplayer (a real 4-player LAN match), unlocks, then the details. Each act gets its own music section and a chapter tag. |
| **Finale** | A drop montage that ends on a crash. The music cuts out: *"GG."* |
| **End card** | Logo, platforms and the download link. |

`edit.py footage` (your own recording) makes a shorter 50 s cut: a freeze-frame hook on your last death, a rewind, a title slam, your best moments on the beat, and the payoff.

## 1. From your own OBS recording

```bash
python tools/trailer/edit.py footage "C:/Videos/2026-10-11 my run.mkv" -o trailer.mp4
python tools/trailer/edit.py footage my_run.mkv -o short.mp4 --vertical   # 9:16 for Shorts/TikTok/Reels
```

`footage.py` finds the good bits by *listening*. The game's sound effects are synthesized,
so it rebuilds each one and finds it in your recording's audio: deaths, golden apples, combos,
power-ups, achievements, meteors, near misses. The last death becomes the hook. Only the game
audio is needed (OBS "Desktop Audio"; a muted mic is fine).

If the auto-pick isn't what you want, pass the times yourself:

```bash
python tools/trailer/edit.py footage my_run.mkv --death 4:31.5 --moments 0:42,1:10,1:55,2:30
```

Add `--preview` for a fast, low-quality render while you try things out.

## 2. From fresh footage recorded by a bot

```bash
python tools/trailer/record.py trailer_clips      # ~75 scripted scenes, headless, ~25 minutes
python tools/trailer/edit.py clips trailer_clips -o trailer.mp4
```

`record.py` runs the real game offscreen on a fixed 60 fps clock and lets a BFS bot play.
It forces the moments a trailer needs (Hunter, Blackout, Meteor Shower, Gold Rush, perks...),
records each scene's sound effects to a wav, and uses a throwaway save folder, so your real
save is never touched. Use `--only battle,hunter` to re-record just some scenes.

`live.py ROOMCODE` joins a real online room as up to 3 bot guests and films what they see.

Files: `capture.py` (headless harness), `capture_bot.py` (the bot), `record.py` (scenes), `music.py` (procedural
128 BPM track and stingers, built from the game's own synth voices), `footage.py` (sound
matching), `edit.py` (the cut, effects, captions and mix).
