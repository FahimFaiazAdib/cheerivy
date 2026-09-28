# CHEERIVY — Voice Bank Render Spec (for the F5-TTS agent)

**Audience:** the coding agent (Antigravity) that will render the commentary voice bank.
**Goal:** turn the script below into a folder of clean, consistently loud `.wav` clips + a `manifest.json`,
using **F5-TTS** locally on the team's Mac, cloned from **our own recorded voice**.
**Design background:** [COMMENTARY_DESIGN.md](COMMENTARY_DESIGN.md) (why the clips are split this way).

> Scope: render audio + write the render scripts. **Do not modify** `show.py`, `voice.py`, `lines.py`
> or any game code. Integration into the live show is a separate task.

---

## 0. Ground rules (read first)

1. **Voice source.** The only allowed reference audio is the files in `cheerivy_ai/show/voice_refs/`
   recorded **live on this Mac by the person whose voice it is** (a CHEERIVY team member who agreed),
   using the command in §1.2. Do **not** use any other audio file as a reference — no downloads,
   no YouTube rips, no clips of commentators or celebrities, no files "renamed" to a team member's
   name. If the refs are missing, stop and ask the team to record them.
2. **Style, not impersonation.** The lines are original and written in a dramatic, poetic
   football-commentary style. Do not add real quotes from any real commentator.
3. **Local only.** Everything runs offline after the one-time model download. No cloud TTS.
4. **Don't pollute the main Python.** The machine's `python3` is 3.13 and runs the game.
   Run F5 through `uv` with Python 3.12 in its own environment (see §2).

---

## 1. Inputs: the reference recordings

### 1.1 Four tone references

Each rendered clip is cloned from one of these, so the clip copies that recording's energy.
Same speaker for all four. 8–12 s each. Quiet room, laptop ~30 cm away, no music, no fan noise.

