#!/usr/bin/env Rscript
# Deterministic conformance check of a built ADaM dataset against the metacore spec:
# variable presence, R type (character vs numeric), length, and controlled terminology.
# This is the format/type/CT error class — the durable one — checked in reverse from
# the same metadata a P21/CORE rule set encodes. Prints findings; exit 1 if any error.
suppressMessages({library(metacore); library(haven); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
dataset <- args[1]

mc <- load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))
m <- suppressWarnings(select_dataset(mc, dataset))
ds <- read_xpt(sprintf("data/adam/%s.xpt", dataset))
vs <- m$var_spec
val <- m$value_spec
cl <- m$codelist
findings <- c()

for (i in seq_len(nrow(vs))) {
  v <- vs$variable[i]
  if (!v %in% names(ds)) next  # presence handled by check_variables; skip here
  col <- ds[[v]]
  expected <- vs$type[i]
  # Dates/times are numeric ADaM variables carried as Date/POSIXct with a date format.
  is_num <- is.numeric(col) || inherits(col, c("Date", "POSIXct", "POSIXt"))
  if (expected == "text" && is_num)
    findings <- c(findings, sprintf("%s: expected text, got numeric", v))
  if (expected %in% c("integer", "float") && !is_num && !all(is.na(col)))
    findings <- c(findings, sprintf("%s: expected %s, got character", v, expected))
  if (!is.na(vs$length[i]) && is.character(col)) {
    over <- max(nchar(col), na.rm = TRUE)
    if (is.finite(over) && over > vs$length[i])
      findings <- c(findings, sprintf("%s: value length %d exceeds spec length %d", v, over, vs$length[i]))
  }
  code_id <- val$code_id[match(v, val$variable)]
  if (!is.na(code_id)) {
    row <- cl[cl$code_id == code_id, ]
    if (nrow(row) > 0) {
      codes <- row$codes[[1]]
      if (!is.null(codes) && "code" %in% names(codes)) {
        allowed <- codes$code
        present <- unique(as.character(col[!is.na(col)]))
        present <- present[present != ""]  # "" is SAS missing for character, not a CT value
        bad <- setdiff(present, allowed)
        if (length(bad) > 0)
          findings <- c(findings, sprintf("%s: values not in controlled terminology: %s",
                                          v, paste(head(bad, 5), collapse = ", ")))
      }
    }
  }
}

# Supplementary CT check against the free NCI-EVS CDISC controlled terminology
# (knowledge/ct/variable_ct.json), independent of the spec's own codelists — so CT is
# validated even when the (generated) spec carries no codelists.
ct_file <- "knowledge/ct/variable_ct.json"
if (file.exists(ct_file)) {
  var_ct <- jsonlite::fromJSON(ct_file, simplifyVector = FALSE)
  for (v in names(var_ct)) {
    if (!v %in% names(ds)) next
    allowed <- toupper(unlist(var_ct[[v]]))
    present <- unique(toupper(as.character(ds[[v]][!is.na(ds[[v]])])))
    present <- present[present != ""]
    bad <- setdiff(present, allowed)
    if (length(bad) > 0)
      findings <- c(findings, sprintf("%s: values not in CDISC CT (%s): %s",
                                      v, "NCI-EVS", paste(head(bad, 5), collapse = ", ")))
  }
}

if (length(findings) == 0) {
  cat("CONFORMANCE PASS\n")
} else {
  cat("CONFORMANCE FINDINGS:\n"); cat(paste0("- ", findings), sep = "\n"); cat("\n")
  quit(status = 1)
}
