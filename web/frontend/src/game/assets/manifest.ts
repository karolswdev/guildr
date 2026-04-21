export type AssetKind = "texture" | "font" | "hdri" | "model";
export type AssetPhase = "core" | "deferred" | "reference";

export type GameAsset = {
  id: string;
  path: string;
  kind: AssetKind;
  phase: AssetPhase;
  optional: boolean;
  bytesHint: number;
};

export interface GameAssetManifest {
  environment: {
    hdriSky: string;
  };
  atom: {
    flatNormal: string;
    grain: string;
  };
  artifact: {
    grain: string;
  };
  particles: {
    disc: string;
    spark: string;
  };
  memPalace: {
    radialAlpha: string;
    lensflare: string;
  };
  polyPizza: {
    planetA: string;
    planetB: string;
    pixelPlanet: string;
  };
  fonts: {
    inter: string;
    jetbrainsMono: string;
    tablerIcons: string;
  };
}

export const ASSET_BASE_PATH = "/assets";

export const GAME_ASSET_MANIFEST: GameAssetManifest = {
  environment: {
    hdriSky: `${ASSET_BASE_PATH}/hdris/kloppenheim-02-puresky-1k.hdr`,
  },
  atom: {
    flatNormal: `${ASSET_BASE_PATH}/atom-meshes/flat-normal.png`,
    grain: `${ASSET_BASE_PATH}/atom-meshes/canvas-grain.png`,
  },
  artifact: {
    grain: `${ASSET_BASE_PATH}/artifact-textures/canvas-grain.png`,
  },
  particles: {
    disc: `${ASSET_BASE_PATH}/edge-particle-sprites/disc.png`,
    spark: `${ASSET_BASE_PATH}/edge-particle-sprites/spark1.png`,
  },
  memPalace: {
    radialAlpha: `${ASSET_BASE_PATH}/mempalace/radial-alpha-gradient.png`,
    lensflare: `${ASSET_BASE_PATH}/mempalace/lensflare0.png`,
  },
  polyPizza: {
    planetA: `${ASSET_BASE_PATH}/poly-pizza/planet-18Uxrb2dIc/planet-18Uxrb2dIc.glb`,
    planetB: `${ASSET_BASE_PATH}/poly-pizza/planet-9g1aIbfR9Y/planet-9g1aIbfR9Y.glb`,
    pixelPlanet: `${ASSET_BASE_PATH}/poly-pizza/pixel-planet-wise-0855-0714-KcQcdI9GTt/pixel-planet-wise-0855-0714-KcQcdI9GTt.glb`,
  },
  fonts: {
    inter: `${ASSET_BASE_PATH}/fonts/InterVariable.woff2`,
    jetbrainsMono: `${ASSET_BASE_PATH}/fonts/JetBrainsMono-Regular.woff2`,
    tablerIcons: `${ASSET_BASE_PATH}/icon-sprites/tabler-icons.woff2`,
  },
};

export const REFERENCE_ASSETS = {
  lensDirt: `${ASSET_BASE_PATH}/post-processing-refs/lensDirt1.png`,
} as const;

export const GAME_ASSETS: readonly GameAsset[] = [
  { id: "atom.flatNormal", path: GAME_ASSET_MANIFEST.atom.flatNormal, kind: "texture", phase: "core", optional: false, bytesHint: 800 },
  { id: "atom.grain", path: GAME_ASSET_MANIFEST.atom.grain, kind: "texture", phase: "core", optional: false, bytesHint: 200000 },
  { id: "artifact.grain", path: GAME_ASSET_MANIFEST.artifact.grain, kind: "texture", phase: "core", optional: false, bytesHint: 200000 },
  { id: "particles.disc", path: GAME_ASSET_MANIFEST.particles.disc, kind: "texture", phase: "core", optional: false, bytesHint: 1400 },
  { id: "memPalace.radialAlpha", path: GAME_ASSET_MANIFEST.memPalace.radialAlpha, kind: "texture", phase: "core", optional: false, bytesHint: 13000 },
  { id: "fonts.inter", path: GAME_ASSET_MANIFEST.fonts.inter, kind: "font", phase: "core", optional: false, bytesHint: 880000 },
  { id: "fonts.jetbrainsMono", path: GAME_ASSET_MANIFEST.fonts.jetbrainsMono, kind: "font", phase: "core", optional: false, bytesHint: 120000 },
  { id: "fonts.tablerIcons", path: GAME_ASSET_MANIFEST.fonts.tablerIcons, kind: "font", phase: "core", optional: false, bytesHint: 50000 },
  { id: "particles.spark", path: GAME_ASSET_MANIFEST.particles.spark, kind: "texture", phase: "deferred", optional: true, bytesHint: 700 },
  { id: "memPalace.lensflare", path: GAME_ASSET_MANIFEST.memPalace.lensflare, kind: "texture", phase: "deferred", optional: true, bytesHint: 150000 },
  { id: "environment.hdriSky", path: GAME_ASSET_MANIFEST.environment.hdriSky, kind: "hdri", phase: "deferred", optional: true, bytesHint: 1500000 },
  { id: "polyPizza.planetA", path: GAME_ASSET_MANIFEST.polyPizza.planetA, kind: "model", phase: "deferred", optional: true, bytesHint: 86312 },
  { id: "polyPizza.planetB", path: GAME_ASSET_MANIFEST.polyPizza.planetB, kind: "model", phase: "deferred", optional: true, bytesHint: 74072 },
  { id: "polyPizza.pixelPlanet", path: GAME_ASSET_MANIFEST.polyPizza.pixelPlanet, kind: "model", phase: "deferred", optional: true, bytesHint: 105716 },
  { id: "postProcessing.lensDirtReference", path: REFERENCE_ASSETS.lensDirt, kind: "texture", phase: "reference", optional: true, bytesHint: 3000000 },
] as const;

export const CORE_GAME_ASSETS = GAME_ASSETS.filter((asset) => asset.phase === "core");
export const DEFERRED_GAME_ASSETS = GAME_ASSETS.filter((asset) => asset.phase === "deferred");
export const SERVICE_WORKER_ASSET_PATHS = CORE_GAME_ASSETS.map((asset) => asset.path);
