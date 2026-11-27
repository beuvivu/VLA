import {
  EXPECTED_COUNTS,
  PRIZE_ORDER,
  emptyPrizeMap,
  validPrizeToken,
} from "./prize_map.js";

const SOURCE_INDEPENDENCE_GROUP = {
  "xoso.com.vn": "xoso",
  "mketqua.net": "mketqua",
  "www.minhngoc.net.vn": "minhngoc",
};

export function sourceIndependenceKey(sourceName) {
  return SOURCE_INDEPENDENCE_GROUP[sourceName] ?? sourceName;
}

export function sourceConsensusPartial(partials, { minAgreement = 1 } = {}) {
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
          return [groups.size, names.length, -firstPriority];
        };

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
