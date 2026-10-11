# Trailer tools

Make a hook-first MEGA SNAKE trailer, with music, captions and the game's own sound effects.
Everything is Python: pygame-ce and numpy (already game dependencies) plus `ffmpeg` on your PATH.

The trailer is cut like this:

| part | what happens |
|---|---|
| **Hook** (0-6 s) | Cold open on a run that's about to go wrong. Then a freeze frame and record scratch: *"yep. that's me. you're probably wondering how I got here."* Then a VHS rewind. |
| **Title slam** | Impact and flash, and the music starts. |
| **Features** | One bar (about 1.9 s at 128 BPM) per feature, with a caption on the downbeat. |
| **Drop** | A beat-synced montage: every map, Gold Rush, Frenzy, Ghost, Rockfall, stat cards, then a fast flurry. |
| **Payoff** | Back to the hook moment. The music stops and the snake crashes: *"...that's how I got here."* |
| **End card** | Logo, platforms and the download link. |

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
python tools/trailer/record.py trailer_clips      # ~22 scripted scenes, headless, a few minutes
python tools/trailer/edit.py clips trailer_clips -o trailer.mp4
```

`record.py` runs the real game offscreen on a fixed 60 fps clock and lets a BFS bot play.
It forces the moments a trailer needs (Hunter, Blackout, Meteor Shower, Gold Rush, perks...),
records each scene's sound effects to a wav, and uses a throwaway save folder, so your real
save is never touched. Use `--only battle,hunter` to re-record just some scenes.

Files: `capture.py` (headless harness + bot), `record.py` (scenes), `music.py` (procedural
128 BPM track and stingers, built from the game's own synth voices), `footage.py` (sound
matching), `edit.py` (the cut, effects, captions and mix).
