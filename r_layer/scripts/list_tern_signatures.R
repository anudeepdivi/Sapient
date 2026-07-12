#!/usr/bin/env Rscript
# Print name(args) for each tern/rtables function name given on the command line.
# Resolves each name from the tern namespace first, then rtables (the table-layout
# verbs live in rtables; the clinical analysis functions live in tern).
# Degrades gracefully if tern isn't installed yet — emits the rtables subset only.
args <- commandArgs(trailingOnly = TRUE)
has_tern <- suppressMessages(requireNamespace("tern", quietly = TRUE))
suppressMessages(library(rtables))
for (fn in args) {
  ns <- if (has_tern && exists(fn, where = asNamespace("tern"))) "tern"
        else if (exists(fn, where = asNamespace("rtables"))) "rtables"
        else NA
  if (is.na(ns)) {
    cat(fn, ": NOT A REAL tern/rtables FUNCTION\n")
    next
  }
  sig <- deparse(args(get(fn, envir = asNamespace(ns))))
  sig <- paste(trimws(sig[-length(sig)]), collapse = " ")
  cat(sub("^function ?", fn, sig), "\n")
}
