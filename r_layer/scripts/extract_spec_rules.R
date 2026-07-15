#!/usr/bin/env Rscript
# Precompile the full conformance rule set for one dataset from the metacore spec:
# per variable — type, length, format, core status, and controlled-terminology values.
# Emits JSON to stdout. Usage: Rscript extract_spec_rules.R ADSL
suppressMessages({library(metacore); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
dataset <- args[1]

mc <- load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))
m <- suppressWarnings(select_dataset(mc, dataset))

vs <- m$var_spec
val <- m$value_spec
cl <- m$codelist

code_values <- function(code_id) {
  if (is.na(code_id)) return(NULL)
  row <- cl[cl$code_id == code_id, ]
  if (nrow(row) == 0) return(NULL)
  codes <- row$codes[[1]]
  if (is.null(codes) || !"code" %in% names(codes)) return(NULL)
  head(codes$code, 40)
}

dv <- m$derivations
deriv_text <- function(v) {
  did <- val$derivation_id[match(v, val$variable)]
  if (is.na(did)) return(NULL)
  txt <- dv$derivation[match(did, dv$derivation_id)]
  if (is.na(txt)) NULL else txt
}

rules <- lapply(seq_len(nrow(vs)), function(i) {
  v <- vs$variable[i]
  code_id <- val$code_id[match(v, val$variable)]
  list(
    variable = v,
    type = vs$type[i],
    length = if (is.na(vs$length[i])) NULL else vs$length[i],
    format = if (is.na(vs$format[i])) NULL else vs$format[i],
    ct = code_values(code_id),
    origin = {o <- val$origin[match(v, val$variable)]; if (is.na(o)) NULL else o},
    derivation = deriv_text(v)
  )
})
cat(toJSON(rules, auto_unbox = TRUE, na = "null"))
