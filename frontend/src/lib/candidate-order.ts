/** Rank only available point scores. Unknowns are not treated as zero. */
export function sortByMatchScore<T extends { score: number | null; name: string }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => {
    if (a.score !== null && b.score !== null) return b.score - a.score || a.name.localeCompare(b.name);
    if (a.score !== null) return -1;
    if (b.score !== null) return 1;
    return a.name.localeCompare(b.name);
  });
}
