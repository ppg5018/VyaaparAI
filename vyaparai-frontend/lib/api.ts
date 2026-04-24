const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── Types ─────────────────────────────────────────────────────────────────────
export type Band = 'healthy' | 'watch' | 'at_risk';

export interface Business {
  id: string;
  name: string;
  place_id: string;
  category: string;
  owner_name: string;
}

export interface Review {
  rating: number;
  text: string;
  relative_time: string;
}

export interface Competitor {
  name: string;
  rating: number;
  review_count: number;
}

export interface HealthReport {
  business_id: string;
  business_name: string;
  final_score: number;
  band: Band;
  sub_scores: { review_score: number; competitor_score: number; pos_score: number };
  google_rating: number;
  total_reviews: number;
  reviews: Review[];
  competitors: Competitor[];
  insights: [string, string, string];
  action: string;
  generated_at: string;
}

export interface HistoryEntry {
  final_score: number;
  review_score: number;
  competitor_score: number;
  pos_score: number;
  google_rating: number;
  insights: [string, string, string];
  action: string;
  created_at: string;
}

// ─── API functions ──────────────────────────────────────────────────────────────
export interface PlaceSuggestion {
  place_id: string;
  name: string;
  address: string;
}

export async function searchPlaces(q: string): Promise<PlaceSuggestion[]> {
  const res = await fetch(`${BASE}/search-places?q=${encodeURIComponent(q)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.suggestions ?? [];
}

export async function onboardBusiness(data: {
  name: string;
  place_id?: string;
  category: string;
  owner_name: string;
}): Promise<{ business_id: string; name: string; place_id: string; google_verified_name: string }> {
  const res = await fetch(`${BASE}/onboard`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (res.status === 409) {
    const body = await res.json();
    return { business_id: body.detail.business_id, name: data.name, place_id: data.place_id ?? '', google_verified_name: data.name };
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function generateReport(businessId: string): Promise<HealthReport> {
  const res = await fetch(`${BASE}/generate-report/${businessId}`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getHistory(
  businessId: string,
  limit = 12,
): Promise<{ business_id: string; count: number; scores: HistoryEntry[] }> {
  const res = await fetch(`${BASE}/history/${businessId}?limit=${limit}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadPOS(
  businessId: string,
  file: File,
): Promise<{ business_id: string; rows_inserted: number; status: string }> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload-pos/${businessId}`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
