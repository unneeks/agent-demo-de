export class ResultCache {
  constructor() {
    this.map = new Map();
  }

  get(key) {
    return this.map.get(key) ?? null;
  }

  set(key, value) {
    this.map.set(key, value);
  }
}
