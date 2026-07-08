# Stage 19 — Import Source and Domain Matrix

## Purpose

Data Warehouse Utopia needs to define both:

1. where data comes from; and
2. what categories of data ED-Finder wants to import, stage, warehouse, reconcile, and eventually expose.

This document defines the initial import source and domain/entity matrix.

## Source matrix

| Source | Category | Likely use | Trust / caveat | Auto-import priority |
|---|---|---|---|---|
| EDSM | Source of evidence | Systems, stations, station types, external IDs, services/economies where available | Proven useful in Stage 18J/P18; still source evidence, not direct canonical truth | First |
| Spansh | Source of evidence | Broad system/body/station data, coordinates, bodies, rings | High coverage; needs schema mapping, chunking, and freshness checks | High |
| Inara | Source of evidence | Stations, markets, economies, factions, services, commodity signals, mission context if accessible | Useful but needs access/rate-limit/trust review | Medium/high |
| DaftMav sheets/templates | Source of truth/evidence for build templates | Facility templates, build economics, colonisation planning rules | Should be versioned and hashed; likely manual/file import first | High |
| Mega Guide | Source of truth/reference | Rules, constraints, mechanics, interpretation | Human/reference source; not all content is machine-importable | High as reference |
| ED-Finder operator artifacts | Manual/operator source | Review packets, dry-runs, approval allowlists, write results | Primary audit trail for controlled canonical changes | Critical |
| Mission observations | Source of evidence / derived analytics | Mission board patterns, mission density, station-to-station links | Volatile; must be freshness-bound | High after warehouse basics |
| reference planner | Source of inspiration | UI ideas, workflow ideas, feature comparison | Not a source of canonical Elite Dangerous data | Low/import not needed |
| EDCD/community datasets | Source of evidence | Potential future reference/metadata feeds | Evaluate later; do not assume trust yet | Later |
| Canonn/community science data | Source of evidence | Specialist location/body/phenomena context | Useful in niche cases; not core first pass | Later |
| Frontier/game journal data | Source of evidence/manual import | Player-observed facts, mission observations, market/service snapshots | High value if available but user-specific/manual | Later |

## Import domains

### Systems

Useful fields:

- system name;
- system address / ID64;
- coordinates;
- primary star;
- population;
- allegiance;
- government;
- economy;
- security;
- controlling faction where available;
- permit / accessibility flags where available;
- updated timestamps;
- source provenance.

Priority: High.

### Stars

Useful fields:

- star type;
- scoopable flag;
- main star flag;
- distance to arrival;
- age/mass/radius/temperature where available;
- luminosity;
- subclass;
- source timestamps.

Priority: Medium.

### Bodies / planets / moons

Useful fields:

- body name;
- body ID;
- parent body;
- body type;
- planet class;
- landable flag;
- gravity;
- radius;
- mass;
- temperature;
- pressure;
- atmosphere;
- volcanism;
- terraform state;
- orbital period;
- semi-major axis;
- eccentricity;
- inclination;
- axial tilt;
- rotation period;
- source timestamps.

Priority: High.

### Rings

Useful fields:

- ring name;
- parent body;
- ring type;
- inner radius;
- outer radius;
- mass;
- reserve level where available;
- hotspots where available;
- material/mineral signals where available;
- source timestamps.

Priority: High.

Rings should be first-class warehouse facts, not buried as loose body text.

### Belt clusters

Useful fields:

- belt cluster name;
- parent star/system;
- belt type;
- reserve level where available;
- orbital/station slots if known;
- source timestamps.

Priority: Medium.

### Stations and ports

Useful fields:

- station name;
- station ID / EDSM ID / market ID;
- system ID64;
- body association;
- distance to arrival;
- station type;
- landing pad size;
- services;
- economies;
- allegiance/government/faction where available;
- market/shipyard/outfitting flags;
- update timestamps;
- source provenance.

Priority: Very high.

Policy carried forward from Stage 18:

| Source value | Policy |
|---|---|
| `Coriolis Starport` | May map to `Coriolis` with confirmed identity and review/approval. |
| `Dodec Starport` | May map to `Dodec` with confirmed identity and review/approval. |
| `Drake-Class Carrier` | Refuse/defer as transient/mobile carrier. |
| `Space Construction Depot` | Refuse/defer as transient construction object. |
| `NULL` | Refuse. |

### Settlements / planetary ports / outposts

Useful fields:

- name;
- body ID/name;
- latitude/longitude where available;
- settlement type;
- economy;
- government;
- faction;
- services;
- market/outfitting/shipyard flags where applicable;
- landing pad;
- source timestamps.

Priority: High.

### Services

Useful fields:

- market;
- shipyard;
- outfitting;
- refuel;
- repair;
- rearm;
- contacts;
- universal cartographics;
- Vista Genomics;
- material trader;
- technology broker;
- interstellar factors;
- rescue/search services;
- black market.

Priority: High.

### Markets and commodities

Useful fields:

- market ID;
- commodity;
- buy price;
- sell price;
- demand;
- supply;
- age/freshness;
- station ID;
- source timestamps.

