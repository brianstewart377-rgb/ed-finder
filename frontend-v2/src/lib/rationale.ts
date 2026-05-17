export function displayRationale(rationale?: string | null): string | null {
  if (!rationale) return null;
  let text = rationale;
  text = text.replace(
    /Strong Refinery;\s*via\s*([^;]*?)(?=(?:;|$))/i,
    'Strong Refinery; rationale uses an older format and may cite legacy contributors; rebuild this system rating to refresh this rationale',
  );
  text = text.replace(
    /Industrial\s+via\s+[^;]*ELW[^;]*/gi,
    'Industrial factors should come from icy, rocky-ice, gas giant, geological, or support-facility signals',
  );
  text = text.replace(
    /Military\s+via\s+[^;]*ELW[^;]*/gi,
    'Military factors include main-star/body inheritance, landable support, and mixed ELW value',
  );
  if (/ELW/i.test(text) && /Military/i.test(text) && !/mixed/i.test(text)) {
    text += ' Caveat: ELWs add mixed economy value including Military, Agriculture, High Tech and Tourism.';
  }
  return text;
}
