# VS: raw (pharmaverseraw vitals EDC form) -> SDTM VS via sdtm.oak.
# Deterministic template — same scaffolding status as templates/derivations/*.R:
# hand-written to establish the SDTM layer harness; the product generates this
# from a generated SDTM spec. CT comes from knowledge/ct/oak_ct_spec.csv (NCI-EVS).
# Study metadata baked in (visit schedule, unit heuristics) is protocol-derived.
suppressMessages({
  library(dplyr)
  library(sdtm.oak)
  library(haven)
})

vs_raw <- read.csv("data/raw/vs_raw.csv", colClasses = "character") |>
  mutate(across(everything(), ~ na_if(., ""))) |>
  generate_oak_id_vars(pat_var = "PATNUM", raw_src = "vs_raw")

study_ct <- read_ct_spec("knowledge/ct/oak_ct_spec.csv")
dm <- read_xpt("data/sdtm/DM.xpt")

# Map one topic (VSTESTCD/VSTEST/VSORRES) from one raw column.
map_topic <- function(raw_var, testcd, test) {
  hardcode_ct(
    raw_dat = vs_raw, raw_var = raw_var,
    tgt_var = "VSTESTCD", tgt_val = testcd,
    ct_spec = study_ct, ct_clst = "C66741"
  ) |>
    filter(!is.na(.data$VSTESTCD)) |>
    hardcode_ct(
      raw_dat = vs_raw, raw_var = raw_var,
      tgt_var = "VSTEST", tgt_val = test,
      ct_spec = study_ct, ct_clst = "C67153", id_vars = oak_id_vars()
    ) |>
    assign_no_ct(
      raw_dat = vs_raw, raw_var = raw_var,
      tgt_var = "VSORRES", id_vars = oak_id_vars()
    )
}

vs_sysbp <- map_topic("SYS_BP", "SYSBP", "Systolic Blood Pressure") |>
  assign_ct(raw_dat = vs_raw, raw_var = "SUBPOS", tgt_var = "VSPOS",
            ct_spec = study_ct, ct_clst = "C71148", id_vars = oak_id_vars())
vs_diabp <- map_topic("DIA_BP", "DIABP", "Diastolic Blood Pressure") |>
  assign_ct(raw_dat = vs_raw, raw_var = "SUBPOS", tgt_var = "VSPOS",
            ct_spec = study_ct, ct_clst = "C71148", id_vars = oak_id_vars())
vs_pulse <- map_topic("PULSE", "PULSE", "Pulse Rate") |>
  assign_ct(raw_dat = vs_raw, raw_var = "SUBPOS", tgt_var = "VSPOS",
            ct_spec = study_ct, ct_clst = "C71148", id_vars = oak_id_vars())
vs_temp <- map_topic("IT.TEMP", "TEMP", "Temperature") |>
  assign_ct(raw_dat = vs_raw, raw_var = "IT.TEMP_LOC", tgt_var = "VSLOC",
            ct_spec = study_ct, ct_clst = "C74456", id_vars = oak_id_vars())
vs_height <- map_topic("IT.HEIGHT_VSORRES", "HEIGHT", "Height")
vs_weight <- map_topic("IT.WEIGHT", "WEIGHT", "Weight")

# Visit schedule (protocol) and timepoint map (CRF timepoint codelist).
visit_schedule <- c(
  "SCREENING 1" = 1, "SCREENING 2" = 2, "BASELINE" = 3, "AMBUL ECG PLACEMENT" = 3.5,
  "WEEK 2" = 4, "WEEK 4" = 5, "AMBUL ECG REMOVAL" = 6, "WEEK 6" = 7, "WEEK 8" = 8,
  "WEEK 12" = 9, "WEEK 16" = 10, "WEEK 20" = 11, "WEEK 24" = 12, "WEEK 26" = 13,
  "RETRIEVAL" = 201, "UNSCHEDULED 3.1" = 3.1
)
visit_day <- c(
  "SCREENING 1" = -7, "SCREENING 2" = -1, "BASELINE" = 1, "AMBUL ECG PLACEMENT" = 13,
  "WEEK 2" = 14, "WEEK 4" = 28, "AMBUL ECG REMOVAL" = 30, "WEEK 6" = 42, "WEEK 8" = 56,
  "WEEK 12" = 84, "WEEK 16" = 112, "WEEK 20" = 140, "WEEK 24" = 168, "WEEK 26" = 182,
  "RETRIEVAL" = 168
)
tpt_num <- c("after Lying Down for 5 Minutes" = 815,
             "after Standing for 1 Minute" = 816,
             "after Standing for 3 Minutes" = 817)
