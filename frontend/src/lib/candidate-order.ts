/** Rank only available point scores (plus any availability bonus). Unknowns are not treated as zero. */
export function sortForReview<T extends { rank: number | null; name: string }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => {
    if (a.rank !== null && b.rank !== null) return b.rank - a.rank || a.name.localeCompare(b.name);
    if (a.rank !== null) return -1;
    if (b.rank !== null) return 1;
    return a.name.localeCompare(b.name);
  });
}
