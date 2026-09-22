"""New calibration metadata must not leak raw keys into visible cards."""

import json

from bs4 import BeautifulSoup

from build_dashboard import main


def test_calibration_selection_is_localized_without_changing_raw_evidence(tmp_path, monkeypatch):
    payload = {
        "component_availability_required": True,
        "selection": {
            "chosen": "parametric", "selected": False,
            "fit_days": 20, "holdout_days": 0,
        },
    }
    source = tmp_path / "data" / "ensemble" / "calibration_loto.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["--docs-dir", "docs"])
    soup = BeautifulSoup((tmp_path / "docs/dashboard.html").read_text(), "html.parser")
    evidence = [json.loads(node.get_text()) for node in soup.select("details pre")]
    assert payload in evidence
    for details in soup.find_all("details"):
        details.decompose()
    visible = soup.get_text(" ", strip=True)
    for token in ("component_availability_required", "selection", "chosen", "selected",
                  "fit_days", "holdout_days", "parametric"):
        assert token not in visible, f"untranslated calibration field: {token}"
    assert "20" in visible
    assert json.loads(source.read_text()) == payload
