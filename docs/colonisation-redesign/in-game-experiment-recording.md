# Recording an in-game colonisation experiment

Status: 2026-10-21. Manual journal import only. No scheduler, no automation, no
canonical promotion, and no research export (the research export stays paused
by the owner's 2026-10-21 decision).

This page explains, step by step, how to run an in-game test such as:

> Dock at a station and note its economy mix and services. Build a facility in
> the system. Come back later, dock again, and see what changed.

ED-Finder keeps the evidence for the **station side** of that test today. It
does **not** yet keep the colonisation events themselves (see
[What is not kept yet](#what-is-not-kept-yet)).

## What ED-Finder keeps from your journal

Each time you dock, the game writes a `Docked` line to your journal. When you
import that journal, ED-Finder keeps these facts about the station, and nothing
about you:

- the time you docked;
- system name and system address;
- station name, station type and market ID (the station's permanent number);
- economy mix: each economy and its share (for example Extraction 60 %,
  Industrial 40 %);
- the list of station services (for example `dock`, `commodities`, `shipyard`);
- government, allegiance and distance from the arrival star.

Since 2026-10-21 **every docking is kept**, even at the same station. Before
that change, a second docking at the same station was thrown away as a
duplicate, so a before/after could not be read back. Dockings imported before
this change are not lost, but only the first docking per station was stored
for them.

## Step by step

### 1. Before the test: dock and import

1. In the game, dock at the station you want to watch.
2. Stay docked for a few seconds, then leave the game or keep playing (the line
   is already written).
3. Import your journal (step 4 below).

### 2. Do the in-game change

Build the facility, deliver to the construction site, or do whatever the test
is about. Write down, on paper or in a note, what you did and when, because the
colonisation events are not kept yet.

### 3. After the test: dock again and import

1. Come back later (after the facility is finished, or after the weekly tick if
   that is what you are testing).
2. Dock at the **same** station again.
3. Import your journal again (step 4 below). Re-importing a file you already
   imported is safe: lines already stored are skipped, new lines are added.

### 4. How to import your journal

Your journal files are on the Windows PC that runs Elite Dangerous.

The command below is **(a) a command to run in PowerShell on the Windows PC
that runs the game**. It lists your five newest journal files, newest first,
so you know which ones to pick:

```powershell
Get-ChildItem "$env:USERPROFILE\Saved Games\Frontier Developments\Elite Dangerous\Journal.*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
```

Then, in a web browser on any computer:

1. Open the ED-Finder **Account** page and sign in.
2. In **Commanders and journals**, use **Verify with Frontier** if your
   commander is not verified yet. Only verified imports keep every docking.
3. Click **Select journal logs** and pick the journal file(s) that cover the
   time you docked. They are in the folder named in the command above.
4. Leave the sharing checkbox as you normally have it (it does not affect what
   is kept for you).
5. Click **Import journals** and wait for "Import finished".

### 5. Read the before/after

There is no page for this yet (a later change will add one). For now, read it
straight from the API in the same browser where you are signed in.

The text below is **(c) reference text: a web address to paste into the
browser's address bar** while signed in to ED-Finder. It lists your stations,
the most recently docked first, each with its dockings oldest first:

```text
https://ed-finder.app/api/v1/journal/station-observations
```

To look at one station only, add its market ID (shown as `market_id` in the
list above). This is also **(c) reference text: a web address to paste into
the browser's address bar**; replace `3700000001` with your station's
`market_id`:

```text
https://ed-finder.app/api/v1/journal/station-observations?market_id=3700000001
```

This address only works once the production site runs a release that includes
this change.

How to read the answer:

- `observations` is the list of dockings, **oldest first**. The first entry is
  your "before", the last entry is your "after".
- `economies` lists each economy and its `proportion` (0.6 means 60 %).
- `services` lists the station services at that moment.
- `observation_count` is how many dockings exist for the station. If
  `observations_truncated` is `true`, only the most recent ones are shown; add
  `&max_observations=200` to the address to see up to 200.
- `has_more: true` means there are more stations; add `&offset=25` (then 50,
  75, and so on) to see the next ones.

### What the route returns, exactly

The route is `GET /api/v1/journal/station-observations` (operation
`listV3JournalStationObservations`). It needs you to be signed in, and it only
ever reads your own imported journals.

| Query parameter | Meaning | Allowed values | Default |
|---|---|---|---|
| `offset` | skip this many stations | 0 to 100,000 | 0 |
| `limit` | stations per page | 1 to 100 | 25 |
| `max_observations` | dockings kept per station (the most recent) | 1 to 200 | 50 |
| `market_id` | only this station | digits only, up to 20 | all stations |

Each station has `market_id`, `observation_count`, `first_docked_at`,
`last_docked_at`, `observations_truncated` and `observations`. Each observation
has `observed_at`, `system_id64`, `system_name`, `station_name`,
`station_type`, `station_government`, `station_allegiance`,
`dist_from_star_ls`, `economies` (`name`, `name_localised`, `proportion`) and
`services`.

## How this feeds the research engine (CRE)

For now this is **manual**. Copy the before and after observations (or the
whole answer from step 5) into your CRE notes or experiment record yourself,
together with your note of what you built and when. ED-Finder does not send
this data to CRE automatically, and the research export stays paused.

## What is not kept yet

The colonisation events themselves (construction-site progress, your
deliveries, system claims, beacon deployment) are **not** kept yet. The
journal store only accepts a fixed list of event types, and that list is
enforced by the database (migration `005`). Adding the colonisation events
needs a new migration (`017`), which can only be registered after the Finder
go-live. They will follow in a later change with that migration.

Until then, write down what you built, when, and how far the construction
progress was.

The five colonisation events, verified on 2026-10-21:

| Event | When the game writes it | Fields besides `timestamp`/`event` |
|---|---|---|
| `ColonisationConstructionDepot` | every 15 s while docked at a construction site | `MarketID`, `ConstructionProgress`, `ConstructionComplete`, `ConstructionFailed`, `ResourcesRequired[]` (`Name`, `Name_Localised`, `RequiredAmount`, `ProvidedAmount`, `Payment`) |
| `ColonisationContribution` | when you deliver materials | `MarketID`, `Contributions[]` (`Name`, `Name_Localised`, `Amount`) |
| `ColonisationSystemClaim` | when you pay to claim a system | `StarSystem`, `SystemAddress` |
| `ColonisationSystemClaimRelease` | when a claim is released | `StarSystem`, `SystemAddress` |
| `ColonisationBeaconDeployed` | when a colonisation beacon is deployed | none |

Sources:

- Elite Dangerous Player Journal manual v38 ("Changes for Odyssey up to
  release 4.1.0.3", April 2025), Colonisation chapter:
  <https://doc.elitedangereuse.fr/Colonisation/> (documents the depot and
  contribution events).
- Community journal JSON schemas, `schemas/Colonisation*/*.json` at commit
  `e4976b5f9b46f784029364453622c2668087cfd6` (2026-09-06):
  <https://github.com/jixxed/ed-journal-schemas> (all five events).

The older readthedocs manual (elite-journal.readthedocs.io, v37, May 2023)
predates colonisation and does not list these events.

Planned handling for the follow-up (decided 2026-10-21, not implemented here):
keep `Payment` (it is the construction site's price per unit, a game-world
fact, not your credits), and key the depot events by the journal line with its
timestamp, because the game repeats them every 15 seconds.
