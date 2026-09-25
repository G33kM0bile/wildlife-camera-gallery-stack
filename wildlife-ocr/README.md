# Wildlife camera temperature OCR

`temperature_parser.py` contains the hardened parser used by the live
`wildlife-ocr.service`. Suntek camera footers print both Celsius and Fahrenheit,
so the parser validates the pair instead of depending on Tesseract recognizing
the tiny degree, C and F glyphs.

Handled examples include `6/42`, `87/46 F`, `67/42`, `9/485`, `26°%/78F` and
`10TC/50F`. A value is accepted only when the two units agree within 4 °F.
This prevents OCR artifacts such as 67 °C from becoming temperature spikes.

Run the parser tests with:

```bash
python3 -m unittest discover -s wildlife-ocr/tests -v
```

The Grafana dashboard additionally limits displayed camera temperatures to
the physically plausible range -40–40 °C. That hides old bad OCR points without
deleting historical InfluxDB data.
