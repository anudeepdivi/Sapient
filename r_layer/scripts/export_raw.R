#!/usr/bin/env Rscript
# Export pharmaverseraw EDC-style raw datasets to data/raw/*.csv — the inputs to
# the SDTM generation layer (raw -> SDTM via sdtm.oak). CSV because that is the
# shape raw EDC exports actually arrive in.
suppressMessages(library(pharmaverseraw))
dir.create("data/raw", showWarnings = FALSE, recursive = TRUE)
for (nm in data(package = "pharmaverseraw")$results[, "Item"]) {
  data(list = nm, package = "pharmaverseraw")
  write.csv(get(nm), sprintf("data/raw/%s.csv", nm), row.names = FALSE, na = "")
  cat(nm, ":", nrow(get(nm)), "rows\n")
}
