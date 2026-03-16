import { getTraditionEndYear, TIMELINE_END, TIMELINE_START } from "./timeline.js";

const BAND_ORDER = [
  "tribal religious systems",
  "Vedic ritual systems",
  "Brahminical institutions",
  "temple religions",
  "tantric traditions",
  "bhakti movements",
  "modern reform movements",
  "non-Vedic ascetic systems"
];

export function buildSynchronologyBands(traditions) {
  const grouped = new Map();

  for (const tradition of traditions) {
    const key = tradition.category;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(tradition);
  }

  return [...grouped.entries()]
    .sort(([left], [right]) => getBandIndex(left) - getBandIndex(right) || left.localeCompare(right))
    .map(([category, items]) => ({
      id: slugify(category),
      title: category,
      items: [...items].sort((left, right) => left.originTime - right.originTime || left.name.localeCompare(right.name))
    }));
}

export function getSynchronologyLayout(tradition, pixelsPerYear = 0.42) {
  const start = Math.max(TIMELINE_START, tradition.originTime);
  const end = Math.min(TIMELINE_END, getTraditionEndYear(tradition));
  const left = Math.round((start - TIMELINE_START) * pixelsPerYear);
  const width = Math.max(32, Math.round((end - start) * pixelsPerYear));

  return { left, width, start, end };
}

function getBandIndex(category) {
  const index = BAND_ORDER.indexOf(category);
  return index === -1 ? BAND_ORDER.length : index;
}

function slugify(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}
