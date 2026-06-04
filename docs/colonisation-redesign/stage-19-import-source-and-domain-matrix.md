# Stage 19 — Import Source and Domain Matrix

## Purpose

Data Warehouse Utopia needs to define both:

1. where data comes from; and
2. what categories of data ED-Finder wants to import, stage, warehouse, reconcile, and eventually expose.

This document defines the initial import domain/entity matrix.

## Import domains

### 1. Systems

Goal:

Import and track system-level facts.

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

Likely sources:

- EDSM;
- Spansh;
- Inara where useful;
- local/operator sources.

Canonical impact:

High. System data powers search, filtering, route planning, colonisation planning, and body/station joins.

Initial priority:

High.

### 2. Stars

Goal:

Import and track star-level facts.

Useful fields:

- star type;
- scoopable flag;
- main star flag;
- distance to arrival;
- age/mass/radius/temperature where available;
- luminosity;
- subclass;
- source timestamps.

Likely sources:

- Spansh;
- EDSM;
- possible ED journal/manual sources.

Canonical impact:

Medium/high. Useful for search, route planning, system assessment, and exploration context.

Initial priority:

Medium.

### 3. Bodies / planets / moons

Goal:

Import and track body-level facts.

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
- coordinates/arrival distance where available;
- source timestamps.

Likely sources:

- Spansh;
- EDSM;
- ED journal/manual sources.

Canonical impact:

Very high. Body data drives colonisation planning, ground slot decisions, resource interpretation, and search.

Initial priority:

High.

### 4. Rings

Goal:

Import and track ring-level facts separately from bodies.

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

Likely sources:

- Spansh;
- EDSM where available;
- future specialist sources if needed.

Canonical impact:

High for mining/resource planning and colonisation analysis.

Initial priority:

High.

Notes:

Rings should be first-class warehouse facts, not buried as loose body text.

### 5. Belt clusters

Goal:

Import and track asteroid belt clusters and related orbital infrastructure possibilities.

Useful fields:

- belt cluster name;
- parent star/system;
- belt type;
- reserve level where available;
- orbital/station slots if known;
- source timestamps.

Likely sources:

- Spansh;
- EDSM where available;
- manual/operator observations.

Canonical impact:

Medium/high for colonisation build planning.

Initial priority:

Medium.

### 6. Stations and ports

Goal:

Import stable station facts.

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

Likely sources:

- EDSM;
- Inara;
- Spansh;
- ED journal/manual sources.

Canonical impact:

Very high.

Initial priority:

Very high.

Policy carried forward from Stage 18:

| Source value | Policy |
|---|---|
| `Coriolis Starport` | May map to `Coriolis` with confirmed identity and review/approval. |
| `Dodec Starport` | May map to `Dodec` with confirmed identity and review/approval. |
| `Drake-Class Carrier` | Refuse/defer as transient/mobile carrier. |
| `Space Construction Depot` | Refuse/defer as transient construction object. |
| `NULL` | Refuse. |

### 7. Settlements / planetary ports / outposts

Goal:

Import stable surface infrastructure separately from orbitals where possible.

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

Likely sources:

- Inara;
- EDSM where available;
- Spansh where available;
- manual/operator data.

Canonical impact:

High for colonisation, ground slot planning, and search.

Initial priority:

High.

### 8. Services

Goal:

Import station/service availability as source evidence.

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
- black market;
- carrier-specific services, if carriers are tracked separately as transient evidence.

Likely sources:

- Inara;
- EDSM;
- journal/manual data.

Canonical impact:

High, but should not overwrite canonical service flags without reconciliation.

Initial priority:

High.

### 9. Markets and commodities

Goal:

Import market facts where useful and legally/practically available.

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

Likely sources:

- Inara where accessible/appropriate;
- ED journal/manual data;
- possible community datasets.

Canonical impact:

Medium/high for planning and search, but highly freshness-sensitive.

Initial priority:

Medium.

Notes:

Market data should always carry freshness/age and should never be treated as timeless canonical truth.

### 10. Shipyard and outfitting

Goal:

Import availability of ships/modules.

Useful fields:

- station/market ID;
- ship/module name;
- availability;
- price where available;
- timestamp;
- source.

Likely sources:

- Inara;
- ED journal/manual data.

Canonical impact:

Medium.

Initial priority:

Later, unless needed for user-facing search.

### 11. Factions / BGS / controlling faction

Goal:

Import political/economic context.

Useful fields:

