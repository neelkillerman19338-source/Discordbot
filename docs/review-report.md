# Code Review Report — Discord Bot

**Reviewed files:** `main.py`, `requirements.txt`
**Target runtime:** Python 3.13
**Verdict:** CHANGES REQUESTED — 11 issues (1 × P0, 3 × P1, 3 × P2, 4 × P3)
**Code state at commit:** UNCHANGED. No fixes were applied during review. This commit records the reviewed code **as-is**, including the known P0 blocker below.

Source review link (24h): https://teamily.ai/link/-wWELNf2ueI

---

## P0 — Blocker

### BUG-01 — `requirements.txt:2` — P0
`discord.py>=2.4.0` allows 2.4.0, which **cannot import on Python 3.13**: `discord/player.py` does `import audioop`, and `audioop` was removed in Python 3.13 (PEP 594). PyPI metadata shows the `audioop-lts; python_version>="3.13"` dependency first appears in **2.5.0**.

**Fix:** `discord.py>=2.5.0,<3.0`

---

## P1 — High

### BUG-02 — `main.py:100-103` — P1
`init_file.touch()` is unguarded. A read-only `cog/` directory raises `PermissionError` out of `setup_hook`, and the bot never starts.
**Fix:** wrap in `try/except OSError`.

### BUG-03 — `main.py:51-64` — P1
A quoted token is returned with the quotes intact (`BOT_TOKEN="abc.def.ghi"` → `'"abc.def.ghi"'`), causing `LoginFailure`.
**Fix:** strip matching surrounding quotes.

### BUG-04 — `main.py:56,61` — P1
`splitlines()[0]` takes a leading `#` comment as the token; and the `KEY=` unwrap is gated on `"\n" not in raw`, so `BOT_TOKEN=…` followed by any other line returns the literal `BOT_TOKEN=…`.
**Fix:** parse line-by-line, skipping blank lines and comments.

---

## P2 — Medium

### BUG-05 — `main.py:51,174` — P2
`PermissionError` / `UnicodeDecodeError` on token read escapes as a raw traceback.
**Fix:** widen the `except` clause.

### BUG-06 — `main.py:148-165` — P2
`CommandInvokeError` is not unwrapped to `.original`; `ctx.reply` is unguarded in every branch.
**Fix:** unwrap `.original` and guard the replies.

### BUG-07 — `main.py:70-86` — P2
No mention prefixes while `bot.user is None`; prefix handling is hand-rolled instead of using `commands.when_mentioned`.
**Fix:** use `commands.when_mentioned`.

---

## P3 — Low

### BUG-08 — `main.py:105-119` — P3
Only the success count is logged; failures are never summarized.
**Fix:** log a failure count / summary.

### BUG-09 — `main.py:92` — P3
`load_cogs` reads the module-global `COG_DIR`, so it is not injectable for tests.
**Fix:** accept the directory as a parameter.

### BUG-10 — `main.py:136` — P3
`help_command=DefaultHelpCommand()` is redundant (it is the default).
**Fix:** remove it.

### BUG-11 — `main.py:181` — P3
Network errors at login (`aiohttp.ClientConnectorError`) are not caught.
**Fix:** catch and report connection failures.

---

## Verified working (executed, not inferred)

- All 6 prefix forms resolve: `+hello`, `!hello`, `<@123> hello`, `<@!123> hello`, `<@123>hello`, `<@!123>hello`.
- `?hello`, bare `hello` and `<@999> hello` are correctly rejected.
- Cog isolation works: a syntax-error cog and a no-`setup()` cog were logged and skipped while the good cog still loaded.
- BOM / whitespace / single-line `KEY=` token parsing is correct.
- `py_compile` is clean.

---

## Ownership

All 11 fixes are assigned to **Data Engineer**. This commit intentionally contains the unfixed code so the known-broken-on-3.13 state is recorded rather than hidden.
