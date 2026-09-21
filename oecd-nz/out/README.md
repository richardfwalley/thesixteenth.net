# Results land here

This folder is **tracked**, so every file the pipeline writes travels to GitHub and can
be downloaded from your work machine.

`oecdnz build <dataset>` writes two files per run:

- `<dataset>-spliced.csv` — the tidy panel, one row per observation, every row carrying
  its `source` and a `spliced` flag
- `<dataset>-wide.csv` — the same data as a country-by-period grid, which is the shape
  you want for a spreadsheet or a chart

To download one from a browser: click the file on GitHub, then **Download raw file**.
