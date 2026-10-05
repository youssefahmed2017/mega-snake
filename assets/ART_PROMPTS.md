# MEGA SNAKE art prompts, v2: "cool and simple"

Not cartoon (no outlines, faces, gloss or bubbly shapes), not realistic (no textures, lighting or
gradients). **Minimal geometric vector**: flat matte shapes and a small dark palette with one cyan accent,
like Mini Metro, Alto's Odyssey or Monument Valley. Everything below is written around how the game
actually looks and works, so the art drops in and fits.

**Workflow:** one ChatGPT chat for the whole set → paste **1** → paste **2** → generate the images in the
order of section **4**, snake first → save them to `mega-snake/assets/source/` with the exact filenames →
run `python tools/prepare_art.py` → done. Anything you skip keeps the current art.

---

## 1. Paste this first: what the game is
> I'm making the art for MEGA SNAKE, a 2D top-down Snake game for PC. The player steers only with the
> keyboard (WASD / arrow keys), never the mouse, so never draw cursors, hands or click hints.
> The screen is dark: a charcoal-navy UI (#0D0F14) with a cyan accent (#5CC8FF), off-white text, gold coins.
> The playfield is a 32 x 22 grid of small square cells on a dark-teal checkerboard (#092F3E / #0C3E4E),
> and every sprite sits centred in one cell and is shown only about 24 pixels wide, so it must read
> instantly at that tiny size: one bold silhouette, few details. The snake is built from separate pieces
> (head, straight body segment, tail) that the game lays end to end along the grid.
> The game's menus are minimal and elegant: a letter-spaced title and thin cyan chevron ornaments
> around the selected item. The art should feel cool, calm and grown-up, not for kids.

## 2. The style block (paste at the start of EVERY prompt)
> Minimal geometric flat vector art, in the spirit of Mini Metro, Alto's Odyssey and Monument Valley.
> Simple bold silhouettes built from circles, rounded rectangles and clean angles; slightly rounded
> corners. Flat matte colour with at most two tones per shape (a base plus one slightly darker tone for a
> single clean shadow side). NO outlines, NO black lines around shapes, NO faces or big eyes, NO smiles,
> NO glossy highlights or shine dots, NO gradients, NO glow, NO textures, NO noise, NO 3D rendering, NO
> realistic lighting, NO text, NO watermark. Calm, sleek, modern, readable at 24 px.
> Palette ONLY: charcoal navy #0D0F14, deep teal #123A44, teal #1E5C66, emerald #2FA866,
> mint #6FD39A, cyan #5CC8FF, amber #FFC857, coral #E8475A, violet #8E6CF0, off-white #EEF2F7.

## 3. Keeping the set consistent (this is what stops it looking like AI slop)
- Generate the **snake first** and regenerate until you love it; it's the reference for everything else.
  Then, for each next image: *"Same style, palette and shape language as the snake image."*
- If an image drifts (outlines appear, it gets shiny or cute, or it gets detailed), reply only:
  *"Simpler. Remove outlines, shine and detail. Flat matte shapes, two tones per colour."*
  Don't add more description; that makes it worse.
- One image = one prompt. Ask for **square** images for sheets and say *"equal cells, wide equal gaps"*.

---

## 4. The prompts (in this order)

Sprite sheets go on a flat **pure magenta (#FF00FF)** background. The game cuts them out automatically,
so don't use magenta or hot pink anywhere in the art.

### `snake_sheet.png`: the snake (do this first)
"Top-down snake parts on a flat magenta background, 3 pieces in one row with wide equal gaps:
(1) the HEAD facing right: a smooth rounded-wedge shape slightly wider than the body, two small narrow
slit eyes near the front, no mouth, no face; (2) one STRAIGHT BODY SEGMENT: a horizontal capsule (rounded
rectangle about 1.6 times as long as it is tall) with a lighter belly band along its lower third;
(3) the TAIL: a capsule that tapers to a soft point on the right. Emerald green body (#2FA866), mint belly
band (#6FD39A), one darker emerald tone for the shadow side. All three pieces exactly the same thickness so
they join seamlessly when placed end to end."
*Fits the game because:* it lays these pieces end to end along the grid lines and recolours the green for
each skin (Inferno, Void, Ice, Gold), so keep it **green** and keep all three the **same thickness**.

### `food_sheet.png`: the 4 foods
"4 icons in one row on flat magenta, equal cells, each centred and the same size:
(1) a simple round coral apple with one small emerald leaf; (2) the same apple in amber with a small
four-point off-white spark beside it; (3) the same apple in cyan with a bold off-white lightning-bolt
cut-out; (4) a violet mushroom: a smooth dome cap with three off-white dots on a short off-white stem."
*In game:* normal food +10, golden +50 (rare), speed burst, shrink (bad). They must differ by **shape and
colour** at 24 px.

### `powerup_sheet.png`: the 8 power-ups
"8 round badges in a 4 x 2 grid on flat magenta, equal cells. Each badge is a flat solid circle with one
simple off-white symbol cut cleanly into it, no rim, no outline: (1) violet + ghost, (2) coral + horseshoe
magnet, (3) amber + shield, (4) cyan + hourglass, (5) emerald + 'x2', (6) light cyan + snowflake,
(7) violet + spiral, (8) coral + heart."
*Order matters:* ghost, magnet, shield, slow-mo, 2x score, freeze, teleport, revive. The game reads them
left to right, top row first.

### `hazard_sheet.png`: the 2 hazards
"2 icons side by side on flat magenta: (1) a round charcoal bomb with a short angled fuse ending in a small
amber spark; (2) a violet curse orb: a circle with six short sharp spikes and a single narrow slit eye in
the middle. Menacing but simple."
*In game:* the bomb kills you without a shield; the curse reverses your controls. They should look like
**danger** next to the friendly foods.

### `wall_tile.png`: maze walls
"One square top-down stone block filling the whole square on flat magenta with a small magenta margin:
deep teal (#123A44) with a slightly lighter bevel on the top and left edges and one short thin crack.
No outline, no texture."
*In game:* walls touch each other in long lines on the teal checker, so keep it **darker and calmer** than
the floor and plain enough to repeat.

### `decor_sheet.png`: floor details (optional)
"4 tiny floor accents in one row on flat magenta, equal cells: a small tuft of three blade-shaped leaves,
a flat round pebble pair, a single small leaf, a tiny cluster of two mushrooms. Teal and mint tones only,
very low contrast."
*In game:* a few sit in the board corners. They should almost disappear behind the snake and items.

### `tongue_sheet.png`: tongue flick animation
"A sprite sheet of ONE snake tongue animation on flat magenta, 10 equal cells in a single row, every cell
the same size. In EVERY cell the tongue's root is exactly at the LEFT-CENTRE edge and it points right.
Frames: 1 a tiny stub; 2-4 sliding out longer; 5 fully out, fork closed; 6 fork open, tip bending up;
7 fork half open, tip bending down; 8 fork open, tip bending up; 9 pulling back; 10 a tiny stub. A thin
flat coral tongue (#E8475A) with a deep fork, no outline."
*In game:* it plays in under half a second from the head's mouth in all four directions. Keep the root on
the left edge of every cell or it will jump around.

### `menu_bg.png`: main menu background (opaque, landscape 16:9)
"A minimal night landscape made of flat layered shapes: four overlapping layers of soft rolling hills
fading from teal (#1E5C66) in the back to charcoal navy (#0D0F14) in the front, a small pale off-white moon
high in the upper left, a few tiny star dots, and one long thin snake-like river curve of cyan on the
middle hill. Large calm empty space in the centre and top centre. No characters, no text."
*In game:* the title and a centred menu list sit on top, and the game blurs and darkens this image, so big
simple shapes work and small details are wasted.

### `sidebar_bg.png`: in-game side panel (opaque, tall 1:2)
"A tall flat charcoal-navy (#0D0F14) panel with a thin 3-pixel cyan (#5CC8FF) line running down the left
edge and a barely visible slightly lighter rectangle inset in the middle. Nothing else."
*In game:* the score, combo, power-up timers and controls are drawn on it as text, so it must stay
**empty and dark**.

You don't need a `title.png` (the menu uses a text title now) or a `board_bg.png` (the checkered floor is
drawn by the game in the exact teal tones above).

---

## 5. Before saving, check it fits the game
- **Size:** shrink it to a 24 px icon in your head. Can you still tell what it is? If not, ask for "simpler".
- **Colour:** colours come only from the palette. Nothing neon-pink, nothing glossy.
- **Style:** no outlines, no faces with big eyes, no shine dots. If any crept in, regenerate.
- **Sheets:** equal cells, wide gaps, nothing touching, on pure magenta.
