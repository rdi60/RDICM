/** Capitalize the first letter of ordinary sentences, preserving remaining case.
 * Do not apply to clinical notes, usernames, email, passwords, IDs or codes.
 */
export function sentenceCase(value) {
  if (typeof value !== 'string') return value;
  return value.replace(/(^|[.!?]\s+)(\s*)([a-z])/g, (_, boundary, gap, letter) => boundary + gap + letter.toUpperCase());
}
/** Human-friendly display only; never changes the stored identifier. */
export function displayLabel(value) {
  return typeof value === 'string' ? sentenceCase(value) : value;
}