Priority: Medium.

Market data must always carry freshness/age and should never be treated as timeless canonical truth.

### Shipyard and outfitting

Useful fields:

- station/market ID;
- ship/module name;
- availability;
- price where available;
- timestamp;
- source.

Priority: Later unless needed for user-facing search.

### Factions / BGS / controlling faction

Useful fields:

- controlling faction;
- faction state;
- influence;
- allegiance;
- government;
- security;
- economy;
- timestamps.

Priority: Medium.

BGS/state data is volatile and freshness-bound.

### Economies and security

Useful fields:

- primary economy;
- secondary economy;
- station economy;
- system economy;
- security;
- population;
- source timestamps.

Priority: High.

### Colonisation / construction sites

Useful fields:

- construction depot name;
- planned final station if known;
- source station type;
- required commodities;
- delivered commodities;
- completion state;
- weekly tick transition status;
- source timestamps.

Priority: Medium/high.

Policy:

`Space Construction Depot` is transient. It should be stored as construction evidence or transient infrastructure, not mapped to a final station type.

### Fleet carriers

Useful fields if tracked:

- carrier callsign/name;
- system;
- services;
- market availability;
- last seen;
- source timestamp.

Priority: Low.

Policy:

Fleet carriers should not surface as stable canonical stations. `Drake-Class Carrier` remains refused/deferred for stable station-type writes.

### Materials / resources / hotspots

Useful fields:

- ring hotspot type;
- reserve level;
- body materials;
- geological/biological signals;
- source timestamps.

Priority: Medium.

### Facilities / colonisation build templates

Useful fields:

- facility/building name;
- tier;
- category;
- prerequisites;
- costs;
- outputs;
- slot requirements;
- economy effects;
- build sequencing;
- source/version.

Priority: High.

### Rules / mechanics reference

Useful fields:

- rule name;
- rule description;
- source document;
- source section;
- confidence;
- version;
- examples;
- related mechanics.

Priority: High as manual structured reference.

### Missions and mission-board intelligence

Goal:

Import, infer, and track mission-related evidence so ED-Finder can identify strong mission ecosystems, not just static infrastructure.

Useful fields:

- mission board source station;
- mission destination station/system/body;
- mission type;
- passenger/cargo/combat/mining/source-return/classification;
- faction offering mission;
- target faction where available;
- economy/state context;
- reward type;
- cargo/material requirements where visible;
- destination distance;
- pad-size compatibility;
- repeat destination patterns;
- station-to-station mission links;
- source timestamp;
- freshness/expiry;
- confidence;
- source provenance.

Likely sources:

- player journal/manual captures where available;
- operator-entered mission observations;
- future local capture tooling if safe and allowed;
- inferred mission links from repeated observations;
- faction/economy/system state data from Inara/EDSM/other evidence;
- station/economy/service warehouse facts.

Canonical impact:

High for ED-Finder experience, but mission data is volatile and must be treated as time-bound evidence.

Priority:

High as a derived/analytics domain, after the source-run ledger and first warehouse imports are stable.

Mission intelligence should support:

- mission density score;
- passenger mission suitability;
- cargo/source-return suitability;
- faction mission cluster strength;
- nearby destination network quality;
- large-pad mission usefulness;
- tourism/passenger hub potential;
- mining/source-return opportunity;
- home-system mission paradise score.

### Operator artifacts and review evidence

Useful fields:

- artifact type;
- schema version;
- path;
- file hash;
- artifact integrity hash;
- generated at;
- source stage;
- decision boundary;
- write status;
- reviewed row counts.

Priority: Very high.

## Import domain priority

Recommended initial order:

1. Operator artifact/source-run ledger.
2. EDSM stations/systems.
3. EDSM/Spansh body and ring data.
4. Station services/economies.
5. Facility/build template data.
6. Mission-board intelligence and mission density analytics.
7. Construction/colonisation transient evidence.
8. Inara enrichment where access/trust is confirmed.
9. Markets/shipyard/outfitting after freshness model exists.
10. Fleet carriers only as transient/mobile objects, if needed.
11. Niche community data sources.

## Warehouse design implication

The warehouse should not have one generic import blob.

It should support distinct source/staging/warehouse domains:

- source run ledger;
- raw source files / source hashes;
- staging systems;
- staging stars;
- staging bodies;
- staging rings;
- staging belt clusters;
- staging stations;
- staging settlements;
- staging station services;
- staging markets;
- staging factions;
- staging construction sites;
- staging facility templates;
- staging rules/reference facts;
- staging mission observations;
- warehouse system facts;
- warehouse body facts;
- warehouse ring facts;
- warehouse station facts;
- warehouse service facts;
- warehouse mission intelligence facts;
- reconciliation candidates;
- review/approval/write artifacts.

## Immediate next step

Stage 19A should inventory which of these domains already exist and which are missing.

Stage 19B should define the target schema boundaries.

Stage 19C/19D should complete source and domain priorities before the first auto-import is enabled.

