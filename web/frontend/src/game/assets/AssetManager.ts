import { GAME_ASSETS, type AssetPhase, type GameAsset } from "./manifest.js";

export type AssetLoadStatus = "pending" | "loaded" | "placeholder" | "failed";

export type LoadedAsset = {
  id: string;
  path: string;
  kind: GameAsset["kind"];
  phase: AssetPhase;
  status: AssetLoadStatus;
  blob: Blob | null;
  objectUrl: string | null;
  error: string | null;
};

export type AssetProgress = {
  loaded: number;
  total: number;
  ratio: number;
  currentAssetId: string | null;
};

type ProgressListener = (progress: AssetProgress) => void;

const PLACEHOLDER_BYTES = new Uint8Array([
  137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1,
  0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 13, 73, 68, 65, 84,
  120, 156, 99, 96, 96, 96, 248, 15, 0, 1, 4, 1, 0, 112, 32, 101, 11, 0, 0,
  0, 0, 73, 69, 78, 68, 174, 66, 96, 130,
]);

export class AssetManager {
  private cache = new Map<string, LoadedAsset>();
  private listeners = new Set<ProgressListener>();
  private objectUrls = new Set<string>();

  constructor(private readonly manifest: readonly GameAsset[] = GAME_ASSETS) {}

  onProgress(listener: ProgressListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async preloadCore(): Promise<LoadedAsset[]> {
    return this.loadPhase("core");
  }

  async loadDeferred(): Promise<LoadedAsset[]> {
    return this.loadPhase("deferred");
  }

  async loadPhase(phase: AssetPhase): Promise<LoadedAsset[]> {
    return this.loadMany(this.manifest.filter((asset) => asset.phase === phase));
  }

  async load(assetId: string): Promise<LoadedAsset> {
    const cached = this.cache.get(assetId);
    if (cached) {
      return cached;
    }

    const asset = this.manifest.find((item) => item.id === assetId);
    if (!asset) {
      throw new Error(`Unknown asset: ${assetId}`);
    }
    if (asset.phase === "reference") {
      throw new Error(`Reference-only asset cannot be loaded at runtime: ${assetId}`);
    }
    return this.fetchAsset(asset);
  }

  get(assetId: string): LoadedAsset | null {
    return this.cache.get(assetId) ?? null;
  }

  snapshot(): Record<string, LoadedAsset> {
    return Object.fromEntries(this.cache.entries());
  }

  dispose(): void {
    for (const url of this.objectUrls) {
      URL.revokeObjectURL(url);
    }
    this.objectUrls.clear();
    this.cache.clear();
  }

  private async loadMany(assets: readonly GameAsset[]): Promise<LoadedAsset[]> {
    const runtimeAssets = assets.filter((asset) => asset.phase !== "reference");
    const loaded: LoadedAsset[] = [];
    let completed = 0;
    this.emitProgress({ loaded: completed, total: runtimeAssets.length, ratio: runtimeAssets.length === 0 ? 1 : 0, currentAssetId: null });

    for (const asset of runtimeAssets) {
      const item = await this.fetchAsset(asset);
      loaded.push(item);
      completed += 1;
      this.emitProgress({
        loaded: completed,
        total: runtimeAssets.length,
        ratio: runtimeAssets.length === 0 ? 1 : completed / runtimeAssets.length,
        currentAssetId: asset.id,
      });
    }
    return loaded;
  }

  private async fetchAsset(asset: GameAsset): Promise<LoadedAsset> {
    const cached = this.cache.get(asset.id);
    if (cached) {
      return cached;
    }

    try {
      const response = await fetch(asset.path);
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      const blob = await response.blob();
      const loaded = this.loadedAsset(asset, "loaded", blob, null);
      this.cache.set(asset.id, loaded);
      return loaded;
    } catch (err: unknown) {
      if (!asset.optional) {
        throw new Error(`Required asset failed: ${asset.id} (${err instanceof Error ? err.message : "unknown error"})`);
      }
      const placeholder = this.loadedAsset(asset, "placeholder", placeholderBlob(asset.kind), err instanceof Error ? err.message : "unknown error");
      this.cache.set(asset.id, placeholder);
      return placeholder;
    }
  }

  private loadedAsset(asset: GameAsset, status: AssetLoadStatus, blob: Blob, error: string | null): LoadedAsset {
    const objectUrl = URL.createObjectURL(blob);
    this.objectUrls.add(objectUrl);
    return {
      id: asset.id,
      path: asset.path,
      kind: asset.kind,
      phase: asset.phase,
      status,
      blob,
      objectUrl,
      error,
    };
  }

  private emitProgress(progress: AssetProgress): void {
    for (const listener of this.listeners) {
      listener(progress);
    }
  }
}

function placeholderBlob(kind: GameAsset["kind"]): Blob {
  if (kind === "font") {
    return new Blob([], { type: "font/woff2" });
  }
  if (kind === "hdri") {
    return new Blob([], { type: "application/octet-stream" });
  }
  if (kind === "model") {
    return new Blob([], { type: "model/gltf-binary" });
  }
  return new Blob([PLACEHOLDER_BYTES], { type: "image/png" });
}
