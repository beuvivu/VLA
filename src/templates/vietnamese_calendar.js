/* Phần tính sóc được chuyển thể từ astronomia (Meeus chương 49).
The MIT License (MIT)

Copyright (c) 2013 Sonia Keys
Copyright (c) 2016 Commenthol

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
*/
/* Lịch Việt Nam UTC+7. Công thức thiên văn và tài liệu đối chiếu nằm trong
   documentation/architecture/vietnamese-calendar.md. Không dùng lịch Trung Quốc. */
(function (root) {
  'use strict';
  const MIN_YEAR = 1900, MAX_YEAR = 2099, ZONE = 7 / 24;
  const DAY_MS = 86400000, SYNODIC = 29.530588853;
  const STEMS = ['Giáp', 'Ất', 'Bính', 'Đinh', 'Mậu', 'Kỷ', 'Canh', 'Tân', 'Nhâm', 'Quý'];
  const BRANCHES = ['Tý', 'Sửu', 'Dần', 'Mão', 'Thìn', 'Tỵ', 'Ngọ', 'Mùi', 'Thân', 'Dậu', 'Tuất', 'Hợi'];
  const TERMS = ['Xuân phân', 'Thanh minh', 'Cốc vũ', 'Lập hạ', 'Tiểu mãn', 'Mang chủng',
    'Hạ chí', 'Tiểu thử', 'Đại thử', 'Lập thu', 'Xử thử', 'Bạch lộ', 'Thu phân', 'Hàn lộ',
    'Sương giáng', 'Lập đông', 'Tiểu tuyết', 'Đại tuyết', 'Đông chí', 'Tiểu hàn', 'Đại hàn', 'Lập xuân', 'Vũ thủy', 'Kinh trập'];
  const SOLAR_HOLIDAYS = { '1-1': 'Tết Dương lịch', '3-8': 'Quốc tế Phụ nữ', '4-30': 'Ngày Thống nhất',
    '5-1': 'Quốc tế Lao động', '6-1': 'Quốc tế Thiếu nhi', '9-2': 'Quốc khánh',
    '10-20': 'Phụ nữ Việt Nam', '11-20': 'Nhà giáo Việt Nam', '12-25': 'Giáng sinh' };
  const LUNAR_HOLIDAYS = { '1-1': 'Tết Nguyên đán', '1-2': 'Mùng 2 Tết', '1-3': 'Mùng 3 Tết',
    '1-15': 'Tết Nguyên tiêu', '3-3': 'Tết Hàn thực', '3-10': 'Giỗ Tổ Hùng Vương',
    '4-15': 'Lễ Phật đản', '5-5': 'Tết Đoan ngọ', '7-15': 'Lễ Vu lan',
    '8-15': 'Tết Trung thu', '12-23': 'Ông Công Ông Táo' };
  const mod = (n, divisor) => ((n % divisor) + divisor) % divisor;
  const sin = degrees => Math.sin(degrees * Math.PI / 180);
  const moonCache = new Map(), anchorCache = new Map(), dayCache = new Map();

  function parseDate(iso) {
    if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
    const [year, month, day] = iso.split('-').map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    if (year < MIN_YEAR || year > MAX_YEAR || date.toISOString().slice(0, 10) !== iso) return null;
    return { year, month, day, weekday: date.getUTCDay(), jd: date.getTime() / DAY_MS + 2440588 };
  }

  function deltaT(year) {
    const polynomial = (x, coefficients) => coefficients.reduceRight((value, n) => value * x + n, 0);
    if (year < 1900) return polynomial(year - 1860, [7.62, 0.5737, -0.251754, 0.01680668, -0.0004473624, 1 / 233174]);
    if (year < 1920) return polynomial(year - 1900, [-2.79, 1.494119, -0.0598939, 0.0061966, -0.000197]);
    if (year < 1941) return polynomial(year - 1920, [21.2, 0.84493, -0.0761, 0.0020936]);
    if (year < 1961) return polynomial(year - 1950, [29.07, 0.407, -1 / 233, 1 / 2547]);
    if (year < 1986) return polynomial(year - 1975, [45.45, 1.067, -1 / 260, -1 / 718]);
    if (year < 2005) return polynomial(year - 2000, [63.86, 0.3345, -0.060374, 0.0017275, 0.000651814, 0.00002373599]);
    if (year < 2050) return polynomial(year - 2000, [62.92, 0.32217, 0.005589]);
    return -20 + 32 * ((year - 1820) / 100) ** 2 - 0.5628 * (2150 - year);
  }

  function newMoon(cycle) {
    if (moonCache.has(cycle)) return moonCache.get(cycle);
    // Meeus chương 49, đủ các số hạng nhiễu loạn; chuyển TT sang UT trước khi lấy ngày.
    const k = cycle - 1237, t = k / 1236.85, t2 = t * t, t3 = t2 * t, t4 = t3 * t;
    const mean = 2451550.09766 + 29.530588861 * k + 0.00015437 * t2 - 0.00000015 * t3 + 0.00000000073 * t4;
    const e = 1 - 0.002516 * t - 0.0000074 * t2;
    const m = 2.5534 + 29.1053567 * k - 0.0000014 * t2 - 0.00000011 * t3;
    const p = 201.5643 + 385.81693528 * k + 0.0107582 * t2 + 0.00001238 * t3 - 0.000000058 * t4;
    const f = 160.7108 + 390.67050284 * k - 0.0016118 * t2 - 0.00000227 * t3 + 0.000000011 * t4;
    const omega = 124.7746 - 1.56375588 * k + 0.0020672 * t2 + 0.00000215 * t3;
    const terms = [
      [-0.4072, p], [0.17241 * e, m], [0.01608, 2 * p], [0.01039, 2 * f],
      [0.00739 * e, p - m], [-0.00514 * e, p + m], [0.00208 * e * e, 2 * m],
      [-0.00111, p - 2 * f], [-0.00057, p + 2 * f], [0.00056 * e, 2 * p + m],
      [-0.00042, 3 * p], [0.00042 * e, m + 2 * f], [0.00038 * e, m - 2 * f],
      [-0.00024 * e, 2 * p - m], [-0.00017, omega], [-0.00007, p + 2 * m],
      [0.00004, 2 * (p - f)], [0.00004, 3 * m], [0.00003, p + m - 2 * f],
      [0.00003, 2 * (p + f)], [-0.00003, p + m + 2 * f], [0.00003, p - m + 2 * f],
      [-0.00002, p - m - 2 * f], [-0.00002, 3 * p + m], [0.00002, 4 * p],
      [0.000325, 299.77 + 0.107408 * k - 0.009173 * t2], [0.000165, 251.88 + 0.016321 * k],
      [0.000164, 251.83 + 26.651886 * k], [0.000126, 349.42 + 36.412478 * k],
      [0.00011, 84.66 + 18.206239 * k], [0.000062, 141.74 + 53.303771 * k],
      [0.00006, 207.14 + 2.453732 * k], [0.000056, 154.84 + 7.30686 * k],
      [0.000047, 34.52 + 27.261239 * k], [0.000042, 207.19 + 0.121824 * k],
      [0.00004, 291.34 + 1.844379 * k], [0.000037, 161.72 + 24.198154 * k],
      [0.000035, 239.56 + 25.513099 * k], [0.000023, 331.55 + 3.592518 * k],
    ];
    const jde = mean + terms.reduce((sum, [amplitude, angle]) => sum + amplitude * sin(angle), 0);
    const day = Math.floor(jde - deltaT(2000 + k / 12.3685) / 86400 + 0.5 + ZONE);
    moonCache.set(cycle, day);
    return day;
  }

  function longitude(julian) {
    const t = (julian - 2451545) / 36525, t2 = t * t;
    const anomaly = 357.5291 + 35999.0503 * t - 0.0001559 * t2 - 0.00000048 * t2 * t;
    const mean = 280.46645 + 36000.76983 * t + 0.0003032 * t2;
    return mod(mean + (1.9146 - 0.004817 * t - 0.000014 * t2) * sin(anomaly)
      + (0.019993 - 0.000101 * t) * sin(2 * anomaly) + 0.00029 * sin(3 * anomaly), 360);
  }
  const majorTerm = jd => Math.floor(longitude(jd - 0.5 - ZONE) / 30);

  function winterMonth(year) {
    if (anchorCache.has(year)) return anchorCache.get(year);
    const end = Date.UTC(year, 11, 31) / DAY_MS + 2440588;
    const k = Math.floor((end - 2415021) / SYNODIC);
    const first = newMoon(k);
    const start = majorTerm(first) >= 9 ? newMoon(k - 1) : first;
    anchorCache.set(year, start);
    return start;
  }

  function lunarDate(solar) {
    let k = Math.floor((solar.jd - 2415021.076998695) / SYNODIC);
    while (newMoon(k) > solar.jd) k -= 1;
    while (newMoon(k + 1) <= solar.jd) k += 1;
    const start = newMoon(k);
    const winter = winterMonth(solar.year);
    let year = solar.year, before, after;
    if (winter >= start) { before = winterMonth(year - 1); after = winter; }
    else { before = winter; after = winterMonth(year + 1); year += 1; }
    const offset = Math.floor((start - before) / 29);
    let month = offset + 11, leap = false;
    if (after - before > 365) {
      const base = Math.floor((before - 2415021.076998695) / SYNODIC + 0.5);
      let previous = majorTerm(newMoon(base + 1));
      for (let index = 2; index <= 14; index += 1) {
        const current = majorTerm(newMoon(base + index));
        if (current === previous || index === 14) {
          if (offset >= index - 1) { month = offset + 10; leap = offset === index - 1; }
          break;
        }
        previous = current;
      }
    }
    if (month > 12) month -= 12;
    if (month >= 11 && offset < 4) year -= 1;
    return { day: solar.jd - start + 1, month, year, leap };
  }

  function getDay(iso) {
    if (dayCache.has(iso)) return dayCache.get(iso);
    const solar = parseDate(iso);
    if (!solar) return null;
    const lunar = lunarDate(solar);
    const cyclical = (stem, branch) => `${STEMS[mod(stem, 10)]} ${BRANCHES[mod(branch, 12)]}`;
    const branch = mod(solar.jd + 1, 12);
    const hours = [0, 1, 3, 6, 8, 9].map(n => mod(n + 2 * (branch % 6), 12)).sort((a, b) => a - b)
      .map(n => ({ name: BRANCHES[n], range: `${String(mod(n * 2 - 1, 24)).padStart(2, '0')}:00–${String(n * 2 + 1).padStart(2, '0')}:00` }));
    const holidays = [SOLAR_HOLIDAYS[`${solar.month}-${solar.day}`],
      !lunar.leap && LUNAR_HOLIDAYS[`${lunar.month}-${lunar.day}`]].filter(Boolean);
    const startTerm = Math.floor(longitude(solar.jd - 0.5 - ZONE) / 15);
    const endTerm = Math.floor(longitude(solar.jd + 0.5 - ZONE - 1e-7) / 15);
    const result = { iso, solar, lunar, holidays, hours,
      canChi: { day: cyclical(solar.jd + 9, solar.jd + 1),
        month: cyclical(lunar.year * 12 + lunar.month + 3, lunar.month + 1) + (lunar.leap ? ' nhuận' : ''),
        year: cyclical(lunar.year + 6, lunar.year + 8) },
      term: TERMS[endTerm], termChange: startTerm !== endTerm };
    dayCache.set(iso, result);
    return result;
  }

  function todayISO(now = new Date()) {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh',
      year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }
  root.AppVietnameseCalendar = Object.freeze({ getDay, todayISO, MIN_YEAR, MAX_YEAR });
})(globalThis);
