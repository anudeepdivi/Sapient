# DM: raw (pharmaverseraw demographics EDC form) -> SDTM DM via sdtm.oak.
# Deterministic template — same scaffolding status as templates/sdtm/VS.R.
# Reference dates come from the GENERATED EX and DS (data/sdtm_generated/),
# so DM closes the raw -> SDTM chain end-to-end.
# BRTHDTC has no raw source (only IT.AGE is collected) and is omitted.
# RFPENDTC's true source in the reference is SV (last SVENDTC), a domain with
# no pharmaverseraw form — approximated as max DS DSDTC (74% agreement ceiling).
suppressMessages({
  library(dplyr)
  library(sdtm.oak)
  library(haven)
})

dm_raw <- read.csv("data/raw/dm_raw.csv", colClasses = "character") |>
  mutate(across(everything(), ~ na_if(., ""))) |>
  generate_oak_id_vars(pat_var = "PATNUM", raw_src = "dm_raw")

ex <- read_xpt("data/sdtm_generated/EX.xpt")
ds <- read_xpt("data/sdtm_generated/DS.xpt")
ds_raw <- read.csv("data/raw/ds_raw.csv", colClasses = "character")

ref_dates <- ex |>
  group_by(USUBJID) |>
  summarise(RFSTDTC = min(EXSTDTC, na.rm = TRUE),
            RFXENDTC = max(EXENDTC, na.rm = TRUE), .groups = "drop")
disp_dates <- ds |>
  filter(DSCAT == "DISPOSITION EVENT") |>
  group_by(USUBJID) |>
  summarise(RFENDTC = max(DSSTDTC, na.rm = TRUE), .groups = "drop")
pen_dates <- ds |>
  group_by(USUBJID) |>
  summarise(RFPENDTC = max(DSDTC, na.rm = TRUE), .groups = "drop")
death <- ds_raw |>
  filter(!is.na(DEATHDT) & DEATHDT != "") |>
  transmute(USUBJID = paste0("01-", PATNUM),
            DTHDTC = as.character(create_iso8601(DEATHDT, .format = "m/d/y"))) |>
  distinct()

arm_label <- c("Pbo" = "Placebo", "Xan_Lo" = "Xanomeline Low Dose",
               "Xan_Hi" = "Xanomeline High Dose", "Scrnfail" = "Screen Failure")
sex_map <- c("Female" = "F", "Male" = "M")

dm <- dm_raw |>
  mutate(
    STUDYID = STUDY,
    DOMAIN = "DM",
    USUBJID = paste0("01-", PATNUM),
    SUBJID = sub("^.*-", "", PATNUM),
    SITEID = sub("-.*$", "", PATNUM),
    AGE = suppressWarnings(as.numeric(IT.AGE)),
    AGEU = "YEARS",
    SEX = unname(sex_map[IT.SEX]),
    RACE = toupper(IT.RACE),
    ETHNIC = toupper(IT.ETHNIC),
    ARMCD = PLANNED_ARMCD,
    ARM = unname(arm_label[PLANNED_ARMCD]),
    ACTARMCD = ACTUAL_ARMCD,
    ACTARM = unname(arm_label[ACTUAL_ARMCD]),
    ARMNRS = if_else(PLANNED_ARMCD == "Scrnfail", "SCREEN FAILURE", NA_character_),
    COUNTRY = COUNTRY,
    DMDTC = as.character(create_iso8601(COL_DT, .format = "m/d/y"))
  ) |>
  left_join(ref_dates, by = "USUBJID") |>
  left_join(disp_dates, by = "USUBJID") |>
  left_join(pen_dates, by = "USUBJID") |>
  left_join(death, by = "USUBJID") |>
  mutate(
    RFXSTDTC = RFSTDTC,
    RFICDTC = NA_character_,
    DTHFL = if_else(!is.na(DTHDTC), "Y", NA_character_),
    # screen failures have no reference period
    RFENDTC = if_else(ARMCD == "Scrnfail", NA_character_, RFENDTC),
    DMDY = if_else(
      is.na(RFSTDTC) | is.na(DMDTC), NA_real_,
      as.numeric(as.Date(DMDTC) - as.Date(RFSTDTC)) +
        if_else(as.Date(DMDTC) >= as.Date(RFSTDTC), 1, 0)
    )
  ) |>
  select(STUDYID, DOMAIN, USUBJID, SUBJID, RFSTDTC, RFENDTC, RFXSTDTC, RFXENDTC,
         RFICDTC, RFPENDTC, DTHDTC, DTHFL, SITEID, AGE, AGEU, SEX, RACE, ETHNIC,
         ARMCD, ARM, ACTARMCD, ACTARM, COUNTRY, DMDTC, DMDY, ARMNRS)

dir.create("data/sdtm_generated", showWarnings = FALSE, recursive = TRUE)
write_xpt(dm, "data/sdtm_generated/DM.xpt", name = "DM")
cat("DM:", nrow(dm), "rows written to data/sdtm_generated/DM.xpt\n")
