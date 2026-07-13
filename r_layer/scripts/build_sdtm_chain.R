#!/usr/bin/env Rscript
# Build the full generated SDTM layer into data/sdtm_generated/ for the
# raw -> SDTM -> ADaM chain (set SAPIENT_SDTM_DIR=data/sdtm_generated).
# Order matters: DM derives its reference dates from the GENERATED EX and DS.
# SV/MH/PC have no pharmaverseraw form (nothing to generate from), so they are
# supplemented verbatim from the reference export in data/sdtm/ — documented
# structural ceiling, not a shortcut.
templates <- c("templates/sdtm/EX.R", "templates/sdtm/DS.R", "templates/sdtm/AE.R",
               "templates/sdtm/VS.R", "templates/sdtm/DM.R")
for (t in templates) {
  cat("== running", t, "==\n")
  source(t, local = new.env())
}
for (dom in c("SV", "MH", "PC")) {
  ok <- file.copy(sprintf("data/sdtm/%s.xpt", dom),
                  sprintf("data/sdtm_generated/%s.xpt", dom), overwrite = TRUE)
  cat(sprintf("%s: %s (no raw source; copied from reference)\n", dom,
              if (ok) "copied" else "COPY FAILED"))
}
