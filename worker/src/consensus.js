// Bản JS của `src/sources.py::source_consensus_partial`.
// Xem đầu `prize_map.js` để biết vì sao tồn tại bản thứ hai và chốt chặn nào
// giữ hai bản khỏi trôi lệch.

import {
  EXPECTED_COUNTS,
  PRIZE_ORDER,
  emptyPrizeMap,
  validPrizeToken,
} from "./prize_map.js";

// Bảng này phải khớp TỪNG MỤC với `SOURCE_INDEPENDENCE_GROUP` trong
// `src/sources.py`. Nó ánh xạ MỌI nguồn chứ không chỉ hai bản sao — bỏ sót
// một mục nào thì `support_groups` của ô ấy trả về tên miền đầy đủ thay vì
// khoá nhóm, và bản JS lệch bản Python ngay ở siêu dữ liệu xác minh.
//
// www.minhngoc.net.vn và xosominhngoc.com là hai tên miền cùng thương hiệu
// Minh Ngọc nên tính là MỘT nhà cung cấp độc lập. Đếm chúng là hai sẽ cho một
// nguồn duy nhất quyền tự xác minh chính mình.
const SOURCE_INDEPENDENCE_GROUP = {
  "xoso.com.vn": "xoso",
  "mketqua.net": "mketqua",
  "www.minhngoc.net.vn": "minhngoc",
  "xosominhngoc.com": "minhngoc",
  "xosodaiphat.com": "xosodaiphat",
  "hainhay.net": "hainhay",
  "xskt.vn": "xskt",
};

export function sourceIndependenceKey(sourceName) {
  return SOURCE_INDEPENDENCE_GROUP[sourceName] ?? sourceName;
}

/**
 * Gộp các bảng giải từng ô một theo ưu tiên nguồn cộng đồng thuận.
 *
 * Một giá trị chỉ được coi là ĐÃ XÁC MINH khi có >= `minAgreement` NHÓM nguồn
 * độc lập ủng hộ và không giá trị nào khác có đúng bằng ấy nhóm ủng hộ. Ngoài
 * ra, quan sát của nguồn ưu tiên cao nhất có thể được hiển thị tạm nhưng
 * không bao giờ được đánh dấu đã xác minh.
 *
 * `partials` là mảng [tênNguồn, bảngGiải] và THỨ TỰ CHÍNH LÀ ƯU TIÊN.
 */
export function sourceConsensusPartial(partials, { minAgreement = 2 } = {}) {
  if (!Number.isInteger(minAgreement) || minAgreement < 1) {
    throw new Error("minAgreement must be an integer >= 1");
  }

  const merged = emptyPrizeMap();
  const slotMeta = {};
  const conflicts = [];
  let verifiedSlots = 0;
  let totalSlots = 0;
  for (const key of PRIZE_ORDER) totalSlots += EXPECTED_COUNTS[key];

  for (const key of PRIZE_ORDER) {
    for (let idx = 0; idx < EXPECTED_COUNTS[key]; idx += 1) {
      const values = [];
      for (const [sourceName, prizeMap] of partials) {
        const vals = (prizeMap && prizeMap[key]) || [];
        if (idx < vals.length) {
          const token = validPrizeToken(vals[idx], key);
          if (token !== null) values.push([sourceName, token]);
        }
      }

      // Map giữ thứ tự chèn, khớp với defaultdict của Python khi xếp hạng.
      const counts = new Map();
      for (const [sourceName, value] of values) {
        if (!counts.has(value)) counts.set(value, []);
        counts.get(value).push(sourceName);
      }

      let chosen = "";
      let support = [];
      let supportGroups = [];
      let ambiguousTie = false;

      if (counts.size > 0) {
        const scoreOf = (names) => {
          const groups = new Set(names.map(sourceIndependenceKey));
          let firstPriority = Infinity;
          for (let i = 0; i < values.length; i += 1) {
            if (names.includes(values[i][0])) { firstPriority = i; break; }
          }
          // Phần tử thứ ba (ưu tiên nguồn) là mã BẤT KHẢ ĐẠT với bộ nguồn
          // hiện tại, và điều đó đã được ĐO chứ không suy luận suông.
          //
          // Nó chỉ được hỏi tới khi hai giá trị bằng nhau cả số nhóm lẫn số
          // nguồn. Nhưng bằng nhau về số nhóm kéo theo
          // `runnerUpGroups === bestGroups.length`, tức `ambiguousTie`, và khi
          // ấy kết quả rơi về `values[0]` chứ không dùng `ranked[0]` nữa.
          // Đo trên 9 630 ô sinh ngẫu nhiên: 0 ô mà nhánh này phân định.
          //
          // Tương tự, đảo thứ tự `groups.size` với `names.length` cũng không
          // đổi kết quả: muốn khác nhau thì phải có một nhóm gồm >= 3 nguồn,
          // mà nhóm lớn nhất hiện nay là cặp minhngoc chỉ có 2.
          //
          // Giữ nguyên cả hai để khớp `src/sources.py` từng dòng — phép kiểm
          // đối chiếu không phân biệt được chúng, nên ở đây tài liệu mới là
          // chốt chặn, không phải phép kiểm.
          return [groups.size, names.length, -firstPriority];
        };

        // Python: sorted(..., reverse=True) là sắp GIẢM DẦN nhưng VẪN ỔN ĐỊNH —
        // hoà điểm thì giữ thứ tự chèn. Array.sort của JS cũng ổn định từ
        // ES2019, nên chỉ cần so ngược là khớp cách phá hoà.
        const ranked = [...counts.entries()].sort((a, b) => {
          const sa = scoreOf(a[1]);
          const sb = scoreOf(b[1]);
          for (let i = 0; i < 3; i += 1) {
            if (sb[i] !== sa[i]) return sb[i] - sa[i];
          }
          return 0;
        });

        const [bestValue, bestSources] = ranked[0];
        const bestGroups = [...new Set(bestSources.map(sourceIndependenceKey))];

        if (ranked.length > 1) {
          const runnerUpGroups = new Set(ranked[1][1].map(sourceIndependenceKey)).size;
          ambiguousTie = bestGroups.length >= minAgreement
            && runnerUpGroups === bestGroups.length;
        }

        if (bestGroups.length >= minAgreement && !ambiguousTie) {
          chosen = bestValue;
          support = bestSources;
          supportGroups = bestGroups;
          verifiedSlots += 1;
        } else {
          // Rơi về nguồn ưu tiên cao nhất CHỈ để hiển thị. Thế giằng 2-2 với
          // số nhóm bằng nhau không bao giờ được coi là đã xác minh.
          chosen = values[0][1];
          support = [values[0][0]];
          supportGroups = [sourceIndependenceKey(values[0][0])];
        }
        if (counts.size > 1) conflicts.push(`${key}[${idx}]`);
      }

      if (chosen) merged[key].push(chosen);
      const observations = {};
      for (const [value, names] of counts.entries()) observations[value] = names;
      slotMeta[`${key}[${idx}]`] = {
        value: chosen || null,
        verified: supportGroups.length >= minAgreement && !ambiguousTie,
        ambiguous_tie: ambiguousTie,
        support,
        support_groups: supportGroups,
        observations,
      };
    }
  }

  let received = 0;
  for (const key of PRIZE_ORDER) received += merged[key].length;

  return [merged, {
    received_slots: received,
    total_slots: totalSlots,
    verified_slots: verifiedSlots,
    conflicts,
    slot_meta: slotMeta,
  }];
}
