export class AnalysisCache {
  constructor(limit = 200) {
    this.limit = limit;
    this.store = new Map();
  }

  get(key) {
    if (!this.store.has(key)) {
      return null;
    }

    const value = this.store.get(key);
    this.store.delete(key);
    this.store.set(key, value);
    return value;
  }

  set(key, value) {
    if (this.store.has(key)) {
      this.store.delete(key);
    }

    this.store.set(key, value);
    if (this.store.size > this.limit) {
      const oldestKey = this.store.keys().next().value;
      this.store.delete(oldestKey);
    }
  }
}
