// Bản JS của `src/sources.py::extract_partial_prize_map`.
//
// VÌ SAO CÓ BẢN THỨ HAI
// =====================
// Worker chạy trên nền JavaScript nên không dùng lại được bản Python. Hai bản
// cùng một logic là nợ kỹ thuật thật, không phải chuyện nhỏ: chúng sẽ trôi
// lệch nhau, và lệch ở đây nghĩa là trang live hiển thị một dãy số khác với
// dãy được ghi vào lịch sử.
//
// Chốt chặn là `tests/test_worker_parser_parity.py`: nó chạy CẢ HAI bản trên
// cùng một bộ mẫu HTML và đòi kết quả giống hệt nhau, từng ký tự. Sửa một bản
// mà quên bản kia thì phép kiểm đỏ ngay.
//
// Những chỗ bản Python dựa vào BeautifulSoup mà bản này phải mô phỏng lại,
// đều đo được trên chính bs4 và ghi rõ ngay tại chỗ.

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

// --- Chuẩn hoá nhãn --------------------------------------------------------

// Python: NFKD -> bỏ dấu tổ hợp -> Đ/đ thành D/d -> viết thường -> cắt lề.
// Đ (U+0110) KHÔNG tự phân rã qua NFKD nên phải thay tay; đó là lý do bản
// Python có đúng hai dòng replace ấy chứ không phải thừa.
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

// --- Bóc số ----------------------------------------------------------------

// Python dùng `(?<!\w)[0-9]{n}(?!\w)`, và `\w` của Python trên chuỗi str là
// Unicode: nó khớp cả chữ số toàn phần như "１". Vì thế `\w` của JS (chỉ ASCII)
// KHÔNG tương đương — phải viết lại bằng thuộc tính Unicode, nếu không một
// chuỗi như "１12345２" sẽ lọt qua ở bản JS mà bị chặn ở bản Python.
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

// --- HTML thành các dòng văn bản -------------------------------------------

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

// Mô phỏng `BeautifulSoup(html,"lxml").get_text("\n", strip=True)`.
//
// Ba hành vi đo được trên chính bs4, không phải phỏng đoán:
//   1. Nội dung <script>/<style> BỊ LOẠI (bs4 >= 4.9 xếp chúng ngoài get_text).
//   2. Chú thích <!-- --> bị loại.
//   3. Mỗi nút văn bản là MỘT dòng riêng. "ĐB<span>837</span>72" ra ba dòng
//      chứ không phải "ĐB83772" — nên "837" và "72" không dính lại thành một
//      giải năm chữ số. Thay mọi thẻ bằng xuống dòng cho đúng hành vi ấy.
export function htmlToLines(html) {
  let text = String(html || "");
  text = text.replace(/<!--[\s\S]*?-->/g, "");
  // Nhánh `[\s\S]*$` xử lý thẻ script/style không đóng: bỏ tới hết chuỗi thay
  // vì để nguyên cả khối mã lọt vào phần văn bản.
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

// --- Bóc khối giải ---------------------------------------------------------

export function extractPartialPrizeMap(html) {
  const lines = htmlToLines(html);
  if (lines.length === 0) return emptyPrizeMap();

  const labels = [];
  lines.forEach((line, idx) => {
    const key = labelKey(line);
    if (key !== null) labels.push([idx, key]);
  });
  if (labels.length === 0) return emptyPrizeMap();

  // Trang thật lặp lại nhãn giải ở menu và bảng thống kê. Chấm điểm mọi khối
  // bắt đầu bằng nhãn đặc biệt rồi giữ khối đầy đủ nhất và đúng thứ tự nhất.
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
      if (keyOrder < seenOrder) break;  // một bảng khác đã bắt đầu
      seenOrder = Math.max(seenOrder, keyOrder);
      const nextIdx = pos + 1 < labels.length
        ? labels[pos + 1][0]
        : Math.min(lines.length, lineIdx + 10);
      const chunk = lines.slice(lineIdx, nextIdx).join(" ");
      const values = validTokens(chunk, key);
      if (values.length > 0) prizeMap[key] = values.slice(0, EXPECTED_COUNTS[key]);
      if (key === "prize7") break;
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

  // `max()` của Python giữ phần tử ĐẦU TIÊN khi hoà điểm. So sánh phải chặt
  // (">") để giữ đúng cách phá hoà ấy.
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
