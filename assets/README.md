# Asset licenses

Copyright (C) 2026 Youssef Ahmed.

| Path | License |
| --- | --- |
| `art/` (the game-ready sprites and backgrounds) | GPL-3.0-only, the same as the code |
| `source/` (the raw sheets they are cut from) | GPL-3.0-only |
| `ART_PROMPTS.md` | GPL-3.0-only |
| `fonts/` | SIL Open Font License 1.1, see the `OFL-*.txt` files next to each font |

The full GPL text is in [`../LICENSE`](../LICENSE). Images cannot carry a header comment the way source files do, so
this file, together with the README's licensing section, is the notice for everything in `art/` and `source/`.
If you redistribute the game or its art, keep this notice with them.

**About the art:** the images were generated with ChatGPT from the prompts in `ART_PROMPTS.md`, then cleaned up and
split by `tools/prepare_art.py`. Whether, and to what extent, AI-generated images are protected by copyright
depends on the country. The license above is granted to whatever extent any rights exist.

**About the fonts:** Lilita One and Varela Round are third-party fonts. They keep their own license (the OFL), which
is compatible with shipping them inside a GPL program, but I can't relicense them. Their license texts must stay
alongside the font files.
