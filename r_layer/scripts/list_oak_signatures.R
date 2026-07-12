#!/usr/bin/env Rscript
# Print name(args) for each sdtm.oak function name given on the command line.
args <- commandArgs(trailingOnly = TRUE)
suppressMessages(library(sdtm.oak))
for (fn in args) {
  if (exists(fn, where = asNamespace("sdtm.oak"))) {
    sig <- deparse(args(get(fn, envir = asNamespace("sdtm.oak"))))
    sig <- paste(trimws(sig[-length(sig)]), collapse = " ")
    cat(sub("^function ?", fn, sig), "\n")
  } else {
    cat(fn, ": NOT A REAL sdtm.oak FUNCTION\n")
  }
}
