if (new URLSearchParams(location.search).get("demo") === "1") {
  window.__D_DEMO_DRAWS__ = Array.from({length: 45}, (_, day) => {
    const n = [];
    [0, 1, 2, 3, 4, 5].forEach((count, index) => {
      for (let k = 0; k < count; k++) n.push(String(index).padStart(2, "0"));
    });
    while (n.length < 27) n.push(String(60 + ((day * 7 + n.length * 3) % 39)).padStart(2, "0"));
    const special = day % 2 ? "03" : "04";
    const index = n.indexOf(special);
    [n[0], n[index]] = [n[index], n[0]];
    return {d: new Date(Date.UTC(2026, 0, day + 1)).toISOString().slice(0, 10), s: "123" + special, n};
  });
}