- controlling faction;
- faction state;
- influence;
- allegiance;
- government;
- security;
- economy;
- timestamps.

Likely sources:

- Inara;
- EDSM;
- journal/manual data.

Canonical impact:

Medium/high but volatile.

Initial priority:

Medium.

Notes:

BGS/state data should be treated as volatile and freshness-bound.

### 12. Economies and security

Goal:

Import economy and security signals for systems/stations.

Useful fields:

- primary economy;
- secondary economy;
- station economy;
- system economy;
- security;
- population;
- source timestamps.

Likely sources:

- EDSM;
- Inara;
- Spansh;
- journal/manual data.

Canonical impact:

High for search and colonisation planning.

Initial priority:

High.

### 13. Colonisation / construction sites

Goal:

Track colonisation construction states without polluting stable station catalogue.

Useful fields:

- construction depot name;
- planned final station if known;
- source station type;
- required commodities;
- delivered commodities;
- completion state;
- weekly tick transition status;
- source timestamps.

Likely sources:

- manual/operator input;
- future community sources;
- game/journal observations if available.

Canonical impact:

High for colonisation tools, but must be separated from final stable stations.

Initial priority:

Medium/high.

Policy:

`Space Construction Depot` is transient. It should be stored as construction evidence or transient infrastructure, not mapped to a final station type.

### 14. Fleet carriers

Goal:

Track only if explicitly needed as transient/mobile objects.

Useful fields:

- carrier callsign/name;
- system;
- services;
- market availability;
- last seen;
- source timestamp.

Likely sources:

- Inara;
- EDSM where available;
- journal/manual data.

Canonical impact:

Low for stable station catalogue.

Initial priority:

Low.

Policy:

Fleet carriers should not surface as stable canonical stations. `Drake-Class Carrier` remains refused/deferred for stable station-type writes.

### 15. Materials / resources / hotspots

Goal:

Support mining/resource/colonisation planning.

Useful fields:

- ring hotspot type;
- reserve level;
- body materials;
- geological/biological signals;
- source timestamps.

Likely sources:

- Spansh;
- EDSM;
- ED journal/manual data;
- community sources.

Canonical impact:

Medium/high.

Initial priority:

Medium.

### 16. Facilities / colonisation build templates

Goal:

Import build-plan templates and facility metadata.

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

Likely sources:

- DaftMav spreadsheet;
- Mega Guide;
- manual/operator structured files.

Canonical impact:

Very high for colonisation planner logic.

Initial priority:

High.

### 17. Rules / mechanics reference

Goal:

Import or structure rules that constrain planner logic.

Useful fields:

- rule name;
- rule description;
- source document;
- source section;
- confidence;
- version;
- examples;
- related mechanics.

Likely sources:

- Mega Guide;
- curated manual docs;
- operator-confirmed decisions.

Canonical impact:

Very high for planner correctness, but should be manually curated.

Initial priority:

High as manual structured reference, not automatic web import.

### 18. Operator artifacts and review evidence

Goal:

Treat operator artifacts as first-class audit evidence.

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

Likely sources:

- `/var/lib/ed-finder/operator-artifacts/`;
- GitHub docs closeouts.

Canonical impact:

High for auditability.

Initial priority:

Very high.

## Import domain priority

Recommended initial order:

1. Operator artifact/source-run ledger.
2. EDSM stations/systems.
3. EDSM/Spansh body and ring data.
4. Station services/economies.
5. Facility/build template data.
6. Construction/colonisation transient evidence.
7. Inara enrichment where access/trust is confirmed.
8. Markets/shipyard/outfitting after freshness model exists.
9. Fleet carriers only as transient/mobile objects, if needed.
10. Niche community data sources.

## Warehouse design implication

The warehouse should not have one generic “import data” blob.

It should support distinct source/staging/warehouse domains:

- source run ledger;
- raw source files / source hashes;
- staging systems;
- staging bodies;
- staging rings;
- staging stations;
- staging station services;
- staging markets;
- staging factions;
- staging construction sites;
- staging facility templates;
- staging rules/reference facts;
- warehouse system facts;
- warehouse body facts;
- warehouse ring facts;
- warehouse station facts;
- warehouse service facts;
- warehouse market facts;
- reconciliation candidates;
- review/approval/write artifacts.

## Immediate next step

Stage 19A should inventory which of these domains already exist and which are missing.

Stage 19B should define the target schema boundaries.

Stage 19C should complete the source/domain priority matrix before the first auto-import is enabled.
