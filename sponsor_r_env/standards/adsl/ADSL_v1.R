library(dplyr)
source("modules/treatment.R")

adsl_raw <- data.frame(
  USUBJID   = c("S001", "S002", "S003", "S004"),
  ARM       = c("Placebo", "Active", "Active", "Placebo"),
  AGE       = c(64, 71, 58, 66),
  SEX       = c("F", "M", "F", "M"),
  SAFFL     = c("Y", "Y", "Y", "N"),
  ITTFL     = c("Y", "Y", "Y", "Y"),
  SPECIALFL = c("N", "Y", "N", "N")
)

result <- derive_treatment(adsl_raw)
pop <- filter(result, SAFFL == "Y")
cat("ADSL subjects:", nrow(pop), "\n")