tpt_eltm <- c("after Lying Down for 5 Minutes" = "PT5M",
              "after Standing for 1 Minute" = "PT1M",
              "after Standing for 3 Minutes" = "PT3M")

vs <- bind_rows(vs_sysbp, vs_diabp, vs_pulse, vs_temp, vs_height, vs_weight) |>
  assign_datetime(
    raw_dat = vs_raw, raw_var = "VTLD",
    tgt_var = "VSDTC", raw_fmt = "d-m-y"
  ) |>
  left_join(
    vs_raw |> select(all_of(c(oak_id_vars(), "INSTANCE", "TMPTC"))),
    by = oak_id_vars()
  ) |>
  mutate(
    STUDYID = "CDISCPILOT01",
    DOMAIN = "VS",
    USUBJID = paste0("01-", patient_number),
    VISIT = toupper(INSTANCE),
    VISITNUM = unname(visit_schedule[VISIT]),
    VISITDY = unname(visit_day[VISIT]),
    VSTPT = if_else(TMPTC == "", NA_character_, toupper(TMPTC)),
    VSTPTNUM = unname(tpt_num[TMPTC]),
    VSELTM = unname(tpt_eltm[TMPTC]),
    # Units are per-record; raw carries no unit column, ranges separate cleanly
    # (kg <= 55.5 vs LB >= 73; C <= 40 vs F >= 93; IN <= 84 vs cm >= 135).
    orres_n = suppressWarnings(as.numeric(VSORRES)),
    VSORRESU = case_when(
      VSTESTCD %in% c("SYSBP", "DIABP") ~ "mmHg",
      VSTESTCD == "PULSE" ~ "BEATS/MIN",
      VSTESTCD == "TEMP" & orres_n >= 50 ~ "F",
      VSTESTCD == "TEMP" ~ "C",
      VSTESTCD == "HEIGHT" & orres_n < 100 ~ "IN",
      VSTESTCD == "HEIGHT" ~ "cm",
      VSTESTCD == "WEIGHT" & orres_n >= 60 ~ "LB",
      VSTESTCD == "WEIGHT" ~ "kg"
    ),
    VSSTRESN = case_when(
      VSORRESU == "F" ~ round((orres_n - 32) * 5 / 9, 2),
      VSORRESU == "IN" ~ round(orres_n * 2.54, 2),
      VSORRESU == "LB" ~ round(orres_n * 0.45359237, 2),
      TRUE ~ orres_n
    ),
    VSSTRESC = as.character(VSSTRESN),
    VSSTRESU = case_when(
      VSTESTCD %in% c("SYSBP", "DIABP") ~ "mmHg",
      VSTESTCD == "PULSE" ~ "BEATS/MIN",
      VSTESTCD == "TEMP" ~ "C",
      VSTESTCD == "HEIGHT" ~ "cm",
      VSTESTCD == "WEIGHT" ~ "kg"
    ),
    VSBLFL = if_else(VISIT == "BASELINE", "Y", NA_character_)
  ) |>
  derive_study_day(
    dm_domain = dm, tgdt = "VSDTC", refdt = "RFSTDTC", study_day_var = "VSDY"
  ) |>
  arrange(USUBJID, VSTESTCD, VISITNUM, VSTPTNUM) |>
  group_by(USUBJID) |>
  mutate(VSSEQ = row_number()) |>
  ungroup() |>
  select(STUDYID, DOMAIN, USUBJID, VSSEQ, VSTESTCD, VSTEST, VSPOS, VSORRES,
         VSORRESU, VSSTRESC, VSSTRESN, VSSTRESU, VSLOC, VSBLFL, VISITNUM, VISIT,
         VISITDY, VSDTC, VSDY, VSTPT, VSTPTNUM, VSELTM)

dir.create("data/sdtm_generated", showWarnings = FALSE, recursive = TRUE)
write_xpt(vs, "data/sdtm_generated/VS.xpt", name = "VS")
cat("VS:", nrow(vs), "rows written to data/sdtm_generated/VS.xpt\n")
