#!/usr/bin/env Rscript
# Catalog every exported admiral function (name, help title, formal arguments) for
# arm B, which exposes each one as its own MCP tool - the "wrap the whole package"
# approach. Read from the installed package, never written by hand.
suppressMessages({library(admiral); library(jsonlite)})
rd <- tools::Rd_db("admiral")
titles <- vapply(rd, function(x) {
  t <- Filter(function(e) identical(attr(e, "Rd_tag"), "\\title"), x)
  if (length(t)) paste(trimws(unlist(t)), collapse = " ") else ""
}, character(1))
names(titles) <- sub("\\.Rd$", "", names(titles))
exports <- sort(getNamespaceExports("admiral"))
catalog <- lapply(exports, function(fn) {
  f <- get(fn, envir = asNamespace("admiral"))
  if (!is.function(f)) return(NULL)
  args <- names(formals(f))
  list(name = fn, title = if (!is.na(titles[fn])) unname(titles[fn]) else "",
       args = setdiff(args, "..."))
})
catalog <- Filter(Negate(is.null), catalog)
write_json(catalog, "bench/admiral_catalog.json", auto_unbox = TRUE, pretty = TRUE)
cat(length(catalog), "admiral functions catalogued\n")
