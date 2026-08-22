library(dplyr)
source("modules/teae.R")

adae <- data.frame(
  USUBJID = c("S001", "S002", "S003"),
  AETERM  = c("Headache", "Fatigue", "Dizziness"),
  AESTDT  = as.Date(c("2024-01-10", "2024-01-20", "2024-02-15")),
  AESEV   = c("MILD", "MILD", "SEVERE")
)
adsl <- data.frame(
  USUBJID = c("S001", "S002", "S003"),
  TRTSDT  = as.Date(c("2024-01-05", "2024-01-08", "2024-02-11")),
  SAFFL   = c("Y", "Y", "N")
)

ae1 <- derive_teae(adae, adsl$TRTSDT[match(adae$USUBJID, adsl$USUBJID)])
cat("Treatment-emergent AEs:", sum(ae1$TRTEMFL == "Y", na.rm = TRUE), "\n")
