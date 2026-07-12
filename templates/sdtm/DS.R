# DS: raw (pharmaverseraw disposition EDC form) -> SDTM DS via sdtm.oak.
# Deterministic template — same scaffolding status as templates/sdtm/VS.R.
suppressMessages({
  library(dplyr)
  library(sdtm.oak)
  library(haven)
})

ds_raw <- read.csv("data/raw/ds_raw.csv", colClasses = "character") |>
  mutate(across(everything(), ~ na_if(., ""))) |>
  generate_oak_id_vars(pat_var = "PATNUM", raw_src = "ds_raw")

dm <- read_xpt("data/sdtm/DM.xpt")

visit_schedule <- c(
  "SCREENING 1" = 1, "SCREENING 2" = 2, "BASELINE" = 3, "AMBUL ECG PLACEMENT" = 3.5,
  "WEEK 2" = 4, "WEEK 4" = 5, "AMBUL ECG REMOVAL" = 6, "WEEK 6" = 7, "WEEK 8" = 8,
  "WEEK 12" = 9, "WEEK 16" = 10, "WEEK 20" = 11, "WEEK 24" = 12, "WEEK 26" = 13,
  "RETRIEVAL" = 201
)

ds <- ds_raw |>
  mutate(
    STUDYID = STUDY,
    DOMAIN = "DS",
    USUBJID = paste0("01-", PATNUM),
    VISIT = toupper(INSTANCE),
    VISITNUM = if_else(
      grepl("^UNSCHEDULED", VISIT),
      suppressWarnings(as.numeric(sub("^UNSCHEDULED ", "", VISIT))),
      unname(visit_schedule[VISIT])
    ),
    DSDECOD = case_when(
      is.na(IT.DSDECOD) & VISIT == "RETRIEVAL" ~ "FINAL RETRIEVAL VISIT",
      is.na(IT.DSDECOD) ~ "FINAL LAB VISIT",
      TRUE ~ toupper(IT.DSDECOD)
    ),
    DSCAT = case_when(
      DSDECOD %in% c("FINAL LAB VISIT", "FINAL RETRIEVAL VISIT") ~ "OTHER EVENT",
      DSDECOD == "RANDOMIZED" ~ "PROTOCOL MILESTONE",
      TRUE ~ "DISPOSITION EVENT"
    ),
    DSTERM = if_else(is.na(IT.DSTERM), DSDECOD, toupper(IT.DSTERM)),
    DSDTC = if_else(
      is.na(DSTMCOL),
      as.character(create_iso8601(DSDTCOL, .format = "m-d-y")),
      paste0(as.character(create_iso8601(DSDTCOL, .format = "m-d-y")), "T", DSTMCOL)
    ),
    DSSTDTC = as.character(create_iso8601(IT.DSSTDAT, .format = "m-d-y"))
  ) |>
  derive_study_day(
    dm_domain = dm, tgdt = "DSSTDTC", refdt = "RFSTDTC", study_day_var = "DSSTDY"
  ) |>
  mutate(DSSTDTC = as.character(DSSTDTC)) |>
  arrange(USUBJID, DSSTDTC, DSCAT) |>
  group_by(USUBJID) |>
  mutate(DSSEQ = row_number()) |>
  ungroup() |>
  select(STUDYID, DOMAIN, USUBJID, DSSEQ, DSTERM, DSDECOD, DSCAT,
         VISITNUM, VISIT, DSDTC, DSSTDTC, DSSTDY)

dir.create("data/sdtm_generated", showWarnings = FALSE, recursive = TRUE)
write_xpt(ds, "data/sdtm_generated/DS.xpt", name = "DS")
cat("DS:", nrow(ds), "rows written to data/sdtm_generated/DS.xpt\n")
