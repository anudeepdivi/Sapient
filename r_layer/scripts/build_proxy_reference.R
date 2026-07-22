#!/usr/bin/env Rscript
# Build a PROXY reference for ADLBC. The CDISC pilot's own ADLBC is not published
# in pharmaverseadam, so there is no genuine value-match target for it (unlike
# ADSL/ADAE, whose references are the real pilot datasets in data/reference/).
#
# This proxy is pharmaverseadam::adlb restricted to chemistry. It is NOT the pilot
# ADLBC and must never be reported as one:
#   - adlb is a different derivation of the same source LB (115 vars vs spec's 46)
#   - PARCAT1 is "CHEMISTRY" here vs the pilot spec's "CHEM"
#   - 3 of 18 analytes carry different PARAMCD codes; renamed below so the join
#     lands. The rename is an EVAL-SIDE transformation, listed explicitly so it is
#     auditable rather than silently improving the score.
# Any number computed against this file must be labelled "proxy" — compare_reference.R
# prints that label automatically for datasets listed in its PROXY_REFERENCE set.
suppressMessages({library(pharmaverseadam); library(dplyr); library(haven)})

data(adlb)

# pilot-spec PARAMCD <- pharmaverseadam adlb PARAMCD (same analyte, different codelist)
paramcd_map <- c(ALKPH = "ALP", CHOLES = "CHOL", POTAS = "K")

chem <- adlb |>
  filter(PARCAT1 == "CHEMISTRY") |>
  mutate(PARAMCD = ifelse(PARAMCD %in% names(paramcd_map),
                          paramcd_map[PARAMCD], PARAMCD),
         PARCAT1 = "CHEM")

dir.create("data/reference", showWarnings = FALSE, recursive = TRUE)
write_xpt(chem, "data/reference/ADLBC.xpt", version = 5, name = "ADLBC")

cat(sprintf("PROXY reference written: data/reference/ADLBC.xpt\n"))
cat(sprintf("  %d rows, %d subjects, %d params (%d renamed: %s)\n",
            nrow(chem), length(unique(chem$USUBJID)), length(unique(chem$PARAMCD)),
            length(paramcd_map),
            paste(names(paramcd_map), paramcd_map, sep = "->", collapse = ", ")))
cat("  NOT the pilot ADLBC - every number from it is a proxy figure.\n")
