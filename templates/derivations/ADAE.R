adsl_vars <- adsl |>
  select(STUDYID, USUBJID, SITEID, TRTSDT, TRTEDT, AGE, AGEGR1, AGEGR1N,
         RACE, RACEN, SEX, SAFFL, TRT01A, TRT01AN)

result <- sdtm |>
  filter(!is.na(AETERM)) |>
  inner_join(adsl_vars, by = c("STUDYID", "USUBJID")) |>
  mutate(
    TRTA = TRT01A,
    TRTAN = TRT01AN,
    ASTDT = convert_dtc_to_dt(AESTDTC),
    AENDT = convert_dtc_to_dt(AEENDTC),
    ASTDTF = NA_character_,
    ASTDY = as.numeric(ASTDT - TRTSDT) + if_else(ASTDT >= TRTSDT, 1, 0),
    AENDY = as.numeric(AENDT - TRTSDT) + if_else(AENDT >= TRTSDT, 1, 0),
    ADURN = as.numeric(AENDT - ASTDT) + 1,
    ADURU = if_else(!is.na(ADURN), "days", NA_character_),
    AESEV = AESEV,
    TRTEMFL = if_else(!is.na(ASTDT) & !is.na(TRTSDT) & ASTDT >= TRTSDT, "Y", ""),
    AESER = coalesce(na_if(AESER, ""), "N"),
    AESCAN = coalesce(na_if(AESCAN, ""), "N"),
    AESCONG = coalesce(na_if(AESCONG, ""), "N"),
    AESDISAB = coalesce(na_if(AESDISAB, ""), "N"),
    AESDTH = coalesce(na_if(AESDTH, ""), "N"),
    AESHOSP = coalesce(na_if(AESHOSP, ""), "N"),
    AESLIFE = coalesce(na_if(AESLIFE, ""), "N"),
    AEOUT = AEOUT,
    CQ01NAM = if_else(str_detect(toupper(coalesce(AEDECOD, "")), "APPLICATION|ADMINISTRATION SITE|ERYTHEMA|PRURITUS"),
                      "DERMATOLOGIC EVENTS", NA_character_)
  )

# Treatment-emergent occurrence flags (first occurrence within TRTEMFL == "Y")
te <- result |> filter(TRTEMFL == "Y")

first_flag <- function(df, group_vars) {
  df |>
    arrange(USUBJID, ASTDT, AESEQ) |>
    group_by(across(all_of(group_vars))) |>
    mutate(.rn = row_number()) |>
    ungroup()
}

te <- te |>
  arrange(USUBJID, ASTDT, AESEQ) |>
  group_by(USUBJID) |>
  mutate(AOCCFL = if_else(row_number() == 1, "Y", "")) |>
  ungroup() |>
  group_by(USUBJID, AESOC) |>
  mutate(AOCCSFL = if_else(row_number() == 1, "Y", "")) |>
  ungroup() |>
  group_by(USUBJID, AEDECOD) |>
  mutate(AOCCPFL = if_else(row_number() == 1, "Y", "")) |>
  ungroup() |>
  group_by(USUBJID, AEBODSYS) |>
  mutate(AOCC02FL = if_else(row_number() == 1, "Y", "")) |>
  ungroup() |>
  group_by(USUBJID, AESOC, AEDECOD) |>
  mutate(AOCC03FL = if_else(row_number() == 1, "Y", "")) |>
  ungroup() |>
  group_by(USUBJID, AEBODSYS, AEDECOD) |>
  mutate(AOCC04FL = if_else(row_number() == 1, "Y", "")) |>
  ungroup() |>
  group_by(USUBJID, CQ01NAM) |>
  mutate(AOCC01FL = if_else(row_number() == 1 & !is.na(CQ01NAM), "Y", "")) |>
  ungroup() |>
  select(USUBJID, AESEQ, AOCCFL, AOCCSFL, AOCCPFL, AOCC02FL, AOCC03FL, AOCC04FL, AOCC01FL)

result <- result |>
  left_join(te, by = c("USUBJID", "AESEQ")) |>
  mutate(across(c(AOCCFL, AOCCSFL, AOCCPFL, AOCC02FL, AOCC03FL, AOCC04FL, AOCC01FL),
                ~ coalesce(.x, "")))
