#!/usr/bin/env Rscript
# Print name(args) for each function name given on the command line.
# Usage: list_signatures.R <namespace[,namespace...]> <function> ...
# Each name is resolved from the first listed namespace that has it; a namespace that is
# not installed is skipped (tern's layout verbs live in rtables, so "tern,rtables" still
# yields the rtables subset when tern is missing).
args <- commandArgs(trailingOnly = TRUE)
namespaces <- Filter(function(ns) suppressMessages(requireNamespace(ns, quietly = TRUE)),
                     strsplit(args[1], ",", fixed = TRUE)[[1]])
for (fn in args[-1]) {
  ns <- Find(function(ns) exists(fn, where = asNamespace(ns)), namespaces)
  if (is.null(ns)) {
    cat(fn, ": NOT A REAL", args[1], "FUNCTION\n")
    next
  }
  sig <- deparse(args(get(fn, envir = asNamespace(ns))))
  sig <- paste(trimws(sig[-length(sig)]), collapse = " ")
  cat(sub("^function ?", fn, sig), "\n")
}
