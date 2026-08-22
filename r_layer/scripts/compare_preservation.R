#!/usr/bin/env Rscript
# Compares the analysis frame of an unmodified standard (arg1) against a
# delta-modified copy (arg2), keyed by comma-separated key columns (arg3).
# Emits line-based results parsed by harness/preservation.py:
#   SCHEMA_EQUAL <TRUE|FALSE>
#   REMOVED <key|key|...>   rows in base absent from modified
#   ADDED <key|key|...>     rows in modified absent from base
#   PRESERVED_IDENTICAL <TRUE|FALSE>
#   PRESERVED_COUNT <n>
#   TOTAL_COMPARED_CELLS <n>
#   CELL_DIFF <key|column|base_value|mod_value>  (repeated)
# Base R only — no packages.

args <- commandArgs(trailingOnly = TRUE)
base_df <- readRDS(args[1])
mod_df <- readRDS(args[2])
key_cols <- strsplit(args[3], ",", fixed = TRUE)[[1]]

mk_keys <- function(df) {
  apply(df[, key_cols, drop = FALSE], 1, paste, collapse = "|")
}
bk <- mk_keys(base_df)
mk <- mk_keys(mod_df)

schema_equal <- identical(names(base_df), names(mod_df))
cat("SCHEMA_EQUAL", schema_equal, "\n")
cat("REMOVED", paste(setdiff(bk, mk), collapse = ";"), "\n")
cat("ADDED", paste(setdiff(mk, bk), collapse = ";"), "\n")

preserved <- intersect(bk, mk)
bi <- match(preserved, bk)
mi <- match(preserved, mk)

diffs <- character(0)
total_cells <- 0L
if (schema_equal && length(preserved) > 0) {
  for (cn in names(base_df)) {
    av <- as.character(base_df[[cn]][bi])
    mv <- as.character(mod_df[[cn]][mi])
    # NA-safe equality: R's NA == x is NA, which which() would silently drop
    both <- !is.na(av) & !is.na(mv)
    same <- (both & av == mv) | (is.na(av) & is.na(mv))
    total_cells <- total_cells + length(av)
    for (i in which(!same)) {
      diffs <- c(diffs, paste(preserved[i], cn, av[i], mv[i], sep = "|"))
    }
  }
}
cat("PRESERVED_IDENTICAL", length(diffs) == 0, "\n")
cat("PRESERVED_COUNT", length(preserved), "\n")
cat("TOTAL_COMPARED_CELLS", total_cells, "\n")
for (d in diffs) cat("CELL_DIFF", d, "\n")
