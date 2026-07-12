# EX: raw (pharmaverseraw EC/dosing EDC form) -> SDTM EX via sdtm.oak.
# Deterministic template — same scaffolding status as templates/sdtm/VS.R.
suppressMessages({
  library(dplyr)
  library(sdtm.oak)
  library(haven)
})

ec_raw <- read.csv("data/raw/ec_raw.csv", colClasses = "character") |>
  mutate(across(everything(), ~ na_if(., ""))) |>
  generate_oak_id_vars(pat_var = "PATNUM", raw_src = "ec_raw")

dm <- read_xpt("data/sdtm/DM.xpt")

visit_schedule <- c(
  "SCREENING 1" = 1, "SCREENING 2" = 2, "BASELINE" = 3, "AMBUL ECG PLACEMENT" = 3.5,
  "WEEK 2" = 4, "WEEK 4" = 5, "AMBUL ECG REMOVAL" = 6, "WEEK 6" = 7, "WEEK 8" = 8,
  "WEEK 12" = 9, "WEEK 16" = 10, "WEEK 20" = 11, "WEEK 24" = 12, "WEEK 26" = 13,
  "RETRIEVAL" = 201
)
visit_day <- c(
  "SCREENING 1" = -7, "SCREENING 2" = -1, "BASELINE" = 1, "AMBUL ECG PLACEMENT" = 13,
  "WEEK 2" = 14, "WEEK 4" = 28, "AMBUL ECG REMOVAL" = 30, "WEEK 6" = 42, "WEEK 8" = 56,
  "WEEK 12" = 84, "WEEK 16" = 112, "WEEK 20" = 140, "WEEK 24" = 168, "WEEK 26" = 182,
  "RETRIEVAL" = 168
)
dosu_map <- c("Milligram" = "mg")
frq_map <- c("Daily" = "QD")

ex <- ec_raw |>
  mutate(
    STUDYID = STUDY,
    DOMAIN = "EX",
    USUBJID = paste0("01-", PATNUM),
    EXTRT = DRUGAD,
    EXDOSE = suppressWarnings(as.numeric(IT.ECDSTXT)),
    EXDOSU = unname(dosu_map[IT.ECDOSU]),
    EXDOSFRM = toupper(DOSFM),
    EXDOSFRQ = unname(frq_map[DOSFRQ]),
    EXROUTE = toupper(IT.ECROUTE),
    VISIT = toupper(VISITNAME),
    VISITNUM = unname(visit_schedule[VISIT]),
    VISITDY = unname(visit_day[VISIT]),
    EXSTDTC = as.character(create_iso8601(IT.ECSTDAT, .format = "d-m-y")),
    EXENDTC = as.character(create_iso8601(IT.ECENDAT, .format = "d-m-y"))
  ) |>
  derive_study_day(
    dm_domain = dm, tgdt = "EXSTDTC", refdt = "RFSTDTC", study_day_var = "EXSTDY"
  ) |>
  derive_study_day(
    dm_domain = dm, tgdt = "EXENDTC", refdt = "RFSTDTC", study_day_var = "EXENDY"
  ) |>
  mutate(across(c(EXSTDTC, EXENDTC), as.character)) |>
  arrange(USUBJID, EXSTDTC) |>
  group_by(USUBJID) |>
  mutate(EXSEQ = row_number()) |>
  ungroup() |>
  select(STUDYID, DOMAIN, USUBJID, EXSEQ, EXTRT, EXDOSE, EXDOSU, EXDOSFRM,
         EXDOSFRQ, EXROUTE, VISITNUM, VISIT, VISITDY, EXSTDTC, EXENDTC,
         EXSTDY, EXENDY)

dir.create("data/sdtm_generated", showWarnings = FALSE, recursive = TRUE)
write_xpt(ex, "data/sdtm_generated/EX.xpt", name = "EX")
cat("EX:", nrow(ex), "rows written to data/sdtm_generated/EX.xpt\n")
