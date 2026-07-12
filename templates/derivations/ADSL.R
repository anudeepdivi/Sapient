ex_dt <- ex |>
  filter(!is.na(EXSTDTC)) |>
  mutate(EXSTDT = convert_dtc_to_dt(EXSTDTC),
         EXENDT = convert_dtc_to_dt(EXENDTC))

trt_dates <- ex_dt |>
  group_by(STUDYID, USUBJID) |>
  summarise(TRTSDT = min(EXSTDT, na.rm = TRUE),
            TRTEDT = max(coalesce(EXENDT, EXSTDT), na.rm = TRUE),
            CUMDOSE = sum(EXDOSE * (as.numeric(coalesce(EXENDT, EXSTDT) - EXSTDT) + 1), na.rm = TRUE),
            .groups = "drop")

vs_bl <- vs |>
  filter(VSTESTCD %in% c("HEIGHT", "WEIGHT"), VSBLFL == "Y" | VISITNUM == 1) |>
  group_by(STUDYID, USUBJID, VSTESTCD) |>
  summarise(BLVAL = first(VSSTRESN[!is.na(VSSTRESN)]), .groups = "drop") |>
  pivot_wider(names_from = VSTESTCD, values_from = BLVAL)

sv_sum <- sv |>
  mutate(SVSTDT = convert_dtc_to_dt(SVSTDTC)) |>
  group_by(STUDYID, USUBJID) |>
  summarise(VISIT1DT = min(SVSTDT, na.rm = TRUE),
            LASTVISDT = max(SVSTDT, na.rm = TRUE),
            VISNUMEN = max(VISITNUM, na.rm = TRUE),
            .groups = "drop")

ds_disp <- ds |>
  filter(DSCAT == "DISPOSITION EVENT", DSDECOD != "SCREEN FAILURE") |>
  group_by(STUDYID, USUBJID) |>
  slice_tail(n = 1) |>
  ungroup() |>
  select(STUDYID, USUBJID, DCDECOD = DSDECOD, DCSREAS = DSTERM)

mh_dis <- mh |>
  filter(!is.na(MHSTDTC), nchar(MHSTDTC) >= 4) |>
  group_by(STUDYID, USUBJID) |>
  summarise(DISONSDT = min(convert_dtc_to_dt(MHSTDTC), na.rm = TRUE), .groups = "drop")

result <- dm |>
  filter(ACTARMCD != "SCRNFAIL" | ARMCD != "SCRNFAIL") |>
  mutate(
    TRT01P = ARM,
    TRT01A = if_else(ACTARM != "", ACTARM, ARM),
    TRT01PN = as.numeric(factor(TRT01P, levels = sort(unique(TRT01P)))),
    TRT01AN = as.numeric(factor(TRT01A, levels = sort(unique(TRT01A)))),
    SITEGR1 = SITEID,
    RACEN = as.numeric(factor(RACE, levels = sort(unique(RACE)))),
    AGEGR1 = case_when(AGE < 65 ~ "<65", AGE <= 80 ~ "65-80", TRUE ~ ">80"),
    AGEGR1N = case_when(AGE < 65 ~ 1, AGE <= 80 ~ 2, TRUE ~ 3),
    AGEGR2 = if_else(AGE < 65, "<65", ">=65"),
    AGEGR2N = if_else(AGE < 65, 1, 2),
    RFENDT = convert_dtc_to_dt(RFENDTC)
  ) |>
  left_join(trt_dates, by = c("STUDYID", "USUBJID")) |>
  left_join(vs_bl, by = c("STUDYID", "USUBJID")) |>
  left_join(sv_sum, by = c("STUDYID", "USUBJID")) |>
  left_join(ds_disp, by = c("STUDYID", "USUBJID")) |>
  left_join(mh_dis, by = c("STUDYID", "USUBJID")) |>
  mutate(
    TRTDURD = as.numeric(TRTEDT - TRTSDT) + 1,
    AVGDD = round(CUMDOSE / TRTDURD, 1),
    SAFFL = if_else(!is.na(TRTSDT), "Y", "N"),
    ITTFL = if_else(ARM != "", "Y", "N"),
    EFFFL = if_else(SAFFL == "Y" & !is.na(LASTVISDT) & as.numeric(LASTVISDT - TRTSDT) >= 1, "Y", "N"),
    COMP8FL = if_else(!is.na(LASTVISDT) & !is.na(TRTSDT) & as.numeric(LASTVISDT - TRTSDT) >= 56, "Y", "N"),
    COMP16FL = if_else(!is.na(LASTVISDT) & !is.na(TRTSDT) & as.numeric(LASTVISDT - TRTSDT) >= 112, "Y", "N"),
    COMP24FL = if_else(!is.na(LASTVISDT) & !is.na(TRTSDT) & as.numeric(LASTVISDT - TRTSDT) >= 168, "Y", "N"),
    EOSSTT = case_when(is.na(DCDECOD) ~ "ONGOING",
                       DCDECOD == "COMPLETED" ~ "COMPLETED",
                       TRUE ~ "DISCONTINUED"),
    DISCONFL = if_else(EOSSTT == "DISCONTINUED", "Y", ""),
    DSRAEFL = if_else(coalesce(DCDECOD, "") == "ADVERSE EVENT", "Y", ""),
    DTHFL = coalesce(na_if(DTHFL, ""), "N"),
    HEIGHTBL = round(HEIGHT, 1),
    WEIGHTBL = round(WEIGHT, 1),
    BMIBL = round(WEIGHTBL / ((HEIGHTBL / 100)^2), 1),
    BMIBLGR1 = case_when(is.na(BMIBL) ~ NA_character_,
                         BMIBL < 25 ~ "<25",
                         BMIBL < 30 ~ "25-<30",
                         TRUE ~ ">=30"),
    DURDIS = round(as.numeric(TRTSDT - DISONSDT) / 30.4375, 1),
    DURDSGR1 = case_when(is.na(DURDIS) ~ NA_character_,
                         DURDIS < 12 ~ "<12",
                         TRUE ~ ">=12"),
    EDUCLVL = NA_real_,
    MMSETOT = NA_real_
  ) |>
  select(STUDYID, USUBJID, SUBJID, SITEID, SITEGR1, ARM, TRT01P, TRT01PN, TRT01A, TRT01AN,
         TRTSDT, TRTEDT, TRTDURD, AVGDD, CUMDOSE, AGE, AGEGR1, AGEGR1N, AGEGR2, AGEGR2N,
         AGEU, RACE, RACEN, SEX, ETHNIC, SAFFL, ITTFL, EFFFL, COMP8FL, COMP16FL, COMP24FL,
         DISCONFL, DSRAEFL, DTHFL, BMIBL, BMIBLGR1, HEIGHTBL, WEIGHTBL, EDUCLVL, DISONSDT,
         DURDIS, DURDSGR1, VISIT1DT, RFSTDTC, RFENDTC, VISNUMEN, RFENDT, DCDECOD, EOSSTT,
         DCSREAS, MMSETOT)
