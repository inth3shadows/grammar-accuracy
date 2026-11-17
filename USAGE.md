# Usage Guide: grammar-accuracy

## What This Does

Editors, code search and AI coding tools read source code through tree-sitter grammars. When a
grammar builds the wrong structure for a line of code, those tools quietly see something different
from what the code means, and nothing reports an error.

This project measures how often that happens. It reads thousands of real files with both a
grammar and the language's own official parser, and counts every place where the two disagree.

## How to Read the Results

The results table in the README has one row per grammar version:

- **Precision**: of the pieces the grammar found, the share that were right.
- **Recall**: of the pieces the official parser found, the share the grammar also found.
- **Wrong**: pieces the grammar produced that the official parser did not.
- **Missed**: pieces the official parser produced that the grammar did not.
- **Error files**: files the official parser reads cleanly but the grammar reports as broken.

Higher percentages and lower counts are better. One misread line usually adds to both Wrong and
Missed, because the grammar builds the wrong piece and leaves out the right one.

Below the table, the README lists each confirmed kind of mistake with a short example.

## What to Do When Something Looks Off

- "Two versions score exactly the same": they most likely contain the same grammar. Many copies
  change only packaging.
- "The numbers changed but the grammar did not": check which version of the official parser was
  used. It is recorded with each result.
- "A listed mistake seems wrong": open an issue on this repository with the example.

## FAQ

**Is 99.99% good?** It is a high starting point. The useful signal is the change between versions,
and the list of specific mistakes.

**Why are some kinds of code not counted?** A few things are written down differently by the two
parsers on purpose (for example, brackets). Counting them would add noise without finding mistakes.
They are listed in the technical reference.

**Related documentation:** [README](README.md) · [Technical Reference](TECHNICAL.md)
