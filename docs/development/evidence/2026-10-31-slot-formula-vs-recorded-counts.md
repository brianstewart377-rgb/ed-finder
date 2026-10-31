# Slot formula versus recorded slot counts (2026-10-31)

## Question

Can the V3 Colony Planner (design `docs/superpowers/specs/2026-10-30-v3-colony-planner-design.md`)
rely on `apps/api/src/ingest/slot_prediction.py` (`validated-slot-v1`) for the
number of orbital and surface construction slots on each body?

## Method

- **System:** Praea Euq WV-W b2-2, id64 `5076786292249`, the owner's own colony.
- **Recorded counts:** the `slots` map of the owner's Raven Colonial main layout,
  revision 174, saved 2026-10-30. Raven stores `[orbital, surface]` per body,
  with `-1` meaning not applicable or unknown.
- **Body facts:** the Spansh system dump (`https://spansh.co.uk/api/dump/5076786292249`),
  fetched 2026-10-31. It gives radius, landable, surface temperature, gravity,
  atmosphere, planet class, terraforming state, volcanism, rings and signals.
- **Formula:** `predict_body_slots` from `main` at `442af490`, fed those facts.
  Radius is converted km → m. Terraformable means Spansh's "Candidate for
  terraforming" or "Terraformable". Geological and biological counts come from
  the body's signals.
- Raven Colonial was used only as the source of the recorded numbers. No Raven
  code or data files are copied.

## How Raven gets slot counts

This was checked against Raven's public code (RavenColonialWeb `1b65322`) and
two freshly opened systems on 2026-10-31.

- **Surface slots:** Raven estimates these with a rule close to
  `validated-slot-v1`'s, and labels them "(predicted)".
- **Orbital slots:** Raven never estimates these. In Praea Euq HZ-A c10 all 21
  bodies showed "Orbital slots: unknown"; in Praea Euq YB-V b3-1 all 3 stars
  did. Orbital counts in a Raven layout are typed in from the game's Architect
  Mode.
- **SrvSurvey** (`4b0b65c`) deliberately does not upload slot counts to Raven.

## Result

| Slots | Bodies compared | Formula matches the recorded count |
|---|---:|---:|
| Surface (landable bodies) | 24 | **24** |
| Orbital (all bodies) | 42 | **17** |

**Surface: the formula is right for every landable body.**

**Orbital: it is wrong for 25 of 42 bodies.**
- Every large body is predicted 4, but the recorded counts are 0–2. That is 13
  bodies: four water worlds, a rocky-ice world, six gas giants, a large ringed
  icy body and the star.
- The other 12 misses are small moons.
- Moons of similar radius have recorded counts of 0, 1, 2 or 3 (14 a, 727 km:
  0; 14 e, 840 km: 3). The radius rule cannot produce that spread.

The "2 true mismatches" claim in `slot_prediction.py` refers to an evidence set
that is not in the repository. This result suggests the claim holds for surface
slots but not for orbital slots.

## Body by body

`✗` marks a formula value that differs from the recorded count. `—` means Raven
records no surface slots, because the body is not landable.

