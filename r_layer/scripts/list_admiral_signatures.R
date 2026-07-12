#!/usr/bin/env Rscript
# Print name(args) for each admiral function name given on the command line.
args <- commandArgs(trailingOnly = TRUE)
suppressMessages(library(admiral))
for (fn in args) {
  if (exists(fn, where = asNamespace("admiral"))) {
    sig <- deparse(args(get(fn, envir = asNamespace("admiral"))))
    sig <- paste(trimws(sig[-length(sig)]), collapse = " ")
    cat(sub("^function ?", fn, sig), "\n")
  } else {
    cat(fn, ": NOT A REAL ADMIRAL FUNCTION\n")
  }
}
