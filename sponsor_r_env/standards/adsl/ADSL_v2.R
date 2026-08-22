library(dplyr)
source("modules/treatment.R")
source("modules/dates.R")

adsl_raw <- data.frame(
  USUBJID   = c("S001", "S002", "S003", "S004", "S005", "S006"),
  ARM       = c("Placebo", "Active", "Active", "Placebo", "Active", "Placebo"),
  AGE       = c(64, 71, 58, 66, 73, 61),
  SEX       = c("F", "M", "F", "M", "F", "F"),
  SAFFL     = c("Y", "Y", "Y", "N", "Y", "Y"),
  ITTFL     = c("Y", "Y", "Y", "Y", "Y", "N"),
  SPECIALFL = c("N", "Y", "N", "N", "Y", "N"),
  TRTSDT    = as.Date(c("2024-01-05", "2024-01-08", "2024-02-11",
                        "2024-01-15", "2024-03-02", "2024-02-20")),
  TRTEDT    = as.Date(c("2024-03-05", "2024-04-08", "2024-03-11",
                        "2024-02-15", "2024-06-02", "2024-03-20"))
)

result <- derive_treatment(adsl_raw)
result <- derive_study_day(result)
pop <- filter(result, SAFFL == "Y")
cat("ADSL subjects:", nrow(pop), "\n")
