# Drop source files here

This folder is **tracked**, so anything you put here travels to GitHub and is waiting
for the next session. That is how source data gets from your machine into the pipeline.

To add a file from a browser: open this folder on GitHub → **Add file** → **Upload
files** → drag it in → **Commit changes**.

What belongs here:

- the OECD extract for the chosen indicator (the Data Explorer's download button)
- the Stats NZ BOS innovation table

Point `config/datasets.toml` at whatever you name them (`source.path` for the NZ side;
the OECD side is passed on the command line as `--oecd-file`).

Keep files here as you downloaded them — unedited. The pipeline does the cleaning, and
an untouched original is the only way to check its work later.
