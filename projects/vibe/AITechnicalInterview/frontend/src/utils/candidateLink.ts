/** Ссылка кандидату — из origin, с которого открыта админка (quick tunnel и т.д.). */
export function buildCandidateLink(accessToken: string, origin?: string): string {
  const base = (origin ?? (typeof window !== "undefined" ? window.location.origin : "")).replace(
    /\/$/,
    ""
  );
  return `${base}/interview/${accessToken}`;
}

export function isLocalAdminOrigin(origin: string): boolean {
  try {
    const h = new URL(origin).hostname;
    return h === "localhost" || h === "127.0.0.1";
  } catch {
    return false;
  }
}
