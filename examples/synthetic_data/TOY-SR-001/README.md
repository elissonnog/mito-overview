# TOY-SR-001

`TOY-SR-001` is the tracked reduced short-read smoke fixture. It contains ten coordinate-sorted 20-bp alignments over a 60-bp mitochondrial reference. Three reads carry `A>C` at one-based position 10, giving an exact observed alternate allele fraction of `3/10 = 0.3` at that site under the public filters.

The fixture validates short-read routing, allele-count arithmetic, stable report generation, and `not_applicable` states for long-read-only modules. It is not a caller benchmark or a model of a complete short-read library.
