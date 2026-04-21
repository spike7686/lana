const UTC8_OFFSET_MS = 8 * 60 * 60 * 1000;

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function formatUtc8Ms(ms: number, withZone: boolean): string {
  const shifted = new Date(ms + UTC8_OFFSET_MS);
  const y = shifted.getUTCFullYear();
  const m = pad2(shifted.getUTCMonth() + 1);
  const d = pad2(shifted.getUTCDate());
  const hh = pad2(shifted.getUTCHours());
  const mm = pad2(shifted.getUTCMinutes());
  const ss = pad2(shifted.getUTCSeconds());
  return withZone ? `${y}-${m}-${d} ${hh}:${mm}:${ss} UTC+8` : `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}

export function formatUtc8(value: string): string {
  return formatUtc8Ms(new Date(value).getTime(), true);
}

export function formatUnixSecondsUtc8(seconds: number): string {
  return formatUtc8Ms(seconds * 1000, true);
}

export function formatUnixSecondsUtc8Tick(seconds: number): string {
  const shifted = new Date(seconds * 1000 + UTC8_OFFSET_MS);
  const m = pad2(shifted.getUTCMonth() + 1);
  const d = pad2(shifted.getUTCDate());
  const hh = pad2(shifted.getUTCHours());
  const mm = pad2(shifted.getUTCMinutes());
  return `${m}-${d} ${hh}:${mm}`;
}

