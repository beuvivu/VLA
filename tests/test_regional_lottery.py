from datetime import date

from regional_lottery import parse_xskt_html


SAMPLE = """
<table>
<tr><th>05/10</th><th>Thừa Thiên Huế</th><th>Phú Yên</th></tr>
<tr><td>G.8</td><td>32</td><td>72</td></tr>
<tr><td>G.7</td><td>709</td><td>310</td></tr>
<tr><td>G.6</td><td>7306<br>5631<br>5808</td><td>2280<br>1256<br>2587</td></tr>
<tr><td>G.5</td><td>4366</td><td>0107</td></tr>
<tr><td>G.4</td><td>95101<br>34116<br>92655<br>35498<br>87124<br>62137<br>69034</td><td>53512<br>21300<br>89212<br>45173<br>25196<br>72586<br>65817</td></tr>
<tr><td>G.3</td><td>73217<br>56441</td><td>80504<br>76581</td></tr>
<tr><td>G.2</td><td>82982</td><td>45402</td></tr>
<tr><td>G.1</td><td>88389</td><td>74244</td></tr>
<tr><td>ĐB</td><td>921241</td><td>918260</td></tr>
</table>
"""


def test_parse_xskt_regional_table_preserves_leading_zeroes():
    rows = parse_xskt_html(SAMPLE, region="mt", selected_date=date(2026, 10, 5))
    assert len(rows) == 36
    assert {r.province for r in rows} == {"Thừa Thiên Huế", "Phú Yên"}
    assert any(r.prize == "G.5" and r.province == "Phú Yên" and r.value == "0107" for r in rows)
    assert any(r.prize == "ĐB" and r.value == "921241" for r in rows)


def test_parser_rejects_incomplete_table():
    broken = SAMPLE.replace("<td>921241</td>", "<td></td>")
    assert parse_xskt_html(broken, region="mt", selected_date=date(2026, 10, 5)) == []
