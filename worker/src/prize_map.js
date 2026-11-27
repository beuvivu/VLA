export const PRIZE_ORDER = [
  "special", "prize1", "prize2", "prize3",
  "prize4", "prize5", "prize6", "prize7",
];

export const EXPECTED_COUNTS = {
  special: 1, prize1: 1, prize2: 2, prize3: 6,
  prize4: 4, prize5: 6, prize6: 3, prize7: 4,
};

export const EXPECTED_WIDTHS = {
  special: 5, prize1: 5, prize2: 5, prize3: 5,
  prize4: 4, prize5: 4, prize6: 3, prize7: 2,
};

export function emptyPrizeMap() {
  const out = {};
  for (const key of PRIZE_ORDER) out[key] = [];
  return out;
}

export function asciiFold(value) {
  return String(value)
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .replace(/Đ/g, "D")
    .replace(/đ/g, "d")
    .toLowerCase()
    .trim();
}

const LABEL_PATTERNS = [
  ["special", /^(?:(?:giai|g)[.\s]*)?(?:db|dac\s+biet)\b/],
  ["prize1", /^(?:(?:giai|g)[.\s]*)?(?:nhat|1)\b/],
  ["prize2", /^(?:(?:giai|g)[.\s]*)?(?:nhi|2)\b/],
  ["prize3", /^(?:(?:giai|g)[.\s]*)?(?:ba|3)\b/],
  ["prize4", /^(?:(?:giai|g)[.\s]*)?(?:tu|4)\b/],
  ["prize5", /^(?:(?:giai|g)[.\s]*)?(?:nam|5)\b/],
  ["prize6", /^(?:(?:giai|g)[.\s]*)?(?:sau|6)\b/],
  ["prize7", /^(?:(?:giai|g)[.\s]*)?(?:bay|7)\b/],
];

export function labelKey(line) {
  const folded = asciiFold(line);
  for (const [key, pattern] of LABEL_PATTERNS) {
    if (pattern.test(folded)) return key;
  }
  return null;
}

const WORD_CHAR = "[\\p{L}\\p{N}_]";

export function validTokens(text, key) {
  const width = EXPECTED_WIDTHS[key];
  const pattern = new RegExp(
    `(?<!${WORD_CHAR})[0-9]{${width}}(?!${WORD_CHAR})`,
    "gu",
  );
  return String(text).match(pattern) || [];
}

export function validPrizeToken(value, key) {
  const token = String(value).trim();
  const width = EXPECTED_WIDTHS[key];
  return new RegExp(`^[0-9]{${width}}$`).test(token) ? token : null;
}

const LINE_TOKEN = /[0-9]+|[^\s0-9,;|]+/gu;

export function valueLineTokens(line, key) {
  const width = EXPECTED_WIDTHS[key];
  const values = [];
  for (const token of String(line).match(LINE_TOKEN) || []) {
    if (!/^[0-9]+$/.test(token) || token.length !== width) return null;
    values.push(token);
  }
  return values;
}

export function prizeRowValues(lines, labelIdx, stopIdx, key) {
  const values = validTokens(lines[labelIdx], key).slice();
  for (let idx = labelIdx + 1; idx < stopIdx; idx += 1) {
    const row = valueLineTokens(lines[idx], key);
    if (row === null) break;
    values.push(...row);
  }
  return values.slice(0, EXPECTED_COUNTS[key]);
}

const NAMED_ENTITIES = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'",
  nbsp: " ", ndash: "–", mdash: "—",
  hellip: "…", laquo: "«", raquo: "»",
  ldquo: "“", rdquo: "”", lsquo: "‘", rsquo: "’",
  bull: "•", middot: "·", times: "×", deg: "°",
};

export function decodeEntities(text) {
  return String(text).replace(
    /&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g,
    (match, body) => {
      if (body[0] === "#") {
        const code = body[1] === "x" || body[1] === "X"
          ? parseInt(body.slice(2), 16)
          : parseInt(body.slice(1), 10);
        if (!Number.isFinite(code) || code < 0 || code > 0x10ffff) return match;
        try { return String.fromCodePoint(code); } catch { return match; }
      }
      const named = NAMED_ENTITIES[body.toLowerCase()];
      return named === undefined ? match : named;
    },
  );
}

export function htmlToLines(html) {
  let text = String(html || "");
  text = text.replace(/<!--[\s\S]*?-->/g, "");
  text = text.replace(
    /<(script|style)\b[^>]*>(?:[\s\S]*?<\/\1\s*>|[\s\S]*$)/gi,
    "\n",
  );
  text = text.replace(/<[^>]*>/g, "\n");
  text = decodeEntities(text);
  return text
    .split("\n")
    .map((line) => line.replace(/\s+/gu, " ").trim())
    .filter((line) => line.length > 0);
}

export function extractPartialPrizeMap(html) {
  const lines = htmlToLines(html);
  if (lines.length === 0) return emptyPrizeMap();

  const labels = [];
  lines.forEach((line, idx) => {
    const key = labelKey(line);
    if (key !== null) labels.push([idx, key]);
  });
  if (labels.length === 0) return emptyPrizeMap();

  let specialPositions = [];
  labels.forEach(([, key], n) => { if (key === "special") specialPositions.push(n); });
  if (specialPositions.length === 0) specialPositions = [0];

  const candidates = [];
  for (const labelPos of specialPositions) {
    const prizeMap = emptyPrizeMap();
    let seenOrder = -1;
    for (let pos = labelPos; pos < labels.length; pos += 1) {
      const [lineIdx, key] = labels[pos];
      const keyOrder = PRIZE_ORDER.indexOf(key);
      if (pos > labelPos && key === "special") break;
      if (keyOrder < seenOrder) break;
      seenOrder = Math.max(seenOrder, keyOrder);
      const nextIdx = pos + 1 < labels.length ? labels[pos + 1][0] : lines.length;
      const values = prizeRowValues(lines, lineIdx, nextIdx, key);
      if (values.length > 0) prizeMap[key] = values;
      const nextKey = pos + 1 < labels.length ? labels[pos + 1][1] : null;
      if (key === "prize7" && (prizeMap.prize7.length > 0 || nextKey !== "prize7")) break;
    }
    candidates.push(prizeMap);
  }

  const score = (candidate) => {
    let received = 0;
    let complete = 0;
    for (const key of PRIZE_ORDER) {
      received += candidate[key].length;
      if (candidate[key].length === EXPECTED_COUNTS[key]) complete += 1;
    }
    return [received, complete];
  };

  let best = candidates[0];
  let bestScore = score(best);
  for (let i = 1; i < candidates.length; i += 1) {
    const current = score(candidates[i]);
    if (current[0] > bestScore[0]
      || (current[0] === bestScore[0] && current[1] > bestScore[1])) {
      best = candidates[i];
      bestScore = current;
    }
  }
  return best;
}
