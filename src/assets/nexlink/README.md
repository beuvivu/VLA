# Nexlink shell reference assets

Source: https://nexlink.layoutdrop.com/demo/index.html, captured 26 September 2026.
These assets implement the owner's explicit request to use the exact Nexlink
left icon rail and header, replacing the previous Lucide approximation.

- Eleven rail SVGs and six header SVGs preserve all source paths, primitives,
  opacity and dimensions. Whitespace is normalized; the renderer resolves the
  original Bootstrap color tokens against the shared shell's theme.
- Expanded navigation and search use the original UIcons 2.4.2 Regular Rounded
  glyph outlines from the Flaticon font bundled with the reference. FontTools
  SVGPathPen converts them without simplifying geometry. Original em size: 300;
  ascent: 300; descent: 0. No icon font is loaded at runtime.
- Brand and avatar are the exact reference assets. The header retains the
  application's own labels and links to existing pages.
- Instrument Sans is bundled locally in weights 400, 600 and 700. Its OFL is
  included in `InstrumentSans-OFL.txt` and published with the font files.

`provenance.json` records sources and SHA-256 hashes. Assets belong to their
respective authors (Nexlink/LayoutDrop, Flaticon, Instrument Sans contributors);
no ownership or alternate license is asserted here.

`tests/test_nexlink_shell.py` checks vector geometry and the complete rail order.
The shared browser check exercises the header menus at desktop and phone widths.