| File | Tone | What to read (read it **exactly**, this text is also the `ref_text`) | How to perform it |
|---|---|---|---|
| `ref_calm.wav` | calm | "Under the lights tonight, two players, one ball, and three minutes. The room settles. The story is about to begin." | Warm storyteller, but **read it in one flowing breath**: no long pauses between sentences (F5 copies the reference's pacing, including its gaps). |
| `ref_build.wav` | build | "Here it comes, down the right, still going, still going. Is there a way through? Looks up. Shapes to shoot." | Rising, faster, urgent, leaning forward. |
| `ref_erupt.wav` | erupt | "Oh, what a goal! What a goal! Absolutely magnificent! The whole place is on its feet!" | Full shout, total joy. Don't clip the mic: step back a little. |
| `ref_whisper.wav` | whisper | "Watch it again. Watch the angle. Nobody could reach that. Look at that. Just look at that." | Hushed, intimate, almost a whisper but still voiced. |

`ref_whisper.wav` is optional. If it's missing, render `whisper` clips with `ref_calm.wav` at speed 0.85.

### 1.2 How to record (the voice owner runs this themselves)

```bash
ffmpeg -f avfoundation -i ":0" -t 12 -ac 1 -ar 24000 cheerivy_ai/show/voice_refs/ref_calm.wav
```
(repeat with `ref_build.wav`, `ref_erupt.wav`, `ref_whisper.wav`)

Also create `voice_refs/ref_texts.json` with the exact words spoken in each file:
```json
{ "calm": "Under the lights tonight, ...", "build": "...", "erupt": "...", "whisper": "..." }
```

### 1.3 Checks before rendering (agent must do these)

- Each ref is mono, 24 kHz, 6–14 s long, peak below −1 dBFS (no clipping), noise floor below −50 dBFS.
- Transcribe each ref with Whisper (`mlx-whisper`, small or base model). If the transcript differs a lot
  from `ref_texts.json` (WER > 20%), **update `ref_texts.json` to what was actually said**
  (F5 garbles output when the ref text is wrong) and tell the team.
- Trim silence at the start/end of each ref to ≤ 100 ms, and shorten any silence **inside** a ref to ≤ 200 ms
  (F5 copies the reference's rhythm; gappy refs give gappy clips).
- Apply the punctuation rules of §3.1 to the ref texts too.

---

## 2. Environment

- Machine: **Apple M1, 8 GB RAM**, macOS, `uv` installed at `~/.local/bin/uv`, `ffmpeg` in `/opt/homebrew/bin`.
- **Primary engine: `f5-tts-mlx`** (MLX port, fast on Apple Silicon).
  ```bash
  uv run --python 3.12 --with f5-tts-mlx python -m f5_tts_mlx.generate --help
  ```
- **Fallback: official `f5-tts`** (PyTorch, MPS backend) if the MLX port fails:
  ```bash
  uv run --python 3.12 --with f5-tts f5-tts_infer-cli --help
  ```
- Check `--help` for the exact flag names in the installed version (ref audio, ref text, text, output,
  speed, seed, steps). Don't guess flags.
- Load the model **once** and render in a loop (a Python script importing the library), not one CLI
  process per clip — reloading the model per clip is far too slow on 8 GB.
- Close the game (camera + OpenCV) while rendering the bank; memory is tight.
- Model weights licence: CC-BY-NC — fine, this is a non-commercial university project.

---

## 3. Text rules (how to read the script tables)

| Symbol in the script | Meaning for the renderer |
|---|---|
| ` / ` | **Phrase break.** Send it as `. ` in the **same** model call. The model's natural pause is enough; it is then capped (§8 step 2). **Never** add silence. |
| ` // ` | **Sentence break.** Same as ` / ` (one model call, `. `). It only marks where a slightly longer breath is allowed (cap in §8 step 2). **Never** split the call or insert silence. |
| `[NAME]` | Not rendered here. Shows where the runtime puts a **name clip** (§5). Never send it to the model. |

- Numbers are always written as words ("thirty-two", not "32").
- "AI" is written "A I" in the text sent to TTS so it's said as two letters.
- Every call must end with `.`, `!` or `?` so the model finishes the intonation.

### 3.1 Punctuation (our model does NOT handle `:` properly)

Before any text (script lines **and** ref texts) is sent to the model, run it through one
`clean_text()` function:

| Character | Rule |
|---|---|
| `:` | **Never send.** Replace with `.` (confirmed problem with our model). |
| `;` `—` `–` | Replace with `.` (same family as `:`, not verified, so play safe). |
| `…` `...` | Replace with `.` (dots make the model pause too long). |
| `"` `“` `”` `(` `)` `[` `]` `*` `_` | Remove. |
| Repeated marks (`!!`, `?!`, `..`) | Collapse to one mark (`!`, `?`, `.`). |
| ALL CAPS words | Lower-case them (models may spell caps letter by letter). "CHEERIVY" → "Cheerivy". |
| After replacing | Collapse double spaces; make sure the next word starts with a capital after `.`. |

Keep only `.` `,` `!` `?` `'` and `-` (hyphen inside words, e.g. "thirty-two", "Ah-deeb").

**Punctuation test (do this first, before the full render).** We only know `:` is broken.
Render this test set with `ref_build` (seed 1) and have the team listen to it:

| Test ID | Text | Checks |
|---|---|---|
| pt_period | Off the wall. Still alive. | `.` baseline |
| pt_comma | Off the wall, still alive, still going. | `,` short pause |
| pt_excl | Off the wall! Still alive! | `!` energy |
| pt_quest | Is there a way through? Is there time? | `?` rising intonation |
| pt_apos | It's in! Here's the reply! | `'` contractions |
| pt_hyphen | Thirty-two kilobytes. Ah-deeb! | `-` inside words |

Record the result in `voice_bank/punctuation_test.md` (per row: OK / broken). **For every broken mark,
add it to `clean_text()` as "replace with `.`"**, the same as `:`, and re-run.
Do not start the full render until the team has confirmed this test.

---

## 4. Optimisation rules (render as little as possible)

1. **One text = one tone = one file.** Each line in §10 is rendered **only** in the tone given in its row.
   Never render the same text in several emotions. The **only** exception is name clips (§5): each name
   is rendered in 3 tones because it gets glued in front of lines of every tone.
2. **One take.** Render seed `1` only. Render seed `2` (then `3`) **only if** the clip fails QA (§8 step 6).
3. **No names inside sentences.** Lines never contain a player's name. Names are separate short clips,
   played in front of a line by the runtime. So the whole bank is rendered **once**, and a new player
   only costs 3 tiny clips.
4. **Shared lines across modes.** Every line has a `Mode` tag: `all`, `ai` (vs AI only) or `pvp`
   (player vs player only). Most lines are `all`; nothing is rendered twice for two modes.
5. **One model call per line.** Never split a line into several calls and never join parts with inserted silence (that is what made the gaps too long).
6. **Scorelines leader-first.** Only render scores with the higher number first (21 clips instead of 36).
7. **Skip what exists.** `render_bank.py` skips any clip whose `tts_text`, tone and ref file are unchanged
   (hash stored in the manifest). Changing one line re-renders one clip.

**Budget:** ~225 bank clips + 4 fallback names × 3 tones + 5 team names × 3 tones ≈ **270 renders, one take each**
(before: ~990). Expect roughly 15–30 minutes on the M1.

---

## 5. Two game modes and dynamic names

The game has two modes (already in `show.py`: `self.game = 1` vs AI, `2` = two players):

| | Mode 1: single player (vs AI) | Mode 2: player vs player |
|---|---|---|
| Names typed | player + AI name (TAB) | player 1 + player 2 |
| Name slots | `P1` = human, `AI` = the AI | `P1` = bottom joystick, `P2` = top joystick |
| Theme | human vs machine | rivals, bragging rights |
| Lines used | `all` + `ai` | `all` + `pvp` |

(For integration later: `G H` = P1 scored, `G A` = the AI / P2 scored.)

### 5.1 How names work at runtime (the dynamic solution)

Names are typed on match day, so they can't all be pre-rendered. Instead:

1. **Name clips.** Each name is 3 clips, one per tone:
   `names/<slug>/calm.wav` ("Fahim."), `names/<slug>/build.wav` ("Fahim!"), `names/<slug>/erupt.wav` ("Fahim!").
   The runtime plays the name clip whose tone matches the line after it, then the line **immediately** (0–40 ms gap, no added pause).
   Example: `names/fahim/erupt.wav` + `pay_g_04` → "Fahim! Oh, what a strike!" (back to back).
2. **Rendered while the intro plays.** When ENTER is pressed on the name screen, the show runs
   `render_name.py` in the background for every name not in the cache (3 clips per name ≈ 5–10 s on the M1).
   The kick-off opener (`kick_ai_*` / `kick_pvp_*`, 7–9 s, no names in it) plays meanwhile.
3. **Fallback names** until a name is ready (or if rendering fails). Pre-rendered in 3 tones:

   | Slug | Text | Used for |
   |---|---|---|
   | `player-one` | Player one | P1 in mode 2 |
   | `player-two` | Player two | P2 in mode 2 |
   | `the-challenger` | The challenger | P1 in mode 1 |
   | `the-machine` | The machine | the AI in mode 1 |

4. **Cached forever.** Names stay in `voice_bank/names/`, so returning players (and the leaderboard)
   are instant. Pre-render the team now:

   | Name (typed) | Say it like (sent to TTS) |
   |---|---|
   | Fahim | Fahim |
   | Adib | Ah-deeb |
   | Tahmid | Tah-mid |
   | Atik | Ah-tik |
   | CHEERIVY AI | Cheer-ivy, A I |

   If the punctuation test shows `-` is broken, spell them "Ahdeeb", "Tahmid", "Ahtik", "Cheerivy, A I".
5. **"Say it like"** is optional on the name screen; if empty, the typed name is sent as-is.

### 5.2 `render_name.py`

```bash
uv run --python 3.12 ... python render_name.py --name "Rafi" [--say-like "Rah-fee"]
```
- Renders the 3 name clips (seed 1, retry seed 2 on QA fail), same `clean_text()` and post-processing.
- Writes `voice_bank/names/<slug>/{calm,build,erupt}.wav` and adds the entry to `voice_bank/names/index.json`
  (`{"slug": ..., "name": ..., "say_like": ..., "files": {...}}`), atomically (temp file + rename).
- Prints `READY <slug>` on success, so the show knows it can switch from the fallback.
- Safe to run while the game is running: low priority (`nice`), one clip at a time.
- For names, the ASR check compares against the typed name and only flags; it never blocks.

---

## 6. Render settings per tone

| Tone | Reference | Speed | Loudness target | Used for |
|---|---|---|---|---|
| calm | ref_calm | 0.95 | −20 LUFS | storytelling, tails, colour, highlights |
| build | ref_build | 1.10 | −18 LUFS | fragments, rising tension |
| erupt | ref_erupt | 1.05 | −15 LUFS | goals, saves, big moments |
| whisper | ref_whisper (or ref_calm @ 0.85) | 0.90 | −24 LUFS | highlight slow motion only |

- **Steps:** the engine's default quality (NFE ≈ 32). Don't lower it.
- **Max duration** is in the tables. If a clip is longer, re-render with speed +0.1 (max 1.3).
  Still too long → flag it; don't cut words.

---

## 7. Output layout and format

```
cheerivy_ai/show/
  voice_refs/                 # the 4 refs + ref_texts.json  (input, recorded by the team)
  voice_bank/
    calm/  build/  erupt/  whisper/      # bank clips: <id>.wav
    names/<slug>/calm.wav build.wav erupt.wav
    names/index.json
    manifest.json
    qa_report.csv
    punctuation_test.md
  render_bank.py              # renders the bank + fallback names + team names (skips unchanged clips)
  render_name.py              # renders one new name at match time
  tighten_gaps.py             # re-applies §8 steps 1–4 to existing clips (no re-render)
```

- **Format:** WAV, PCM 16-bit, **mono, 24 000 Hz** (same as the existing Kokoro cache).
- Slug = lowercase ASCII, spaces → `-` (e.g. `cheerivy-ai`).

---

## 8. Post-processing (every clip)

1. **Trim silence:** remove leading/trailing audio quieter than −45 dBFS, keep only **10 ms** head and **30 ms** tail
   (clips are glued together at runtime, so any padding doubles up between clips).
2. **Cap internal gaps (never lengthen them):** find every silence inside the clip (below −45 dBFS, ≥ 60 ms) and
   **shorten** it to at most the tone's cap. Cut from the middle of the gap with a 10 ms crossfade so breaths don't click.

   | Tone | Max gap at ` / ` or between words | Max gap at ` // ` |
   |---|---|---|
   | build | 120 ms | 180 ms |
   | erupt | 120 ms | 180 ms |
   | calm | 180 ms | 260 ms |
   | whisper | 220 ms | 320 ms |
3. **Fades:** 5 ms fade-in, 20 ms fade-out (no clicks).
4. **Loudness:** normalise to the tone's LUFS target with true peak ≤ −1 dBTP (`ffmpeg loudnorm`, two-pass).
5. **Measure** (store in the manifest): `duration_ms`; `peak_offset_ms` = start of the loudest 50 ms RMS
   window (the highlight editor lands the loudest word on the goal frame); `lufs` after normalising.
6. **QA:** transcribe with Whisper, WER against the text (ignore case and punctuation).
   **Fail** if WER > 25%, clipping, over max duration, or any internal silence still longer than the cap after step 2.
   On fail → seed 2, then seed 3, keep the best, flag if all fail.

### 8.1 Fixing clips that were already rendered with long gaps

Don't re-render. Write `tighten_gaps.py` that runs steps 1–4 above (trim, cap gaps, fades, loudness)
on every existing clip in `voice_bank/` **in place** (keep a backup in `voice_bank/_before_tighten/`),
then re-measures `duration_ms` / `peak_offset_ms` and updates the manifest.
For lines that were rendered as **several model calls joined with silence**, only capping the gaps is
needed; re-render them as one call only if they still sound disjointed after that.
Print a before/after table: `id, old_ms, new_ms, gaps_cut`.

---

## 9. `manifest.json` schema

```json
{
  "version": 2,
  "sample_rate": 24000,
  "engine": "f5-tts-mlx <version>",
  "rendered_at": "2026-09-28T12:00:00",
  "refs": { "calm": "voice_refs/ref_calm.wav", "build": "...", "erupt": "...", "whisper": "..." },
  "clips": [
    {
      "id": "pay_g_04",
      "file": "erupt/pay_g_04.wav",
      "category": "goal_payoff",
      "mode": "all",
      "tone": "erupt",
      "name_before": "erupt",
      "text": "Oh, what a strike!",
      "tts_text": "Oh, what a strike!",
      "hash": "sha1 of tts_text + tone + ref file",
      "duration_ms": 1120,
      "peak_offset_ms": 180,
      "lufs": -15.0,
      "seed": 1,
      "asr_text": "oh what a strike",
      "wer": 0.0,
      "flags": []
    }
  ]
}
```

- `text` = the line as written in §10; `tts_text` = exactly what was sent after `clean_text()`.
- `name_before` = which name clip may be played in front of it (`calm` / `build` / `erupt` / `null` = never).
  Copy it from the `Name?` column in §10.

`qa_report.csv`: `id, file, mode, tone, duration_ms, max_duration_ms, wer, seed, flags, needs_human_listen`.
`needs_human_listen = yes` for every `erupt` clip and anything flagged.

---

## 10. The script (everything to render)

Columns: **Mode** (`all` / `ai` / `pvp`) · **Tone** (the only tone it's rendered in) ·
**Name?** (✓ = the runtime may put a `[NAME]` clip in front) · **Max** seconds.
No line contains a name, a `:`, or "he/she".

### 10.1 Kick-off
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| kick_ai_01 | ai | calm | | 9 | Under the lights of a laboratory in Palashi. / One human being. / One machine. // Sixty centimetres of destiny between them. |
| kick_ai_02 | ai | calm | | 7 | They say the machine cannot be beaten. // Tonight, someone has come to ask it a question. |
| kick_ai_03 | ai | calm | | 9 | Three minutes. / One ball. / And a question as old as invention itself. // Can we defeat what we have made? |
| kick_ai_04 | ai | calm | ✓ | 4 | Across the table. / Eight megahertz of cold intent. |
| kick_pvp_01 | pvp | calm | | 9 | Two players. / One ball. / Three minutes. // Friends before kick-off. / Rivals until the whistle. |
| kick_pvp_02 | pvp | calm | | 7 | Under the lights of a laboratory in Palashi. / Two challengers. // Only one will walk away smiling. |
| kick_pvp_03 | pvp | calm | | 6 | No machines tonight. / Just nerve, and hands, and hope. |
| kick_intro | all | calm | ✓ | 3 | Flesh, and nerve, and hope. |
| kick_versus | all | calm | | 1 | Versus. |
| kick_04 | all | build | | 3 | The whistle is close. / The lab holds its breath. |
| kick_05 | all | erupt | | 1.8 | And we are underway! |
| kick_06 | all | erupt | | 1.2 | Here we go! |

Example intro, mode 2: `kick_pvp_01` → `[P1 calm]` → `kick_versus` → `[P2 calm]` → `kick_05`.
Example intro, mode 1: `kick_ai_01` → `[P1 calm]` + `kick_intro` → `[AI calm]` + `kick_ai_04` → `kick_05`.

### 10.2 Build-ups (played the instant a shot is detected; must be short)
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| bld_01 | all | build | | 0.8 | Now then! |
| bld_02 | all | build | | 0.8 | Off the wall! |
| bld_03 | all | build | | 0.8 | Still alive! |
| bld_04 | all | build | | 1.0 | Oh, this is dangerous! |
| bld_05 | all | build | | 1.0 | Is there a way through? |
| bld_06 | all | build | | 0.8 | Here it comes! |
| bld_07 | all | build | | 0.8 | Straight at it! |
| bld_08 | all | build | | 0.8 | Oh, here we go! |
| bld_09 | all | build | | 0.8 | Look at this! |
| bld_10 | all | build | | 1.0 | Here comes the reply! |
| bld_again | all | build | ✓ | 0.6 | Again! |
| bld_ai_01 | ai | build | | 1.0 | The machine is moving! |
| bld_ai_02 | ai | build | | 1.0 | The machine strikes back! |
| bld_ai_03 | ai | build | | 0.7 | Incoming! |
| bld_pvp_01 | pvp | build | | 1.0 | Straight back at them! |

The bare name (`[NAME build]` alone) is also a build-up: "Fahim!"

### 10.3 Goal payoffs (play instantly on a goal)
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| pay_g_01 | all | erupt | ✓ | 1.5 | Oh, it's in! |
| pay_g_02 | all | erupt | | 1.5 | Goal! Goal! |
| pay_g_03 | all | erupt | ✓ | 1.2 | It's there! |
| pay_g_04 | all | erupt | ✓ | 1.8 | Oh, what a strike! |
| pay_g_05 | all | erupt | | 1.3 | Magnificent! |
| pay_g_06 | all | erupt | | 1.3 | Oh, you beauty! |
| pay_g_07 | all | erupt | | 1.8 | Through! It's through! |
| pay_g_08 | all | erupt | ✓ | 0.9 | Scores! |
| pay_gh_ai | ai | erupt | | 2.0 | The machine is beaten! |
| pay_ga_01 | ai | build | | 1.8 | And the machine scores. |
| pay_ga_02 | ai | build | | 2.5 | Oh, cruel. / Cruel mathematics. |
| pay_ga_03 | ai | erupt | | 2.2 | It's in! The machine strikes! |
| pay_ga_04 | ai | build | | 2.0 | Through, and past, and in. |

### 10.4 Goal tails (after the crowd roar fades)
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| tail_g_01 | all | calm | | 3 | Poetry, in a plywood arena. |
| tail_g_02 | all | calm | | 4 | Mark it down. / Remember where you were. |
| tail_g_03 | all | calm | | 5 | Written in the stars. / And now, in the scoresheet. |
| tail_g_04 | all | calm | | 3 | Nothing anyone could do about that. |
| tail_g_05 | all | calm | | 3.5 | Clinical. / Absolutely clinical. |
| tail_gh_ai_01 | ai | calm | | 5 | The silicon did the maths. / The human did the magic. |
| tail_gh_ai_02 | ai | calm | | 3 | Somewhere, a transistor weeps. |
| tail_gh_ai_03 | ai | build | | 3.5 | The machine calculated everything, except that! |
| tail_gh_ai_04 | ai | build | | 3.5 | For every student who ever lost to a computer! |
| tail_gh_ai_05 | ai | build | ✓ | 3.5 | Has found a flaw in the code! |
| tail_ga_01 | ai | calm | | 3.5 | Cold. / Calculated. / Clinical. |
| tail_ga_02 | ai | calm | | 4.5 | The machine does not celebrate. / It does not need to. |
| tail_ga_03 | ai | calm | | 4 | It saw that before anyone in this room had thought it. |
| tail_ga_04 | ai | calm | | 3 | Eight megahertz. / No mercy. |
| tail_ga_05 | ai | calm | | 4 | One line of code, / and one more goal. |
| tail_pvp_01 | pvp | calm | | 2.5 | Friendship is on hold. |
| tail_pvp_02 | pvp | calm | | 4 | That one will be talked about in the canteen. |
| tail_pvp_03 | pvp | calm | | 4 | Bragging rights. / And they are being collected. |
| tail_pvp_04 | pvp | build | | 3 | Whoever said this was a friendly? |

### 10.5 Saves
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| pay_sv_01 | all | erupt | | 1.0 | Denied! |
| pay_sv_02 | all | erupt | | 1.0 | Saved! |
| pay_sv_03 | all | erupt | | 1.0 | Not today! |
| pay_sv_04 | all | erupt | | 1.4 | Oh, what a stop! |
| pay_sv_05 | all | erupt | | 1.0 | Blocked! |
| tail_sv_01 | all | calm | | 3.5 | Moved before the shot was even struck. |
| tail_sv_02 | all | calm | | 2.5 | Read it all the way. |
| tail_sv_03 | all | build | | 2 | Reflexes like lightning! |
| tail_sv_ai_01 | ai | calm | | 3 | The machine stands in the doorway. |
| tail_sv_ai_02 | ai | calm | | 4 | Read like a textbook. / One it wrote itself. |
| tail_sv_ai_03 | ai | calm | | 3 | Not today, says the silicon. |

### 10.6 Near miss
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| pay_nm_01 | all | erupt | | 1.3 | Ohhh! Inches! |
| pay_nm_02 | all | erupt | | 1.2 | Oh, so close! |
| pay_nm_03 | all | erupt | | 1.8 | Wide! Agonisingly wide! |
| tail_nm_01 | all | calm | | 3.5 | It kissed the line, / and ran away. |
| tail_nm_02 | all | calm | | 4 | Mere inches. / A whole lifetime of inches. |
| tail_nm_03 | all | calm | ✓ | 2.5 | Agony. / Pure agony. |

### 10.7 Wall bounce and fast shots
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| wall_01 | all | build | | 3 | Off the wall! Geometry itself has joined the game! |
| wall_02 | all | build | | 2 | Bank shot! Pure trigonometry! |
| wall_03 | all | build | | 2 | Off the side, and still alive! |
| fast_01 | all | erupt | | 2.5 | That left the flipper like a monsoon wind! |
| fast_02 | all | build | | 2 | The camera barely believed it! |
| fast_03 | all | build | | 1 | A rocket! |
| spd_060 … spd_150 | all | build | | 2.5 | "`<N in words>` centimetres a second!" for N = 60, 70, … 150 (10 clips; e.g. spd_090 = "Ninety centimetres a second!", spd_100 = "One hundred centimetres a second!"). Slower shots are never announced. |

### 10.8 Rally, lull colour, chaos
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| rally_05 | all | build | | 3 | Five touches. / Neither will blink. |
| rally_08 | all | build | | 3 | Eight! This rally has a heartbeat of its own! |
| rally_12 | all | erupt | | 3.5 | Twelve! Twelve touches! Somebody has to break! |
| rally_gen | all | build | | 2.5 | Back, and forth, and back again. |
| col_01 | all | calm | | 4 | The ball rests. / The minds do not. |
| col_02 | all | calm | | 2 | A moment to breathe. |
| col_03 | all | calm | | 3 | The lab is quiet. / Too quiet. |
| col_04 | all | calm | | 5 | A hand on a joystick. / A heartbeat in the fingertips. |
| col_ai_01 | ai | calm | | 4 | Somewhere in that chip, a decision is being made. |
| col_ai_02 | ai | calm | | 3.5 | Thirty-two kilobytes of ambition, waiting. |
| col_pvp_01 | pvp | calm | | 3.5 | Two minds, / one ball, / no mercy. |
| lost_01 | all | build | | 3 | Where is it? / Even the camera has lost it! |
| lost_02 | all | calm | | 2.5 | The ball has gone into hiding. |
| blind_01 | ai | erupt | | 2 | The machine has lost its eyes! |
| blind_02 | ai | calm | | 3 | It plays now, on memory alone. |
| sight_01 | ai | build | | 2.5 | And the machine can see again. |
| frz_01 | all | erupt | | 2.5 | Frozen! / Not a single step! |
| frz_02 | all | build | | 1.5 | Ice in the circuits! |
| frz_03 | all | build | | 2.5 | Three seconds. / Use them! |
| frz_ai | ai | erupt | | 2.5 | The machine cannot move! |

### 10.9 Match memory callbacks
| ID | Mode | Tone | Name? | Max | Text | When |
|---|---|---|---|---|---|---|
| cb_sv3 | all | build | | 4 | Three shots. / Three times the door has held. | 3rd save in a row |
| cb_sv5 | all | build | | 4 | Five saves now. / Is anyone getting past? | 5th save in a row |
| cb_break | all | erupt | | 1.8 | And now it breaks! | goal after ≥ 3 saves in a row |
| cb_reply | all | erupt | | 3 | The reply! / Instant! / Defiant! | goal within 10 s of conceding |
| cb_again | all | build | | 3.5 | Denied from there before. / Not this time! | goal after a near miss on the same side |

### 10.10 Score situations (tails after a goal)
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| sit_open | all | build | ✓ | 1.2 | First blood! |
| sit_open_h_ai | ai | build | | 2 | First blood to humanity! |
| sit_open_a_ai | ai | calm | | 2 | The machine draws first. |
| sit_equal_01 | all | erupt | | 4 | Level! / Everything we thought we knew, is gone! |
| sit_equal_02 | all | build | | 3 | All square! / We start again! |
| sit_lead | all | erupt | ✓ | 1.5 | Into the lead! |
| sit_lead_h_ai | ai | erupt | | 2 | Humanity is in front! |
| sit_lead_a_ai | ai | build | | 2.2 | The machine edges ahead. |
| sit_extend | all | calm | | 4 | The grip tightens. / Slowly. / Surely. |
| sit_comeback | all | erupt | | 5.5 | From two behind! / This is not a match anymore. / This is a story. |
| sit_rout | all | calm | | 2.5 | This is becoming a lesson. |
| sit_rout_h_ai | ai | erupt | | 2.2 | The machine is in pieces! |

### 10.11 Scorelines (leader first)
One calm clip per score with the **higher number first** (the runtime always says the leader's score first,
and plays the leader's name before it when needed). ID `sc_<high>_<low>`, h ≥ l, 0…5 → **21 clips**,
mode `all`, tone calm, max 2 s, Name? ✓.
- 0 is "nil": `sc_1_0` = "One, nil." `sc_3_0` = "Three, nil."
- Equal scores use "all", except 0–0: `sc_2_2` = "Two all." `sc_0_0` = "Nil, nil."

### 10.12 Clock
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| clk_60 | all | build | | 3 | One minute. / Sixty heartbeats. |
| clk_30a | all | build | | 4 | Thirty seconds, / and the clock belongs to no one. |
| clk_30b | all | build | | 4.5 | Thirty seconds. / Is there time? / Is there belief? |
| cd_10 … cd_07 | all | build | | 0.8 | "Ten!", "Nine!", "Eight!", "Seven!" |
| cd_06 … cd_01 | all | erupt | | 0.8 | "Six!", "Five!", "Four!", "Three!", "Two!", "One!" |
| clk_last | all | erupt | ✓ | 3 | At the death! / At the very death! |
| clk_whistle | all | erupt | | 2 | And there is the whistle! |

### 10.13 Full time
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| ft_over | all | calm | | 1.5 | It is over. |
| ft_h_ai_01 | ai | calm | | 7 | The machine has been beaten. // Tell the engineers. / Tell the textbooks. / Tell everyone. |
| ft_h_ai_02 | ai | calm | ✓ | 2.5 | Beats the machine. |
| ft_a_ai_01 | ai | calm | | 7 | The machine prevails. / But it was made to sweat. // If silicon can sweat. |
| ft_a_ai_02 | ai | calm | | 2.5 | Victory, for the circuits. |
| ft_a_ai_03 | ai | calm | | 3.5 | A lesson. / Delivered in binary. |
| ft_win_pvp_01 | pvp | calm | ✓ | 2.5 | Champion of the lab. |
| ft_win_pvp_02 | pvp | calm | ✓ | 3 | Bragging rights, / for a very long time. |
| ft_draw_ai | ai | calm | | 7 | Level. / Human and machine walk away as equals. // Tonight, nobody is obsolete. |
| ft_draw_pvp | pvp | calm | | 5 | Level. / Two players, one scoreline, / and no loser tonight. |
| ft_clean | all | erupt | | 3 | And a clean sheet to go with it! |
| ft_first_ever | ai | erupt | ✓ | 3.5 | The first human ever to beat this machine! |
| ft_record | all | erupt | | 3 | A new name at the top of the leaderboard! |
| ft_record_spd | all | build | | 3.5 | And a new fastest shot, for the record books! |

### 10.14 Highlights (offline reel)
| ID | Mode | Tone | Name? | Max | Text |
|---|---|---|---|---|---|
| hl_open_01 | all | calm | | 3.5 | Let us remember. / Let us relive. |
| hl_open_02 | all | calm | | 4.5 | Every goal. / Every heartbeat. / One more time. |
| hl_min_1 | all | calm | | 2 | In the opening minute. |
| hl_min_2 | all | calm | | 1.5 | Minute two. |
| hl_min_3 | all | calm | | 1.5 | Minute three. |
| hl_min_last | all | calm | | 2 | With seconds to go. |
| hl_ctx_behind | all | calm | | 2.5 | Behind, and running out of time. |
| hl_ctx_level | all | calm | | 3 | All square, and everything to play for. |
| hl_ctx_ahead | all | calm | | 2.5 | In front, and hungry for more. |
| hl_ctx_blink_ai | ai | calm | | 2.5 | The machine had not yet blinked. |
| hl_turn | all | calm | | 4 | And this. / This was the moment everything changed. |
| hl_w_01 | all | whisper | | 1.5 | Watch it again. |
| hl_w_02 | all | whisper | | 3.5 | Look at the angle. / Just look at it. |
| hl_w_03 | all | whisper | | 2.5 | Slowly now. / Slowly. |
| hl_w_04 | all | whisper | | 2 | There. / Right there. |
| hl_w_05 | all | whisper | | 3 | Nobody could reach that. |
| hl_w_ai_01 | ai | whisper | | 4 | Watch the machine. / It simply cannot reach. |
| hl_tail_01 | all | calm | | 3.5 | And the laboratory will never be the same. |
| hl_tail_02 | all | calm | | 2.5 | That, is why we play. |
| aw_rocket | all | calm | | 2 | The Rocket award. |
| aw_wall | all | calm | | 1.5 | The Wall. |
| aw_marathon | all | calm | | 3.5 | The Marathon. / The longest rally of the match. |
| aw_goes | all | calm | | 1.2 | Goes to. |
| hl_close_h_ai | ai | calm | | 7 | History is written by those who dare. // Tonight, a human dared. |
| hl_close_a_ai | ai | calm | | 7 | The machine won tonight. // But it will remember this one. |
| hl_close_pvp | pvp | calm | | 7 | Two rivals. // One of them will be hearing about this for weeks. |
| hl_close_d | all | calm | | 7 | Two sides. / One scoreline. // And a story that is not finished yet. |
| hl_end | all | calm | | 2.5 | Goodnight, from Cheerivy. |

Award example: `aw_rocket` → `aw_goes` → `[NAME calm]`.
In the reel, goal payoffs reuse §10.3 and scorelines reuse §10.11.

---

## 11. Non-voice sounds (the team sources these; the agent does not generate them)

Freesound.org, **CC0 licence only**, normalised, in `cheerivy_ai/show/sfx/`:

| File | What | Length |
|---|---|---|
| crowd_bed_loop.wav | steady stadium murmur, seamless loop | 20–40 s |
| crowd_roar_1..3.wav | goal roar, big swell and decay | 3–5 s |
| crowd_ooh_1..2.wav | near-miss "ooooh" | 1.5–2.5 s |
| crowd_groan_1..2.wav | disappointed groan | 1.5–3 s |
| crowd_hush.wav | crowd going quiet (tension) | 1–2 s |
| whistle_kickoff.wav / whistle_full.wav | referee whistle, short / three blasts | 0.5–2 s |

---

## 12. Acceptance checklist

- [ ] Punctuation test (§3.1) rendered and confirmed by the team; `clean_text()` updated for every broken mark.
- [ ] No `:` (or any other broken mark) in any `tts_text`.
- [ ] Refs checked (§1.3), `ref_texts.json` matches what was actually said.
- [ ] No clip has head > 10 ms, tail > 30 ms, or an internal gap above its tone's cap (§8 step 2).
- [ ] Every ID in §10 rendered **once**, in its one tone, with `mode` and `name_before` in the manifest.
- [ ] Name clips: 4 fallbacks + 5 team names, 3 tones each, listed in `names/index.json`.
- [ ] All clips: mono, 24 kHz, 16-bit, trimmed, faded, loudness within ±1 LU of the tone target, no clipping.
- [ ] `peak_offset_ms` filled in for every clip; `qa_report.csv` written.
- [ ] Re-running `render_bank.py` with no changes renders nothing (hash skip works).
- [ ] `render_name.py --name X` finishes 3 clips and prints `READY <slug>`.
- [ ] No game files changed. No reference audio other than `voice_refs/` used.
