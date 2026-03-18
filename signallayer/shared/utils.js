export function hashMessage(text) {
  const value = String(text ?? "");
  let hash = 5381;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 33) ^ value.charCodeAt(index);
  }
  return Math.abs(hash >>> 0).toString(16).padStart(8, "0");
}

export function tokenize(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

export function unique(items) {
  return [...new Set(items)];
}

export function scoreOverlap(a, b) {
  const left = new Set(tokenize(a));
  const right = tokenize(b);
  if (!left.size || !right.length) {
    return 0;
  }

  let score = 0;
  for (const token of right) {
    if (left.has(token)) {
      score += 1;
    }
  }

  return score / Math.max(left.size, right.length);
}

export function truncate(text, length = 180) {
  const value = String(text ?? "");
  if (value.length <= length) {
    return value;
  }

  return `${value.slice(0, length - 1)}...`;
}

export function nowMs() {
  return Date.now();
}