| Body | Type | Radius (km) | Landable | Rings | Raven orbital | Formula orbital | Raven surface | Formula surface |
|---|---|---:|---|---|---:|---:|---:|---:|
| (star) | M (Red dwarf) Star | 340,759 | no | no | 2 | 4 ✗ | — | — |
| 1 | High metal content world | 886 | yes | no | 1 | 1 | 0 | 0 |
| 2 | High metal content world | 990 | yes | no | 1 | 1 | 3 | 3 |
| 3 | High metal content world | 2,935 | yes | no | 2 | 2 | 3 | 3 |
| 4 | High metal content world | 2,792 | yes | no | 2 | 2 | 3 | 3 |
| 5 | Water world | 6,927 | no | no | 2 | 4 ✗ | — | — |
| 6 | Water world | 6,839 | no | no | 2 | 4 ✗ | — | — |
| 7 | Water world | 9,886 | no | no | 2 | 4 ✗ | — | — |
| 8 | Water world | 9,535 | no | no | 2 | 4 ✗ | — | — |
| 9 | Rocky Ice world | 9,203 | no | no | 2 | 4 ✗ | — | — |
| 10 | Class I gas giant | 71,535 | no | yes | 2 | 4 ✗ | — | — |
| 10 a | Icy body | 1,200 | yes | no | 2 | 1 ✗ | 2 | 2 |
| 10 b | Icy body | 1,009 | yes | no | 2 | 1 ✗ | 2 | 2 |
| 10 c | Icy body | 1,436 | yes | no | 1 | 1 | 2 | 2 |
| 10 d | Icy body | 1,296 | no | no | 1 | 1 | — | — |
| 10 e | Icy body | 1,535 | no | no | 2 | 2 | — | — |
| 10 f | Icy body | 1,507 | no | no | 1 | 2 ✗ | — | — |
| 11 | Class I gas giant | 70,864 | no | no | 2 | 4 ✗ | — | — |
| 11 a | Icy body | 778 | no | no | 1 | 1 | — | — |
| 11 b | Icy body | 925 | no | no | 1 | 1 | — | — |
| 11 c | Icy body | 610 | yes | no | 2 | 1 ✗ | 1 | 1 |
| 11 d | Icy body | 746 | yes | no | 2 | 1 ✗ | 1 | 1 |
| 11 e | Icy body | 1,161 | yes | no | 1 | 1 | 1 | 1 |
| 12 | Class I gas giant | 70,367 | no | yes | 2 | 4 ✗ | — | — |
| 12 a | Icy body | 958 | yes | no | 1 | 1 | 2 | 2 |
| 12 b | Icy body | 1,242 | yes | no | 1 | 1 | 2 | 2 |
| 12 c | Icy body | 1,202 | yes | no | 2 | 1 ✗ | 2 | 2 |
| 12 d | Icy body | 1,055 | yes | no | 1 | 1 | 2 | 2 |
| 12 e | Icy body | 1,261 | yes | no | 1 | 1 | 2 | 2 |
| 12 f | Icy body | 1,019 | yes | no | 1 | 1 | 2 | 2 |
| 13 | Class I gas giant | 44,123 | no | yes | 1 | 4 ✗ | — | — |
| 13 a | Icy body | 875 | yes | no | 1 | 1 | 2 | 2 |
| 13 b | Icy body | 635 | yes | no | 2 | 1 ✗ | 2 | 2 |
| 14 | Class I gas giant | 50,412 | no | yes | 0 | 4 ✗ | — | — |
| 14 a | Icy body | 727 | yes | no | 0 | 1 ✗ | 1 | 1 |
| 14 b | Icy body | 1,503 | yes | no | 3 | 2 ✗ | 2 | 2 |
| 14 c | Icy body | 1,207 | yes | no | 1 | 1 | 1 | 1 |
| 14 c a | Icy body | 526 | yes | no | 0 | 1 ✗ | 2 | 2 |
| 14 d | Icy body | 860 | yes | no | 2 | 1 ✗ | 1 | 1 |
| 14 e | Icy body | 840 | yes | no | 3 | 1 ✗ | 1 | 1 |
| 15 | Icy body | 14,657 | no | yes | 1 | 4 ✗ | — | — |
| 16 | Class I gas giant | 72,303 | no | no | 1 | 4 ✗ | — | — |

## Consequence for the planner

- **Surface slots** are predicted with `validated-slot-v1`. Its high-metal-content
  bonus needs the planet class, which V3 canonical bodies do not store: every
  planet is `body_type = planet`. The class is in
  `v3_derived.body_mechanics.body_class` of the published derived generation,
  one of the relations step P is copying. Predictions therefore come in slice
  S3b, after step P completes.
- **Orbital slots** are not predicted. They start as "enter what Architect Mode
  shows", as Raven does, or come in through a Raven layout import.
