export function runTraditionQuery(traditions, rawQuery) {
  const query = rawQuery.trim().toLowerCase();

  if (!query) {
    return {
      results: traditions,
      summary: `Showing all ${traditions.length} traditions.`
    };
  }

  if (query.includes("outside vedic")) {
    const results = traditions.filter((item) => item.vedicRelation === "outside");
    return {
      results,
      summary: `Showing ${results.length} traditions outside the Vedic system.`
    };
  }

  if (query.includes("bhakti")) {
    const results = traditions.filter((item) => item.category === "bhakti movements");
    return {
      results,
      summary: `Showing ${results.length} bhakti movement records.`
    };
  }

  const tamilakamMatch = query.includes("tamilakam");
  if (tamilakamMatch) {
    const results = traditions.filter(
      (item) =>
        item.geographicOrigin.toLowerCase().includes("tamilakam") ||
        item.regions.some((region) => region.toLowerCase().includes("tamilakam"))
    );
    return {
      results,
      summary: `Showing ${results.length} traditions connected to Tamilakam.`
    };
  }

  const categoryMatches = traditions.filter((item) =>
    item.category.toLowerCase().includes(query)
  );
  if (categoryMatches.length > 0) {
    return {
      results: categoryMatches,
      summary: `Showing ${categoryMatches.length} traditions matching "${rawQuery}".`
    };
  }

  return {
    results: traditions,
    summary: `No direct parser rule for "${rawQuery}". Showing the full dataset.`
  };
}
