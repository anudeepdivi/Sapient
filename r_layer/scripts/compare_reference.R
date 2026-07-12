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
ref <- read_xpt(sprintf("data/reference/%s.xpt", dataset))

keys <- list(ADAE = c("USUBJID", "AESEQ"),
             VS = c("USUBJID", "VSTESTCD", "VISITNUM", "VSTPTNUM"),
             DS = c("USUBJID", "DSDECOD", "DSSTDTC"),
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
  a <- as.character(merged[[paste0(v, ".gen")]]); b <- as.character(merged[[paste0(v, ".ref")]])
  mean((a == b) | (is.na(a) & is.na(b)))
})
overall <- mean(rates, na.rm = TRUE)
cat(sprintf("VALUE-MATCH %s: %.1f%% mean cell agreement over %d common vars, %d/%d subjects overlap\n",
            dataset, 100 * overall, length(common_vars), nrow(merged), nrow(ref)))
worst <- sort(rates)[seq_len(min(8, length(rates)))]
cat("lowest-agreement variables:\n")
for (nm in names(worst)) cat(sprintf("  %-10s %.0f%%\n", nm, 100 * worst[[nm]]))
