#!/usr/bin/env Rscript
# Value-match a generated dataset against its pharmaverse reference
# (pharmaverseadam for ADaM, pharmaversesdtm for SDTM).
# Reports: subject overlap, common-variable count, and per-variable cell-agreement
# on the shared subjects. This is the correctness bar beyond execution + conformance.
# Usage: Rscript compare_reference.R ADSL [gen_dir]   (gen_dir defaults to data/adam)
suppressMessages({library(haven); library(dplyr)})
args <- commandArgs(trailingOnly = TRUE)
dataset <- args[1]
gen_dir <- if (length(args) > 1) args[2] else "data/adam"

gen <- read_xpt(sprintf("%s/%s.xpt", gen_dir, dataset))
# SAPIENT_REFERENCE_DIR=data/reference/pilot scores against the CDISC pilot's own ADaM
# (built from the same SAP/spec); default is the pharmaverseadam reference.
ref_dir <- Sys.getenv("SAPIENT_REFERENCE_DIR", "data/reference")
ref <- read_xpt(sprintf("%s/%s.xpt", ref_dir, dataset))

# Datasets whose data/reference/*.xpt is a PROXY, not the real pilot dataset
# (see build_proxy_reference.R). Every figure printed for these is labelled.
PROXY_REFERENCE <- c("ADLBC")

keys <- list(ADAE = c("USUBJID", "AESEQ"),
             ADLBC = c("USUBJID", "PARAMCD", "VISITNUM"),
             VS = c("USUBJID", "VSTESTCD", "VISITNUM", "VSTPTNUM"),
             DS = c("USUBJID", "DSDECOD", "DSSTDTC"),
             EX = c("USUBJID", "EXSTDTC"),
             AE = c("USUBJID", "AETERM", "AESTDTC", "AEENDTC"))
key <- if (dataset %in% names(keys)) keys[[dataset]] else "USUBJID"

common_vars <- setdiff(intersect(names(gen), names(ref)), key)
# occurrence index disambiguates records that share a key (e.g. same AE term
# reported twice with identical dates); no-op wherever keys are already unique
add_occ <- function(d) d %>% group_by(across(all_of(key))) %>%
  mutate(.occ = row_number()) %>% ungroup()
merged <- inner_join(
  add_occ(gen %>% select(all_of(c(key, common_vars)))),
  add_occ(ref %>% select(all_of(c(key, common_vars)))),
  by = c(key, ".occ"), suffix = c(".gen", ".ref"))

if (nrow(merged) == 0) {
  cat(sprintf("VALUE-MATCH %s: no overlapping keys (gen %d rows, ref %d rows)\n",
              dataset, nrow(gen), nrow(ref)))
  quit(status = 0)
}

rates <- sapply(common_vars, function(v) {
  a <- merged[[paste0(v, ".gen")]]; b <- merged[[paste0(v, ".ref")]]
  # a date is compared by value: an unformatted numeric date (days since 1970) equals
  # the same Date; a missing DATE9 format is a conformance finding, not a wrong value
  if (inherits(a, "Date") != inherits(b, "Date")) { a <- as.numeric(a); b <- as.numeric(b) }
  a <- as.character(a); b <- as.character(b)
  # missing on one side only is a mismatch; plain `a == b` yields NA there, which
  # silently dropped the whole variable from the mean (na.rm) and inflated agreement
  mean(ifelse(is.na(a) | is.na(b), is.na(a) & is.na(b), a == b))
})
overall <- mean(rates, na.rm = TRUE)
cat(sprintf("VALUE-MATCH%s %s: %.1f%% mean cell agreement over %d common vars, %d/%d rows overlap\n",
            if (dataset %in% PROXY_REFERENCE && ref_dir == "data/reference") " [PROXY REFERENCE - not the pilot dataset]" else "",
            dataset, 100 * overall, length(common_vars), nrow(merged), nrow(ref)))
worst <- sort(rates)[seq_len(min(8, length(rates)))]
cat("lowest-agreement variables:\n")
for (nm in names(worst)) cat(sprintf("  %-10s %.0f%%\n", nm, 100 * worst[[nm]]))
# Full per-variable rates for derivation scoring (scripts/score_derivations.py)
rates_out <- Sys.getenv("SAPIENT_RATES_JSON")
if (nzchar(rates_out)) jsonlite::write_json(as.list(rates), rates_out, auto_unbox = TRUE, digits = 4)
