# "Papers Please" citation generator

A python script to generate citation slips from "Papers Please" game as a PNG file.

---
Usage: `./bin/citate "Protocol Violated.\nSleeping at work" "Penalty assessed - 5 credits"` - gives output like below.

![Image resulting from above command](example_citation.png)

Use `./bin/citate --help` to get list of options.

Live web version is [here](https://saphi.re/papers_please).

---
On a system with the Nix package manager, this tool can be directly run with:
`nix run gitlab:Saphire/citations -- "Using Nix." "That's nice - +1 Flake"`

---
All python, typescript, html and css code in the project is licensed under `GNU AGPL-3.0`.
