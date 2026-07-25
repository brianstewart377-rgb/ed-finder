export interface GalaxyRegionOption {
  id: number;
  name: string;
}

/**
 * Elite Dangerous' 42 named galactic regions.
 *
 * IDs intentionally match sql/001_schema.sql and the authoritative region-map
 * dataset used by the Map route.
 */
export const GALAXY_REGIONS: readonly GalaxyRegionOption[] = [
  { id: 1, name: 'Galactic Centre' },
  { id: 2, name: 'Empyrean Straits' },
  { id: 3, name: "Ryker's Hope" },
  { id: 4, name: "Odin's Hold" },
  { id: 5, name: 'Norma Arm' },
  { id: 6, name: 'Arcadian Stream' },
  { id: 7, name: 'Izanami' },
  { id: 8, name: 'Inner Orion-Perseus Conflux' },
  { id: 9, name: 'Inner Scutum-Centaurus Arm' },
  { id: 10, name: 'Norma Expanse' },
  { id: 11, name: 'Trojan Belt' },
  { id: 12, name: 'The Veils' },
  { id: 13, name: "Newton's Vault" },
  { id: 14, name: 'The Conduit' },
  { id: 15, name: 'Outer Orion-Perseus Conflux' },
  { id: 16, name: 'Orion-Cygnus Arm' },
  { id: 17, name: 'Temple' },
  { id: 18, name: 'Inner Orion Spur' },
  { id: 19, name: "Hawking's Gap" },
  { id: 20, name: "Dryman's Point" },
  { id: 21, name: 'Sagittarius-Carina Arm' },
  { id: 22, name: 'Mare Somnia' },
  { id: 23, name: 'Acheron' },
  { id: 24, name: 'Formorian Frontier' },
  { id: 25, name: 'Hieronymus Delta' },
  { id: 26, name: 'Outer Scutum-Centaurus Arm' },
  { id: 27, name: 'Outer Arm' },
  { id: 28, name: "Aquila's Halo" },
  { id: 29, name: 'Errant Marches' },
  { id: 30, name: 'Perseus Arm' },
  { id: 31, name: 'Formidine Rift' },
  { id: 32, name: 'Vulcan Gate' },
  { id: 33, name: 'Elysian Shore' },
  { id: 34, name: 'Sanguineous Rim' },
  { id: 35, name: 'Outer Orion Spur' },
  { id: 36, name: "Achilles's Altar" },
  { id: 37, name: 'Xibalba' },
  { id: 38, name: "Lyra's Song" },
  { id: 39, name: 'Tenebrae' },
  { id: 40, name: 'The Abyss' },
  { id: 41, name: "Kepler's Crest" },
  { id: 42, name: 'The Void' },
];
