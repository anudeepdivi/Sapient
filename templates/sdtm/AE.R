# AE: raw (pharmaverseraw AE EDC form) -> SDTM AE via sdtm.oak.
# Deterministic template — same scaffolding status as templates/sdtm/VS.R.
# Categorical recodes are the study CT a real study would carry in its oak ct_spec;
# MedDRA coding variables are predecessors copied from the coded raw columns.
suppressMessages({
  library(dplyr)
  library(sdtm.oak)
  library(haven)
})

ae_raw <- read.csv("data/raw/ae_raw.csv", colClasses = "character") |>
  mutate(across(everything(), ~ na_if(., ""))) |>
  generate_oak_id_vars(pat_var = "PATNUM", raw_src = "ae_raw")

dm <- read_xpt("data/sdtm/DM.xpt")

yn <- c("No" = "N", "Yes" = "Y")
rel_map <- c("Not Related" = "NONE", "Remote" = "REMOTE",
             "Possibly Related" = "POSSIBLE", "Probably Related" = "PROBABLE")

ae <- ae_raw |>
  mutate(
    STUDYID = STUDY,
    DOMAIN = "AE",
    USUBJID = paste0("01-", PATNUM),
    AETERM = toupper(IT.AETERM),
    AELLT = AELLT,
    AELLTCD = suppressWarnings(as.numeric(AELLTCD)),
    AEDECOD = AEDECOD,
    AEPTCD = suppressWarnings(as.numeric(AEPTCD)),
    AEHLT = AEHLT,
    AEHLTCD = suppressWarnings(as.numeric(AEHLTCD)),
    AEHLGT = AEHLGT,
    AEHLGTCD = suppressWarnings(as.numeric(AEHLGTCD)),
    AEBODSYS = AEBODSYS,
    AEBDSYCD = suppressWarnings(as.numeric(AEBDSYCD)),
    AESOC = AESOC,
    AESOCCD = suppressWarnings(as.numeric(AESOCCD)),
    AESEV = toupper(sub(" Adverse Event$", "", IT.AESEV)),
    AESER = unname(yn[IT.AESER]),
    AEACN = unname(yn[IT.AEACN]),
    AEREL = unname(rel_map[IT.AEREL]),
    AEOUT = toupper(AEOUTCOME),
    AESCAN = unname(yn[AESCAN]),
    AESCONG = unname(yn[AESCNO]),
    AESDISAB = unname(yn[AEDIS]),
    AESDTH = unname(yn[IT.AESDTH]),
    AESHOSP = unname(yn[IT.AESHOSP]),
    AESLIFE = unname(yn[IT.AESLIFE]),
    AESOD = unname(yn[AESOD]),
    AEDTC = as.character(create_iso8601(AEDTCOL, .format = "m/d/y")),
    AESTDTC = as.character(create_iso8601(IT.AESTDAT, .format = "m/d/y")),
    AEENDTC = as.character(create_iso8601(IT.AEENDAT, .format = "m/d/y"))
  ) |>
  derive_study_day(
    dm_domain = dm, tgdt = "AESTDTC", refdt = "RFSTDTC", study_day_var = "AESTDY"
  ) |>
  derive_study_day(
    dm_domain = dm, tgdt = "AEENDTC", refdt = "RFSTDTC", study_day_var = "AEENDY"
  ) |>
  mutate(across(c(AEDTC, AESTDTC, AEENDTC), as.character)) |>
  arrange(USUBJID, AESTDTC, AETERM) |>
  group_by(USUBJID) |>
  mutate(AESEQ = row_number()) |>
  ungroup() |>
  select(STUDYID, DOMAIN, USUBJID, AESEQ, AETERM, AELLT, AELLTCD, AEDECOD,
         AEPTCD, AEHLT, AEHLTCD, AEHLGT, AEHLGTCD, AEBODSYS, AEBDSYCD, AESOC,
         AESOCCD, AESEV, AESER, AEACN, AEREL, AEOUT, AESCAN, AESCONG, AESDISAB,
         AESDTH, AESHOSP, AESLIFE, AESOD, AEDTC, AESTDTC, AEENDTC, AESTDY, AEENDY)

dir.create("data/sdtm_generated", showWarnings = FALSE, recursive = TRUE)
write_xpt(ae, "data/sdtm_generated/AE.xpt", name = "AE")
cat("AE:", nrow(ae), "rows written to data/sdtm_generated/AE.xpt\n")
