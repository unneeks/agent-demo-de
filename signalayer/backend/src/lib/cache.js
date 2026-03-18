export class AnalysisCache {
  constructor() {
    this.store = new Map();
  }

  get(key) {
    return this.store.get(key);
  }

  set(key, value) {
    this.store.set(key, value);
    return value;
  }
}

export const analysisCache = new AnalysisCache();
